from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.db import db_manager
from app.events.handlers import handle_domain_event
from app.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventBusWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not settings.event_bus_enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="event-bus-worker")

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

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                processed = await self._poll_once()
                if processed == 0:
                    await asyncio.sleep(settings.event_bus_poll_interval_ms / 1000)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("event bus loop failed: %s", exc)
                await asyncio.sleep(settings.event_bus_poll_interval_ms / 1000)

    async def _poll_once(self) -> int:
        async with db_manager.session() as claim_session:
            claim_repo = EventRepository(claim_session)
            batch = await claim_repo.claim_pending_batch(settings.event_bus_batch_size)
        if not batch:
            return 0

        for item in batch:
            async with db_manager.session() as process_session:
                repo = EventRepository(process_session)
                outbox = await repo.get_outbox(item.outbox_id)
                if outbox is None:
                    continue
                event = await repo.get_event(outbox.event_id)
                if event is None:
                    await repo.mark_failed(outbox, "event payload not found")
                    continue
                try:
                    await handle_domain_event(process_session, event)
                    await repo.mark_processed(outbox)
                except Exception as exc:  # pragma: no cover
                    logger.exception("failed processing event %s: %s", event.event_id, exc)
                    await repo.mark_failed(outbox, str(exc))
        return len(batch)


event_bus_worker = EventBusWorker()
