from __future__ import annotations

from datetime import datetime, timezone
UTC = timezone.utc

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.cache.market_cache import market_cache
from app.core.config import settings
from app.core.timeframes import (
    bucket_limit,
    normalize_timeframe_for_cache,
    normalize_timeframe_for_provider,
)
from app.db.models.market import MarketCandle, MarkPrice
from app.repositories.event_repository import EventRepository
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    CacheBookTickerResponse,
    CacheCandleResponse,
    CacheMarkResponse,
    CandleCreate,
    CandleQueryResponse,
    CandleRead,
    MarkPriceCreate,
    MarkPriceRead,
)
from app.services.market import MarketService

router = APIRouter(prefix="/market-prices", tags=["market-prices"])
marketdata_router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.post("/marks", response_model=MarkPriceRead)
async def create_mark_price(
    payload: MarkPriceCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> MarkPrice:
    service = MarketService(MarketRepository(session), EventRepository(session))
    return await service.add_mark_price(MarkPrice(**payload.model_dump()))


@router.get("/marks/latest", response_model=MarkPriceRead | None)
async def get_latest_mark(
    instrument_id: str = Query(...),
    prefer_live: bool = Query(default=settings.market_data_prefer_live),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> MarkPrice | None:
    repo = MarketRepository(session)
    service = MarketService(repo, EventRepository(session))
    return await service.get_best_mark(instrument_id=instrument_id, prefer_live=prefer_live)


@router.post("/candles", response_model=CandleRead)
async def create_candle(
    payload: CandleCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> MarketCandle:
    service = MarketService(MarketRepository(session))
    return await service.add_candle(MarketCandle(**payload.model_dump()))


@router.get("/candles", response_model=list[CandleRead])
async def list_candles(
    instrument_id: str = Query(...),
    timeframe: str = Query(...),
    limit: int = Query(default=200, le=1000),
    prefer_live: bool = Query(default=False),
    price_kind: str = Query(default="last"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> list[MarketCandle]:
    repo = MarketRepository(session)
    provider_timeframe = normalize_timeframe_for_provider(timeframe)
    cache_timeframe = normalize_timeframe_for_cache(timeframe)
    normalized_limit = bucket_limit(limit)
    if prefer_live and settings.market_data_provider.lower() == "gateio":
        service = MarketService(repo)
        return await service.sync_candles_from_provider(
            instrument_id=instrument_id,
            timeframe=provider_timeframe,
            limit=normalized_limit,
            price_kind=price_kind,
        )
    return await repo.list_candles(
        instrument_id=instrument_id,
        timeframe=cache_timeframe,
        limit=normalized_limit,
    )


@router.get("/providers/gateio/time")
async def get_gateio_server_time(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict:
    service = MarketService(MarketRepository(session))
    return await service.get_gate_server_time()


@router.get("/cache/marks/latest", response_model=CacheMarkResponse | None)
async def get_cached_mark(
    instrument_id: str = Query(...),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> CacheMarkResponse | None:
    payload = await market_cache.get_mark(instrument_id)
    if payload is None:
        return None
    return CacheMarkResponse(
        instrument_id=payload["instrument_id"],
        mark_price=payload["mark_price"],
        last_price=payload.get("last_price"),
        source=payload["source"],
        ts_event=datetime.fromisoformat(payload["ts_event"]),
        payload=payload.get("payload", {}),
    )


@router.get("/cache/book-ticker/latest", response_model=CacheBookTickerResponse | None)
async def get_cached_book_ticker(
    instrument_id: str = Query(...),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> CacheBookTickerResponse | None:
    payload = await market_cache.get_book_ticker(instrument_id)
    if payload is None:
        return None
    return CacheBookTickerResponse(
        instrument_id=payload["instrument_id"],
        bid_price=payload.get("bid_price"),
        bid_size=payload.get("bid_size"),
        ask_price=payload.get("ask_price"),
        ask_size=payload.get("ask_size"),
        source=payload["source"],
        ts_event=datetime.fromisoformat(payload["ts_event"]),
    )


@router.get("/cache/candles/latest", response_model=CacheCandleResponse | None)
async def get_cached_candle(
    instrument_id: str = Query(...),
    timeframe: str = Query(...),
    source: str | None = Query(default=None),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> CacheCandleResponse | None:
    payload = await market_cache.get_candle(instrument_id, timeframe, source=source)
    if payload is None:
        return None
    return CacheCandleResponse(
        instrument_id=payload["instrument_id"],
        timeframe=payload["timeframe"],
        ts_open=datetime.fromisoformat(payload["ts_open"]),
        open=payload["open"],
        high=payload["high"],
        low=payload["low"],
        close=payload["close"],
        volume=payload["volume"],
        source=payload["source"],
        is_closed=payload.get("is_closed", False),
        payload=payload.get("payload", {}),
    )


@marketdata_router.get("/candles", response_model=CandleQueryResponse)
async def query_marketdata_candles(
    instrument_id: str = Query(...),
    timeframe: str = Query(...),
    from_ts: int | None = Query(default=None, alias="from"),
    to_ts: int | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, le=1000),
    prefer_live: bool = Query(default=False),
    price_kind: str = Query(default="last"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> CandleQueryResponse:
    repo = MarketRepository(session)
    provider_timeframe = normalize_timeframe_for_provider(timeframe)
    cache_timeframe = normalize_timeframe_for_cache(timeframe)
    normalized_limit = bucket_limit(limit)
    if prefer_live and settings.market_data_provider.lower() == "gateio":
        candles = await MarketService(repo).sync_candles_from_provider(
            instrument_id=instrument_id,
            timeframe=provider_timeframe,
            limit=normalized_limit,
            price_kind=price_kind,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    else:
        candles = await repo.list_candles_filtered(
            instrument_id=instrument_id,
            timeframe=cache_timeframe,
            limit=normalized_limit,
            from_ts=datetime.fromtimestamp(from_ts, tz=timezone.utc) if from_ts else None,
            to_ts=datetime.fromtimestamp(to_ts, tz=timezone.utc) if to_ts else None,
        )
    return CandleQueryResponse(
        instrument_id=instrument_id,
        timeframe=cache_timeframe,
        candles=candles,
    )
