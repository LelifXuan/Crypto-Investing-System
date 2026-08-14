from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.config import settings
from app.db.models.market import MarketEvent, MarketEventTranslationMap
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    MarketEventCreate,
    MarketEventQueryResponse,
    MarketEventRead,
    SupplyEventCalendarResponse,
)
from app.services.market import MarketService
from app.services.translation.normalizer import looks_like_english

UTC = timezone.utc
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/market-events", tags=["market-events"])
marketevents_router = APIRouter(prefix="/marketevents", tags=["marketevents"])


# BNB's original vesting schedule ended in 2021, while 20M BNB remains marked
# locked without a published future release date. Keep it visible as coverage,
# not as a fabricated dated event. Source snapshot reviewed 2026-08-13.
_BNB_UNSCHEDULED_QUANTITY = Decimal("20000000")
_BNB_SCHEDULE_SOURCE = "Tokenomics.com"
_BNB_SCHEDULE_SOURCE_REF = "https://app.tokenomics.com/tokenomics/binance-coin/unlocks"


def _payload_decimal(payload: dict[str, Any], key: str) -> Decimal | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _display_mark(value: Decimal | None) -> Decimal | None:
    return value.quantize(Decimal("0.00000001")) if value is not None else None


def _display_value(quantity: Decimal | None, price: Decimal | None) -> Decimal | None:
    if quantity is None or price is None:
        return None
    return (quantity * price).quantize(Decimal("0.01"))


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
    from app.workers.market_event_translation import market_event_translation_worker

    # The translation status endpoint is the public surface that summarizes
    # how many MarketEventTranslationMap rows are in each lifecycle state. The
    # aggregation lives in MarketRepository so the public counts stay
    # consistent with the normalized translation table instead of the
    # denormalized event payload.
    _ = MarketEventTranslationMap

    worker_status = market_event_translation_worker.worker_status
    base_response = {
        "queued": worker_status.get("queued", 0),
        "inflight": worker_status.get("inflight", 0),
        "queue_depth": worker_status.get("queue_size", 0),
        "worker_running": worker_status.get("running", False),
        "last_error": worker_status.get("last_error"),
        "last_error_at": worker_status.get("last_error_at"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not settings.market_events_translate_enabled:
        return {
            "total": 0, "translated": 0, "pending": 0, "failed": 0,
            "disabled": True,
            **base_response,
        }

    repo = MarketRepository(session)
    counts = await repo.count_market_event_translation_maps_by_status()
    translated = int(counts.get("translated", 0))
    pending = int(counts.get("pending", 0))
    failed = int(counts.get("error", 0)) + int(counts.get("failed", 0))
    total = int(counts.get("total", 0))

    if total == 0:
        events = await repo.list_recent_market_events(limit=500)
        translatable = 0
        for event in events:
            if event.title and looks_like_english(event.title):
                translatable += 1
        total = translatable

    return {
        "total": total,
        "translated": translated,
        "pending": pending,
        "failed": failed,
        "disabled": False,
        **base_response,
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
        deadline = _time.monotonic() + 30
        while translated_items < 200 and _time.monotonic() < deadline:
            processed = await market_event_translation_worker.run_once()
            if processed <= 0:
                break
            translated_items += processed
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


@router.get(
    "/supply-event-calendar",
    response_model=SupplyEventCalendarResponse,
)
async def list_supply_event_calendar(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> SupplyEventCalendarResponse:
    """Upcoming token releases with current local mark-price valuation.

    Dated nodes stay read-only and come from immutable supply snapshots. Assets
    with a known locked balance but no verified future date are returned in
    ``coverage`` so the UI can disclose the gap without inventing an event.
    """
    repo = MarketRepository(session)
    nodes = await repo.list_supply_calendar_nodes(limit=limit)
    instrument_ids = {node.instrument_id for node in nodes}
    instrument_ids.add("bnb-usdt-perp")
    marks = {instrument_id: await repo.latest_mark(instrument_id) for instrument_id in instrument_ids}

    items: list[dict[str, Any]] = []
    for node in nodes:
        payload = node.payload_json or {}
        quantity = _payload_decimal(payload, "nominal_unlock_qty")
        mark = marks.get(node.instrument_id)
        mark_price = _display_mark(mark.mark_price if mark else None)
        items.append(
            {
                "node_id": node.node_id,
                "instrument_id": node.instrument_id,
                "asset": node.asset,
                "node_type": node.node_type,
                "event_at": node.event_at,
                "snapshot_id": node.snapshot_id,
                "allocation": payload.get("allocation"),
                "unlock_quantity": quantity,
                "release_pct": _payload_decimal(payload, "release_pct"),
                "mark_price": mark_price,
                "market_value": _display_value(quantity, mark_price),
                "price_as_of": mark.ts_event if mark else None,
                "source": node.source,
            }
        )

    bnb_mark = marks.get("bnb-usdt-perp")
    bnb_price = _display_mark(bnb_mark.mark_price if bnb_mark else None)
    return SupplyEventCalendarResponse(
        items=items,
        coverage=[
            {
                "asset": "BNB",
                "instrument_id": "bnb-usdt-perp",
                "schedule_status": "no_verified_future_nodes",
                "remaining_quantity": _BNB_UNSCHEDULED_QUANTITY,
                "mark_price": bnb_price,
                "market_value": _display_value(_BNB_UNSCHEDULED_QUANTITY, bnb_price),
                "price_as_of": bnb_mark.ts_event if bnb_mark else None,
                "source": _BNB_SCHEDULE_SOURCE,
                "source_ref": _BNB_SCHEDULE_SOURCE_REF,
                "note": "仍有未释放余额，但没有可核验的未来解锁日期；不生成推测节点。",
            }
        ],
    )
