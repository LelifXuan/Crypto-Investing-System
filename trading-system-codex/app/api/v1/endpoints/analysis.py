from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.timeframes import normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market import AnalysisBundleRead
from app.services.analysis_bundle import AnalysisBundleService

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/bundle", response_model=AnalysisBundleRead)
async def get_analysis_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    view_window: str = Query(default="default"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    normalized_timeframe = normalize_timeframe_for_cache(timeframe)
    return await AnalysisBundleService(MarketRepository(session)).get_bundle(
        instrument_id, normalized_timeframe, view_window
    )


@router.post("/refresh", response_model=AnalysisBundleRead)
async def refresh_analysis_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    view_window: str = Query(default="default"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    normalized_timeframe = normalize_timeframe_for_cache(timeframe)
    return await AnalysisBundleService(MarketRepository(session)).refresh_bundle(
        instrument_id,
        normalized_timeframe,
        view_window,
        sync_inputs=True,
    )
