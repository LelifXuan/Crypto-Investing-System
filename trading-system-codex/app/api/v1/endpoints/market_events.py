from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.config import settings
from app.db.models.market import MarketEvent
from app.repositories.market_repository import MarketRepository
from app.schemas.market import MarketEventCreate, MarketEventQueryResponse, MarketEventRead
from app.services.market import MarketService

UTC = timezone.utc
logger = logging.getLogger(__name__)


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


def _event_payload_for_view(payload: dict[str, Any] | None, translate: bool) -> dict[str, Any]:
    view_payload = dict(payload or {})
    if translate:
        return view_payload
    for key in (
        "translated_title",
        "translated_summary",
        "translation_error",
        "translation_error_at",
        "translation_provider",
    ):
        view_payload.pop(key, None)
    view_payload["translation_status"] = "disabled"
    return view_payload


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
            payload_json=_event_payload_for_view(event.payload_json, translate),
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
            payload_json=_event_payload_for_view(event.payload_json, translate),
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


@router.get("/translations/status")
async def get_translation_status(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    from app.db.models.market import MarketEventTranslationMap
    from app.workers.market_event_translation import market_event_translation_worker

    total_events = 0
    translated = 0
    pending = 0
    failed = 0
    try:
        total_events = (
            await session.execute(select(func.count()).select_from(MarketEventTranslationMap))
        ).scalar() or 0
        translated = (
            await session.execute(
                select(func.count()).where(MarketEventTranslationMap.status == "translated")
            )
        ).scalar() or 0
        pending = (
            await session.execute(
                select(func.count()).where(
                    MarketEventTranslationMap.status.in_(["pending", "queued"])
                )
            )
        ).scalar() or 0
        failed = (
            await session.execute(
                select(func.count()).where(MarketEventTranslationMap.status == "failed")
            )
        ).scalar() or 0
    except Exception:
        pass

    worker_status = market_event_translation_worker.worker_status
    return {
        "total": total_events,
        "translated": translated,
        "pending": pending,
        "failed": failed,
        "queued": worker_status.get("queued", 0),
        "inflight": worker_status.get("inflight", 0),
        "queue_depth": worker_status.get("queue_size", 0),
        "worker_running": worker_status.get("running", False),
        "disabled": not settings.market_events_translate_enabled,
        "last_error": worker_status.get("last_error"),
        "last_error_at": worker_status.get("last_error_at"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/translations/refresh")
async def refresh_translations(
    limit: int = Query(default=20),
    max_batches: int = Query(default=3),
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    from app.services.translation import MarketEventTranslationService
    from app.workers.market_event_translation import market_event_translation_worker

    if not settings.market_events_translate_enabled:
        return {
            "status": "disabled",
            "limit": limit,
            "max_batches": max_batches,
            "force": force,
            "enqueued": 0,
            "translated_items": 0,
            "queue_depth": 0,
            "worker_running": False,
        }

    repo = MarketRepository(session)
    translator = MarketEventTranslationService(enabled=True)
    events = await repo.list_market_events(limit=max(1, min(limit, 200)))
    pending_ids = [
        event.event_id
        for event in events
        if force or translator.needs_translation(event.payload_json, event.title, event.summary)
    ]
    enqueue_result = await market_event_translation_worker.enqueue_event_ids(pending_ids)
    enqueued = (
        int(enqueue_result)
        if isinstance(enqueue_result, int)
        else int(enqueue_result.get("enqueued", 0))
    )
    translated_items = 0
    if not market_event_translation_worker.worker_status.get("running"):
        for _ in range(max(1, min(max_batches, 10))):
            processed = await market_event_translation_worker.run_once()
            translated_items += processed
            if processed <= 0:
                break
    worker_status = market_event_translation_worker.worker_status
    return {
        "status": "queued" if pending_ids else "nothing_to_translate",
        "limit": limit,
        "max_batches": max_batches,
        "force": force,
        "candidate_count": len(events),
        "pending_count": len(pending_ids),
        "enqueued": enqueued,
        "translated_items": translated_items,
        "queue_depth": worker_status.get("queue_size", 0),
        "worker_running": worker_status.get("running", False),
        "last_error": worker_status.get("last_error"),
    }
