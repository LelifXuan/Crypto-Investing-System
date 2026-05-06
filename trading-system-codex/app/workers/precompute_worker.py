from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.services.precompute import precompute_service

logger = logging.getLogger(__name__)


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
        while not self._stopping.is_set():
            processed = False
            try:
                async with db_manager.session() as session:
                    processed = await precompute_service.process_next(MarketRepository(session))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("precompute worker failed: %s", exc)
            if processed:
                continue
            await precompute_service.wait_for_work(settings.precompute_worker_interval_seconds)


precompute_worker = PrecomputeWorker()
