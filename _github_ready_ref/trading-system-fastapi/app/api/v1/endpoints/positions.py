from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.db.models.position import Fill
from app.repositories.event_repository import EventRepository
from app.repositories.position_repository import PositionRepository
from app.schemas.common import RebuildResponse
from app.schemas.positions import FillCreate, FillRead, PositionViewRead, RebuildPositionRequest
from app.services.positions import PositionService

router = APIRouter(prefix="/positions", tags=["positions"])


@router.post("/fills", response_model=FillRead)
async def ingest_fill(
    payload: FillCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader")),
) -> Fill:
    repo = PositionRepository(session)
    service = PositionService(repo, EventRepository(session))
    fill = Fill(**payload.model_dump(), strategy_id=payload.strategy_id or "", ts_ingest=datetime.now(timezone.utc))
    try:
        return await service.ingest_fill(fill)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="duplicate fill for (source, account_id, fill_id)") from exc


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild_positions(
    payload: RebuildPositionRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader")),
) -> RebuildResponse:
    repo = PositionRepository(session)
    service = PositionService(repo)
    views = await service.rebuild_positions(
        account_id=payload.account_id,
        instrument_id=payload.instrument_id,
        strategy_id=payload.strategy_id,
        cost_method=payload.cost_method,
    )
    return RebuildResponse(
        message="positions rebuilt",
        account_id=payload.account_id,
        instrument_id=payload.instrument_id,
        cost_method=payload.cost_method,
        updated=len(views),
    )


@router.get("", response_model=list[PositionViewRead])
async def list_positions(
    account_id: str = Query(...),
    cost_method: str = Query(default="AVG_COST"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = PositionRepository(session)
    return await repo.list_position_views(account_id=account_id, cost_method=cost_method)
