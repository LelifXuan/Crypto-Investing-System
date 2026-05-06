from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.repositories.pnl_repository import PnLRepository
from app.schemas.reviews import ReviewRead
from app.services.reviews import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/performance", response_model=ReviewRead)
async def review_performance(
    account_id: str = Query(...),
    limit: int = Query(default=200, le=2000),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> ReviewRead:
    service = ReviewService(PnLRepository(session))
    return await service.review(account_id=account_id, limit=limit)
