from __future__ import annotations

from datetime import timezone, datetime
UTC = timezone.utc

from app.core.ids import new_id
from app.db.models.eventing import EventOutbox, EventStore
from app.repositories.event_repository import EventRepository


class EventPublisher:
    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    async def publish(
        self,
        *,
        event_type: str,
        source: str,
        partition_key: str,
        payload: dict,
        idempotency_key: str | None = None,
        schema_version: int = 1,
    ) -> str:
        now = datetime.now(timezone.utc)
        event_id = new_id("evt")
        event = EventStore(
            event_id=event_id,
            event_type=event_type,
            schema_version=schema_version,
            source=source,
            partition_key=partition_key,
            idempotency_key=idempotency_key,
            ts_event=now,
            ts_ingest=now,
            trace_id=None,
            span_id=None,
            payload=payload,
        )
        outbox = EventOutbox(
            event_id=event_id,
            event_type=event_type,
            status="PENDING",
            attempts=0,
            available_at=now,
            processed_at=None,
            last_error=None,
        )
        await self.repository.add_event(event, outbox)
        return event_id
