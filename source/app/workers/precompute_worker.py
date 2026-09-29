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
#
# The former 120-second producer generated more work than the single SQLite
# writer could drain (observed queue depth 153). FAST now runs every 10 min,
# SLOW every two hours, and each hint pins its candidate to avoid related-task
# fan-out. Scan publication has its own timer and reads published inputs;
# it never waits behind the precompute task queue.
_PERIODIC_REFRESH_PLAN_FAST = (
    ("analysis", ["analysis"], ("1h",)),
    ("structure", ["structure"], ("1h",)),
)

_PERIODIC_REFRESH_PLAN_MEDIUM = (("strategy", ["strategy"], ("1h",)),)

# 低频刷新：1d/1w 缓存 TTL 长（36h/9d），无需频繁入队
_PERIODIC_REFRESH_PLAN_SLOW = (
    ("analysis", ["analysis"], ("4h",)),
    ("structure", ["structure"], ("4h",)),
    ("strategy", ["strategy"], ("4h", "1d", "1w")),
    ("strategy", ["market_context"], ("1d",)),
    ("monitoring", ["monitoring"], ("1d",)),
)


class PrecomputeWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._scan_task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.precompute_enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="precompute-worker")
        self._scan_task = asyncio.create_task(self._run_scan_loop(), name="strategy-scan-publisher")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        if self._scan_task is not None:
            self._scan_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        if self._scan_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task
        self._task = None
        self._scan_task = None

    async def _run_loop(self) -> None:
        next_maintenance_at = 0.0
        fast_interval = max(600, settings.cache_refresh_scan_seconds * 5)
        medium_interval = max(1800, settings.cache_refresh_scan_seconds * 15)
        slow_interval = max(7200, settings.cache_refresh_scan_seconds * 60)
        next_cache_refresh_fast_at = time.monotonic() + 5
        next_cache_refresh_medium_at = time.monotonic() + 15
        next_cache_refresh_slow_at = time.monotonic() + 30
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
                    #    Short-horizon inputs: every 10 minutes by default.
                    #    4h/daily inputs: every two hours by default.
                    if time.monotonic() >= next_cache_refresh_fast_at:
                        await self._enqueue_periodic_refresh(
                            repository, _PERIODIC_REFRESH_PLAN_FAST
                        )
                        next_cache_refresh_fast_at = time.monotonic() + fast_interval
                    if time.monotonic() >= next_cache_refresh_medium_at:
                        await self._enqueue_periodic_refresh(
                            repository, _PERIODIC_REFRESH_PLAN_MEDIUM
                        )
                        next_cache_refresh_medium_at = time.monotonic() + medium_interval
                    if time.monotonic() >= next_cache_refresh_slow_at:
                        await self._enqueue_periodic_refresh(
                            repository, _PERIODIC_REFRESH_PLAN_SLOW, include_global=True
                        )
                        next_cache_refresh_slow_at = time.monotonic() + slow_interval

            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("precompute worker failed: %s", exc)
            # Don't re-scan next_cache_refresh_at on error — use a shorter
            # back-off so we don't spin, but still retry within a reasonable time
            if not processed and not self._stopping.is_set():
                await precompute_service.wait_for_work(settings.precompute_worker_interval_seconds)

    async def _run_scan_loop(self) -> None:
        """Publish the scan independently of page requests and the task queue."""
        interval = min(30, settings.cache_refresh_scan_seconds)
        while not self._stopping.is_set():
            try:
                await self._refresh_scan_cache()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scan_refresh: publisher failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def _refresh_scan_cache(self) -> None:
        """Project published unified snapshots, then atomically publish one row."""
        from app.services.cache_registry import (
            CACHE_SOURCE_VERSION,
            cache_status,
            expires_at_for_scan,
            strategy_scan_cache_key,
        )
        from app.services.strategy_unified.opportunity_scanner import (
            OpportunityScanner,
            scan_inputs_newer_than_scan,
        )

        cache_key = strategy_scan_cache_key()
        async with db_manager.session() as session:
            repository = MarketRepository(session)
            cache = await repository.get_page_snapshot_cache(cache_key)
            status = cache_status(cache) if cache else "missing"
            if status == "fresh" and not await scan_inputs_newer_than_scan(repository, cache):
                return
            instruments = await repository.list_instruments()
            instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
            if not instrument_ids:
                return
            instrument_codes = {}
            for i in instruments:
                code = getattr(i, "base_ccy", None) or getattr(i, "symbol", None) or i.instrument_id
                instrument_codes[i.instrument_id] = code

            result = await OpportunityScanner(repository).scan_published(
                instrument_ids, instrument_codes
            )

        import dataclasses
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        result_dict = dataclasses.asdict(result)
        result_dict["cache_meta"]["source"] = "background_publisher"
        expiry = expires_at_for_scan(now)
        result_dict["cache_meta"]["fresh_until"] = expiry.isoformat()
        input_at = result.cache_meta.get("input_snapshot_at")
        input_ts = datetime.fromisoformat(input_at) if input_at else None
        async with db_manager.writer_session() as session:
            repository = MarketRepository(session)
            await repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="strategy_scan",
                payload_json=result_dict,
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=input_ts,
                expires_at=expiry,
                source_version=CACHE_SOURCE_VERSION,
            )
        logger.info(
            "scan_refresh: published %d instruments and %d cells from snapshots",
            len(instrument_ids),
            len(result.matrix),
        )

    async def _enqueue_periodic_refresh(
        self,
        repository: MarketRepository,
        plan: tuple[tuple[str, list[str], tuple[str, ...]], ...],
        *,
        include_global: bool = False,
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
        if include_global:
            for page, candidate in (("macro", "macro"), ("events", "events")):
                await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page=page,
                        reason="periodic_cache_refresh",
                        visible=False,
                        candidates=[candidate],
                        priority=6,
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
