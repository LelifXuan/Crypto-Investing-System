from __future__ import annotations

from datetime import timezone, datetime, timedelta
UTC = timezone.utc

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.eventing import EventOutbox, EventStore


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_event(self, event: EventStore, outbox: EventOutbox) -> None:
        self.session.add(event)
        await self.session.flush()
        self.session.add(outbox)
        await self.session.flush()

    async def claim_pending_batch(self, limit: int) -> list[EventOutbox]:
        now = datetime.now(timezone.utc)
        stmt: Select[tuple[EventOutbox]] = (
            select(EventOutbox)
            .where(EventOutbox.status == "PENDING", EventOutbox.available_at <= now)
            .order_by(EventOutbox.created_at, EventOutbox.outbox_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        for item in items:
            item.status = "PROCESSING"
            item.attempts += 1
        await self.session.flush()
        return items

    async def get_outbox(self, outbox_id: int) -> EventOutbox | None:
        return await self.session.get(EventOutbox, outbox_id)

    async def get_event(self, event_id: str) -> EventStore | None:
        return await self.session.get(EventStore, event_id)

    async def mark_processed(self, outbox: EventOutbox) -> None:
        outbox.status = "PROCESSED"
        outbox.processed_at = datetime.now(timezone.utc)
        outbox.last_error = None
        await self.session.flush()

    async def mark_failed(self, outbox: EventOutbox, error: str) -> None:
        outbox.last_error = error[:2000]
        if outbox.attempts >= settings.event_bus_max_retries:
            outbox.status = "FAILED"
        else:
            outbox.status = "PENDING"
            outbox.available_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.event_bus_retry_delay_seconds
            )
        await self.session.flush()
