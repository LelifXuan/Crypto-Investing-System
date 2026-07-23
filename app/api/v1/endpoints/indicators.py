from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.config import settings
from app.db.models.market import IndicatorRefreshPolicy
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    IndicatorCalculateRequest,
    IndicatorPoint,
    IndicatorQueryResponse,
    IndicatorRefreshPolicyCreate,
    IndicatorRefreshPolicyRead,
    IndicatorValueRead,
    PrecomputeHintRequest,
)
from app.services.analysis_bundle import AnalysisBundleService
from app.services.indicators import IndicatorService
from app.services.precompute import precompute_service

UTC = timezone.utc
router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.post("/calculate", response_model=list[IndicatorValueRead])
async def calculate_indicators(
    payload: IndicatorCalculateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorService(MarketRepository(session))
    result = await service.calculate_all(**payload.model_dump())
    await AnalysisBundleService(MarketRepository(session)).refresh_bundle(
        payload.instrument_id,
        payload.timeframe,
        "default",
        sync_inputs=False,
    )
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id=payload.instrument_id,
            timeframe=payload.timeframe,
            reason="indicators_calculate",
            priority=3,
        )
    )
    return result


@router.post("/refresh", response_model=list[IndicatorValueRead])
async def refresh_indicators(
    payload: IndicatorCalculateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorService(MarketRepository(session))
    result = await service.calculate_all(**payload.model_dump())
    await AnalysisBundleService(MarketRepository(session)).refresh_bundle(
        payload.instrument_id,
        payload.timeframe,
        "default",
        sync_inputs=False,
    )
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id=payload.instrument_id,
            timeframe=payload.timeframe,
            reason="indicators_refresh",
            priority=3,
        )
    )
    return result


@router.get("/raw", response_model=list[IndicatorValueRead])
async def list_indicators(
    instrument_id: str = Query(...),
    timeframe: str = Query(...),
    indicator_name: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = MarketRepository(session)
    return await repo.list_indicator_values(
        instrument_id=instrument_id,
        timeframe=timeframe,
        indicator_name=indicator_name,
        limit=limit,
    )


@router.get("", response_model=IndicatorQueryResponse)
async def query_indicators(
    instrument_id: str = Query(...),
    timeframe: str = Query(...),
    indicator_name: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    auto_calculate: bool = Query(default=settings.indicator_read_auto_refresh),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> IndicatorQueryResponse:
    service = IndicatorService(MarketRepository(session))
    values, refreshed = await service.ensure_indicator_data(
        instrument_id=instrument_id,
        timeframe=timeframe,
        indicator_name=indicator_name,
        limit=limit,
        auto_calculate=auto_calculate,
    )
    points = [
        IndicatorPoint(
            ts=int(item.ts_value.timestamp()),
            indicator=item.indicator_name,
            value=item.value_json,
        )
        for item in reversed(values)
    ]
    last_updated_ts = (
        int(max((item.ts_value for item in values), default=datetime.now(timezone.utc)).timestamp())
        if values
        else None
    )
    next_refresh_ts = (
        last_updated_ts + settings.indicator_refresh_interval_seconds
        if last_updated_ts is not None
        else None
    )
    return IndicatorQueryResponse(
        instrument_id=instrument_id,
        timeframe=timeframe,
        refreshed=refreshed,
        last_updated_ts=last_updated_ts,
        next_refresh_ts=next_refresh_ts,
        refresh_interval_seconds=settings.indicator_refresh_interval_seconds,
        points=points,
    )


@router.post("/policies", response_model=IndicatorRefreshPolicyRead)
async def upsert_indicator_policy(
    payload: IndicatorRefreshPolicyCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    repo = MarketRepository(session)
    model = IndicatorRefreshPolicy(**payload.model_dump())
    return await repo.upsert_indicator_refresh_policy(model)


@router.get("/policies", response_model=list[IndicatorRefreshPolicyRead])
async def list_indicator_policies(
    instrument_id: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MarketRepository(session).list_indicator_refresh_policies(
        instrument_id=instrument_id,
        timeframe=timeframe,
        enabled_only=enabled_only,
    )


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_indicator_policy(
    policy_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    deleted = await MarketRepository(session).delete_indicator_refresh_policy(policy_id)
    if not deleted:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
