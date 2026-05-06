from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.db.models.market import IndicatorRefreshPolicy
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    IndicatorCalculateRequest,
    IndicatorRefreshPolicyCreate,
    IndicatorRefreshPolicyRead,
    IndicatorValueRead,
)
from app.services.indicators import IndicatorService

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.post("/calculate", response_model=list[IndicatorValueRead])
async def calculate_indicators(
    payload: IndicatorCalculateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorService(MarketRepository(session))
    return await service.calculate_all(**payload.model_dump())


@router.get("", response_model=list[IndicatorValueRead])
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
    repo = MarketRepository(session)
    return await repo.list_indicator_refresh_policies(
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
    repo = MarketRepository(session)
    deleted = await repo.delete_indicator_refresh_policy(policy_id)
    if not deleted:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
