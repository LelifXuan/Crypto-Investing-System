from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.services.precompute import precompute_service
from app.services.storage_maintenance import StorageMaintenanceService

logger = logging.getLogger(__name__)

# Periodic cache refresh: these page × candidate × timeframe combos are
# re-enqueued at low priority on a fixed interval so caches stay warm even
# when no user is browsing the app.
# 高频刷新：1h/4h 缓存 TTL 短（90min/5h），需要较频繁的预热
_PERIODIC_REFRESH_PLAN_FAST = (
    ("strategy", ["strategy", "market_context"], ("4h", "1h")),
    ("analysis", ["analysis"], ("4h", "1h")),
    ("structure", ["structure"], ("4h", "1h")),
)

# 低频刷新：1d/1w 缓存 TTL 长（36h/9d），无需频繁入队
_PERIODIC_REFRESH_PLAN_SLOW = (
    ("strategy", ["strategy_unified"], ("1d",)),
    ("strategy", ["strategy", "market_context"], ("1w", "1d")),
    ("analysis", ["analysis"], ("1w", "1d")),
    ("structure", ["structure"], ("1w", "1d")),
    ("monitoring", ["monitoring"], ("1d",)),
    ("macro", ["macro"], ("1d",)),
    ("events", ["events"], ("1d",)),
)


class PrecomputeWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.precompute_enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="precompute-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        next_maintenance_at = 0.0
        next_cache_refresh_fast_at = time.monotonic() + settings.cache_refresh_scan_seconds
        next_cache_refresh_slow_at = time.monotonic() + settings.cache_refresh_scan_seconds * 5
        next_scan_refresh_at = time.monotonic() + settings.cache_refresh_scan_seconds
        while not self._stopping.is_set():
            processed = False
            try:
                async with db_manager.writer_session() as session:
                    repository = MarketRepository(session)

                    # 1. Process user-requested / stale-detected precompute hints
                    processed = await precompute_service.process_next(repository)

                    # 2. Storage maintenance (every 900s)
                    if time.monotonic() >= next_maintenance_at:
                        from app.services.btc_derivatives.live_service import (
                            btc_derivatives_live_service,
                        )

                        await StorageMaintenanceService(
                            btc_derivatives_live_service.collector.archive
                        ).run(repository)
                        next_maintenance_at = time.monotonic() + 900

                    # 3. Periodic cache refresh — two cadences:
                    #    Fast (1h/4h): every cache_refresh_scan_seconds (120s)
                    #    Slow (1w/1d): every 5× cache_refresh_scan_seconds (600s)
                    if time.monotonic() >= next_cache_refresh_fast_at:
                        await self._enqueue_periodic_refresh(
                            repository, _PERIODIC_REFRESH_PLAN_FAST
                        )
                        next_cache_refresh_fast_at = (
                            time.monotonic() + settings.cache_refresh_scan_seconds
                        )
                    if time.monotonic() >= next_cache_refresh_slow_at:
                        await self._enqueue_periodic_refresh(
                            repository, _PERIODIC_REFRESH_PLAN_SLOW
                        )
                        next_cache_refresh_slow_at = (
                            time.monotonic() + settings.cache_refresh_scan_seconds * 5
                        )

                    # 4. Periodic scan refresh — the strategy_scan cache is a
                    #    single global row (all instruments × timeframes) that
                    #    the per-instrument refresh plan above does not cover.
                    #    Without this, the scan cache expires and the next user
                    #    refresh pays the full ~13s recompute cost. Refresh at
                    #    the same cadence as the per-instrument plan but offset
                    #    by half a period so the two refreshes don't collide.
                    if time.monotonic() >= next_scan_refresh_at:
                        await self._refresh_scan_cache(repository)
                        next_scan_refresh_at = (
                            time.monotonic() + settings.cache_refresh_scan_seconds
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("precompute worker failed: %s", exc)
            # Don't re-scan next_cache_refresh_at on error — use a shorter
            # back-off so we don't spin, but still retry within a reasonable time
            if not processed and not self._stopping.is_set():
                await precompute_service.wait_for_work(
                    settings.precompute_worker_interval_seconds
                )

    async def _refresh_scan_cache(self, repository: MarketRepository) -> None:
        """Periodically rebuild the global strategy_scan cache row.

        The scan cache is a single row covering all instruments × timeframes.
        It is not covered by the per-instrument refresh plan, so without this
        the row expires and the next user refresh pays the full recompute
        cost.  We only rebuild when the existing row is stale/missing to
        avoid redundant work when a user refresh already repopulated it.

        scan_all runs serially (see OpportunityScanner) and is wrapped in a
        batch timeout so a cold or blocked scan can never stall the
        precompute loop that analysis / structure snapshots depend on —
        the concurrent rewrite (2026-08) that spawned one DB session per
        cell wedged the SQLite single-writer lock for minutes and froze
        every snapshot rebuild.
        """
        from app.services.cache_registry import (
            CACHE_SOURCE_VERSION,
            cache_status,
            expires_at_for_scan,
            strategy_scan_cache_key,
        )
        from app.services.strategy_unified.opportunity_scanner import (
            OpportunityScanner,
        )

        cache_key = strategy_scan_cache_key()
        try:
            cache = await repository.get_page_snapshot_cache(cache_key)
            status = cache_status(cache) if cache else "missing"
            # Skip if a fresh scan already exists (e.g. a user refresh just
            # rebuilt it).  This avoids redundant background scans.
            if status == "fresh":
                return
        except Exception:
            logger.exception("scan_refresh: cache lookup failed")
            # Proceed to rebuild — better a redundant scan than a permanently
            # cold cache.

        try:
            instruments = await repository.list_instruments()
            instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
            if not instrument_ids:
                return
            instrument_codes = {}
            for i in instruments:
                code = (
                    getattr(i, "base_ccy", None)
                    or getattr(i, "symbol", None)
                    or i.instrument_id
                )
                instrument_codes[i.instrument_id] = code

            scanner = OpportunityScanner(repository)
            result = await asyncio.wait_for(
                scanner.scan_all(instrument_ids, instrument_codes),
                timeout=settings.macro_sync_batch_timeout_seconds,
            )

            import dataclasses
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            result_dict = dataclasses.asdict(result)
            result_dict["cache_meta"] = dict(result_dict.get("cache_meta") or {})
            result_dict["cache_meta"]["source"] = "periodic_refresh"
            await repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="strategy_scan",
                payload_json=result_dict,
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=now,
                expires_at=expires_at_for_scan(now),
                source_version=CACHE_SOURCE_VERSION,
            )
            logger.info(
                "scan_refresh: rebuilt strategy_scan cache "
                "(%d instruments, %d cells) in background",
                len(instrument_ids),
                len(result.matrix),
            )
        except asyncio.TimeoutError:
            logger.warning("scan_refresh: batch timed out, skipping this cycle")
        except Exception:
            logger.exception("scan_refresh: background scan rebuild failed")

    async def _enqueue_periodic_refresh(
        self,
        repository: MarketRepository,
        plan: tuple[tuple[str, list[str], tuple[str, ...]], ...],
    ) -> None:
        """Enqueue low-priority refresh hints for all instruments."""
        try:
            instruments = await repository.list_instruments()
        except Exception:
            logger.exception("periodic_cache_refresh: list_instruments failed")
            return

        instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
        if not instrument_ids:
            return

        count = 0
        for iid in instrument_ids:
            for page, candidates, timeframes in plan:
                for tf in timeframes:
                    await precompute_service.enqueue_hint(
                        PrecomputeHintRequest(
                            current_page=page,
                            instrument_id=iid,
                            timeframe=tf,
                            reason="periodic_cache_refresh",
                            visible=False,
                            candidates=list(candidates),
                            priority=6,  # below startup(3) and user(5)
                        )
                    )
                    count += 1
        # BTC derivatives (instrument-agnostic, refresh once per cycle)
        await precompute_service.enqueue_hint(
            PrecomputeHintRequest(
                current_page="btc-derivatives",
                reason="periodic_cache_refresh",
                visible=False,
                candidates=["btc_derivatives"],
                priority=6,
            )
        )
        count += 1
        logger.debug(
            "periodic_cache_refresh: enqueued %d hints for %d instruments",
            count,
            len(instrument_ids),
        )


precompute_worker = PrecomputeWorker()
