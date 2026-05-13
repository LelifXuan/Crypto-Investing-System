from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.db.models.market import MarketEvent
from app.repositories.market_repository import MarketRepository
from app.schemas.market import MarketEventCreate, MarketEventQueryResponse, MarketEventRead
from app.services.market import MarketService

UTC = timezone.utc

router = APIRouter(prefix="/market-events", tags=["market-events"])
marketevents_router = APIRouter(prefix="/marketevents", tags=["marketevents"])


async def _queue_event_translations(
    events: list[MarketEvent],
    *,
    enabled: bool,
) -> list[MarketEvent]:
    if not enabled or not events:
        return events
    from app.services.translation import MarketEventTranslationService
    from app.workers.market_event_translation import market_event_translation_worker

    translator = MarketEventTranslationService(enabled=True)
    pending_ids = [
        event.event_id
        for event in events
        if translator.needs_translation(event.payload_json, event.title, event.summary)
    ]
    if pending_ids:
        await market_event_translation_worker.enqueue_event_ids(pending_ids)
    return events


@router.post("", response_model=MarketEventRead)
async def create_market_event(
    payload: MarketEventCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> MarketEvent:
    service = MarketService(MarketRepository(session))
    data = payload.model_dump()
    instrument_ids = data.pop("instrument_ids")
    return await service.add_market_event(MarketEvent(**data), instrument_ids=instrument_ids)


@router.get("", response_model=list[MarketEventRead])
async def list_market_events(
    limit: int = Query(default=50, le=500),
    translate: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> list[MarketEvent]:
    repo = MarketRepository(session)
    events = await repo.list_market_events(limit=limit)
    events = await _queue_event_translations(events, enabled=translate)
    mapping = await repo.list_market_event_instrument_ids([event.event_id for event in events])
    return [
        MarketEventRead(
            event_id=event.event_id,
            category=event.category,
            title=event.title,
            summary=event.summary,
            source=event.source,
            reliability=event.reliability,
            ts_event=event.ts_event,
            payload_json=event.payload_json,
            instrument_ids=mapping.get(event.event_id, []),
        )
        for event in events
    ]


@marketevents_router.post("", response_model=MarketEventRead)
async def create_market_event_alias(
    payload: MarketEventCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> MarketEventRead:
    service = MarketService(MarketRepository(session))
    data = payload.model_dump()
    instrument_ids = data.pop("instrument_ids")
    event = await service.add_market_event(MarketEvent(**data), instrument_ids=instrument_ids)
    return MarketEventRead(
        event_id=event.event_id,
        category=event.category,
        title=event.title,
        summary=event.summary,
        source=event.source,
        reliability=event.reliability,
        ts_event=event.ts_event,
        payload_json=event.payload_json,
        instrument_ids=instrument_ids,
    )


@marketevents_router.get("", response_model=MarketEventQueryResponse)
async def query_market_events(
    category: str | None = Query(default=None),
    instrument_id: str | None = Query(default=None),
    from_ts: int | None = Query(default=None, alias="from"),
    to_ts: int | None = Query(default=None, alias="to"),
    translate: bool = Query(default=False),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> MarketEventQueryResponse:
    repo = MarketRepository(session)
    events = await repo.list_market_events(
        limit=limit,
        category=category,
        instrument_id=instrument_id,
        from_ts=datetime.fromtimestamp(from_ts, tz=timezone.utc) if from_ts else None,
        to_ts=datetime.fromtimestamp(to_ts, tz=timezone.utc) if to_ts else None,
    )
    events = await _queue_event_translations(events, enabled=translate)
    mapping = await repo.list_market_event_instrument_ids([event.event_id for event in events])
    items = [
        MarketEventRead(
            event_id=event.event_id,
            category=event.category,
            title=event.title,
            summary=event.summary,
            source=event.source,
            reliability=event.reliability,
            ts_event=event.ts_event,
            payload_json=event.payload_json,
            instrument_ids=mapping.get(event.event_id, []),
        )
        for event in events
    ]
    return MarketEventQueryResponse(items=items)


@router.post("/sync")
async def sync_market_event_feeds(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> dict:
    from app.workers.market_event_translation import market_event_translation_worker
    from app.workers.market_events_feed import market_event_feed_worker

    count = await market_event_feed_worker.run_once()
    queued = await market_event_translation_worker.run_once()
    return {"status": "ok", "synced_items": count, "translated_items": queued}
