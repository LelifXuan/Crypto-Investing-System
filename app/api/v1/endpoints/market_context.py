from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market_context import MarketContextRead
from app.services.market_context import MarketContextBuilder

router = APIRouter(prefix="/market-context", tags=["market-context"])


@router.get("/snapshot", response_model=MarketContextRead)
async def get_market_context_snapshot(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    cache_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> MarketContextRead:
    context = await MarketContextBuilder(MarketRepository(session)).get_context(
        normalize_instrument_id(instrument_id),
        normalize_timeframe_for_cache(timeframe),
        cache_only=cache_only,
    )
    return MarketContextRead.model_validate(context.__dict__)
