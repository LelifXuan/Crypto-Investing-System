from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.db.models.market import MarketEvent
from app.repositories.market_repository import MarketRepository
from app.schemas.market import MarketEventCreate, MarketEventRead, MarketEventSyncResponse
from app.services.market import MarketService
from app.services.market_events import MarketEventIngestionService

router = APIRouter(prefix="/market-events", tags=["market-events"])


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


@router.post("/sync", response_model=MarketEventSyncResponse)
async def sync_market_events(
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = MarketEventIngestionService(MarketRepository(session))
    return await service.sync(limit=limit)


@router.get("", response_model=list[MarketEventRead])
async def list_market_events(
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> list[MarketEvent]:
    repo = MarketRepository(session)
    return await repo.list_market_events(limit=limit)
