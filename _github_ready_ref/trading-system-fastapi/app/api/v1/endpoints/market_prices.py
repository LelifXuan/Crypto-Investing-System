from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.cache.market_cache import market_cache
from app.core.config import settings
from app.db.models.market import MarketCandle, MarkPrice
from app.repositories.event_repository import EventRepository
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    CachedBookTickerRead,
    CachedMarkRead,
    CandleCreate,
    CandleRead,
    MarkPriceCreate,
    MarkPriceRead,
)
from app.services.market import MarketService

router = APIRouter(prefix="/market-prices", tags=["market-prices"])


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
    if settings.market_stream_prefer_ws_cache:
        cached = await market_cache.get_mark(instrument_id)
        if cached is not None:
            return MarkPrice(
                mark_id=0,
                instrument_id=instrument_id,
                mark_price=cached.get("mark_price") or cached["price"],
                source=str(cached["source"]),
                ts_event=datetime.fromisoformat(str(cached["ts_event"])),
            )
    repo = MarketRepository(session)
    if prefer_live and settings.market_data_provider.lower() == "gateio":
        service = MarketService(repo, EventRepository(session))
        return await service.fetch_and_persist_live_mark(instrument_id)
    return await repo.latest_mark(instrument_id)


@router.get("/cache/marks/latest", response_model=CachedMarkRead | None)
async def get_cached_mark(
    instrument_id: str = Query(...),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict | None:
    cached = await market_cache.get_mark(instrument_id)
    if cached is None:
        return None
    return {
        **cached,
        "price": cached.get("price"),
        "last_price": cached.get("last_price"),
        "mark_price": cached.get("mark_price"),
        "ts_event": datetime.fromisoformat(str(cached["ts_event"])),
    }


@router.get("/cache/books/latest", response_model=CachedBookTickerRead | None)
async def get_cached_book_ticker(
    instrument_id: str = Query(...),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict | None:
    cached = await market_cache.get_book_ticker(instrument_id)
    if cached is None:
        return None
    return {**cached, "ts_event": datetime.fromisoformat(str(cached["ts_event"]))}


@router.get("/cache/stats")
async def get_cache_stats(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict[str, int]:
    return await market_cache.snapshot()


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
    if prefer_live and settings.market_data_provider.lower() == "gateio":
        service = MarketService(repo)
        return await service.sync_candles_from_provider(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=limit,
            price_kind=price_kind,
        )
    return await repo.list_candles(instrument_id=instrument_id, timeframe=timeframe, limit=limit)


@router.get("/providers/gateio/time")
async def get_gateio_server_time(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> dict:
    service = MarketService(MarketRepository(session))
    return await service.get_gate_server_time()
