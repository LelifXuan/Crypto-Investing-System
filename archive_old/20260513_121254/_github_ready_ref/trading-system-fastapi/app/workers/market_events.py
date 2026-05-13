from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.services.market_events import MarketEventIngestionService

logger = logging.getLogger(__name__)


class MarketEventPollWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.market_events_enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="market-event-poll-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def sync_once(self, limit: int | None = None) -> dict[str, int]:
        async with db_manager.session() as session:
            service = MarketEventIngestionService(MarketRepository(session))
            return await service.sync(limit=limit or settings.market_events_default_limit)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.sync_once()
                await asyncio.sleep(settings.market_events_poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("market event poll worker failed: %s", exc)
                await asyncio.sleep(settings.market_events_poll_interval_seconds)


market_event_poll_worker = MarketEventPollWorker()
