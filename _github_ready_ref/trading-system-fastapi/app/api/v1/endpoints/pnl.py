from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.db.models.pnl import CashMovement, FXRate, FundingEvent
from app.repositories.event_repository import EventRepository
from app.repositories.pnl_repository import PnLRepository
from app.schemas.pnl import (
    CashMovementCreate,
    CashMovementRead,
    FXRateCreate,
    FXRateRead,
    FundingEventCreate,
    FundingEventRead,
    PnLSnapshotRead,
    RecomputePnLRequest,
)
from app.services.eventing import EventPublisher
from app.services.pnl import PnLService

router = APIRouter(prefix="/pnl", tags=["pnl"])


@router.post("/recompute", response_model=PnLSnapshotRead)
async def recompute_pnl(
    payload: RecomputePnLRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader")),
):
    service = PnLService(PnLRepository(session))
    return await service.recompute(
        account_id=payload.account_id,
        strategy_id=payload.strategy_id,
        cost_method=payload.cost_method,
        base_currency=payload.base_currency,
        formula_version=payload.formula_version,
    )


@router.post("/cash-movements", response_model=CashMovementRead)
async def create_cash_movement(
    payload: CashMovementCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader")),
) -> CashMovement:
    service = PnLService(PnLRepository(session))
    movement = await service.record_cash_movement(CashMovement(**payload.model_dump()))
    publisher = EventPublisher(EventRepository(session))
    await publisher.publish(
        event_type="finance.cash.recorded",
        source="pnl",
        partition_key=movement.account_id,
        payload={
            "account_id": movement.account_id,
            "strategy_id": movement.strategy_id,
            "movement_id": movement.movement_id,
            "cost_method": "AVG_COST",
        },
        idempotency_key=f"cash:{movement.account_id}:{movement.movement_id}",
    )
    return movement


@router.get("/cash-movements", response_model=list[CashMovementRead])
async def list_cash_movements(
    account_id: str = Query(...),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = PnLRepository(session)
    return await repo.list_cash_movement_reads(account_id=account_id, limit=limit)


@router.post("/funding-events", response_model=FundingEventRead)
async def create_funding_event(
    payload: FundingEventCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader")),
) -> FundingEvent:
    service = PnLService(PnLRepository(session))
    event = await service.record_funding_event(FundingEvent(**payload.model_dump()))
    publisher = EventPublisher(EventRepository(session))
    await publisher.publish(
        event_type="finance.funding.recorded",
        source="pnl",
        partition_key=event.account_id,
        payload={
            "account_id": event.account_id,
            "strategy_id": event.strategy_id,
            "funding_id": event.funding_id,
            "cost_method": "AVG_COST",
        },
        idempotency_key=f"funding:{event.account_id}:{event.funding_id}",
    )
    return event


@router.get("/funding-events", response_model=list[FundingEventRead])
async def list_funding_events(
    account_id: str = Query(...),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = PnLRepository(session)
    return await repo.list_funding_event_reads(account_id=account_id, limit=limit)


@router.post("/fx-rates", response_model=FXRateRead)
async def create_fx_rate(
    payload: FXRateCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> FXRate:
    service = PnLService(PnLRepository(session))
    rate = await service.record_fx_rate(FXRate(**payload.model_dump()))
    publisher = EventPublisher(EventRepository(session))
    await publisher.publish(
        event_type="market.fx_rate.updated",
        source="pnl",
        partition_key=f"{rate.base_currency}/{rate.quote_currency}",
        payload={
            "base_currency": rate.base_currency,
            "quote_currency": rate.quote_currency,
            "source": rate.source,
            "cost_method": "AVG_COST",
        },
        idempotency_key=f"fx:{rate.base_currency}:{rate.quote_currency}:{rate.source}:{rate.ts_event.isoformat()}",
    )
    return rate


@router.get("/fx-rates/latest", response_model=FXRateRead | None)
async def get_latest_fx_rate(
    base_currency: str = Query(...),
    quote_currency: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> FXRate | None:
    repo = PnLRepository(session)
    return await repo.latest_fx_rate(base_currency=base_currency, quote_currency=quote_currency)


@router.get("/snapshots", response_model=list[PnLSnapshotRead])
async def list_pnl_snapshots(
    account_id: str = Query(...),
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = PnLRepository(session)
    return await repo.list_snapshots(account_id=account_id, limit=limit)


@router.get("/latest", response_model=PnLSnapshotRead | None)
async def get_latest_pnl(
    account_id: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repo = PnLRepository(session)
    return await repo.latest_snapshot(account_id=account_id)
