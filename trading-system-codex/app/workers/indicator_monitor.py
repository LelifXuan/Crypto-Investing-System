from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timezone, datetime, timedelta
UTC = timezone.utc

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService

logger = logging.getLogger(__name__)
STALE_REFRESH_MAX_AGE = timedelta(days=1)


class IndicatorMonitorWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.monitoring_scheduler_enabled or self._task is not None:
            return
        async with db_manager.session() as session:
            service = IndicatorMonitoringService(MarketRepository(session))
            await service.seed_defaults()
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="indicator-monitor-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                async with db_manager.session() as session:
                    service = IndicatorMonitoringService(MarketRepository(session))
                    if settings.worker_profile.lower() == "desktop_light":
                        await self._run_lightweight_refresh(service)
                    else:
                        await service.run_due_policies(datetime.now(timezone.utc))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("indicator monitor worker failed: %s", exc)
            sleep_seconds = (
                settings.monitoring_stale_refresh_check_seconds
                if settings.worker_profile.lower() == "desktop_light"
                else settings.monitoring_scheduler_poll_seconds
            )
            await asyncio.sleep(sleep_seconds)

    async def _run_lightweight_refresh(self, service: IndicatorMonitoringService) -> None:
        now = datetime.now(timezone.utc)
        repository = service.repository

        macro_latest = await repository.list_indicator_observations(category="macro", limit=1)
        if not macro_latest or self._is_stale(macro_latest[0].observation_ts, now):
            logger.info("indicator monitor lightweight refresh: syncing macro observations")
            try:
                await service.sync_macro()
            except Exception as exc:  # pragma: no cover
                logger.warning("indicator monitor lightweight refresh: macro sync failed: %s", exc)

        onchain_latest = await repository.list_indicator_observations(category="onchain", limit=1)
        if not onchain_latest or self._is_stale(onchain_latest[0].observation_ts, now):
            logger.info("indicator monitor lightweight refresh: syncing on-chain observations")
            try:
                await service.sync_onchain()
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "indicator monitor lightweight refresh: on-chain sync failed: %s", exc
                )

        instruments = await repository.list_instruments()
        for instrument in instruments:
            technical_latest = await repository.list_indicator_observations(
                category="technical",
                instrument_id=instrument.instrument_id,
                limit=1,
            )
            if technical_latest and not self._is_stale(technical_latest[0].observation_ts, now):
                continue
            logger.info(
                "indicator monitor lightweight refresh: syncing technical observations for %s",
                instrument.instrument_id,
            )
            try:
                await service.sync_technical(instrument.instrument_id)
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "indicator monitor lightweight refresh: technical sync failed for %s: %s",
                    instrument.instrument_id,
                    exc,
                )

    @staticmethod
    def _is_stale(ts: datetime, now: datetime) -> bool:
        value = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        return value < now - STALE_REFRESH_MAX_AGE


indicator_monitor_worker = IndicatorMonitorWorker()
