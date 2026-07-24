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
_PERIODIC_REFRESH_PLAN = (
    ("strategy", ["strategy_unified"], ("1d",)),
    ("strategy", ["strategy", "market_context"], ("1w", "1d", "4h", "1h")),
    ("analysis", ["analysis"], ("1w", "1d", "4h", "1h")),
    ("structure", ["structure"], ("1w", "1d", "4h", "1h")),
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
        next_cache_refresh_at = time.monotonic() + settings.cache_refresh_scan_seconds
        while not self._stopping.is_set():
            processed = False
            try:
                async with db_manager.session() as session:
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

                    # 3. Periodic cache refresh — keep caches warm independently
                    #    of page visits. Enqueues low-priority hints for all
                    #    instruments × critical page/timeframe combos.
                    if time.monotonic() >= next_cache_refresh_at:
                        await self._enqueue_periodic_refresh(repository)
                        next_cache_refresh_at = (
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

    async def _enqueue_periodic_refresh(self, repository: MarketRepository) -> None:
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
            for page, candidates, timeframes in _PERIODIC_REFRESH_PLAN:
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
