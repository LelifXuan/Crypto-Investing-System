from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.services.market_events_feed import MarketEventFeedService

logger = logging.getLogger(__name__)


class MarketEventFeedWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.market_events_feed_enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="market-events-feed-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> int:
        async with db_manager.session() as session:
            service = MarketEventFeedService(MarketRepository(session))
            return await service.sync_default_feeds()

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                count = await self.run_once()
                logger.info("market events feed synced %s items", count)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("market events feed worker failed: %s", exc)
            await asyncio.sleep(settings.market_events_poll_seconds)


market_event_feed_worker = MarketEventFeedWorker()
