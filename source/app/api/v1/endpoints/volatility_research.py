from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentUser,
    get_db_session,
    get_db_writer_session,
    require_roles,
)
from app.db.models.market import VolatilityResearchSnapshot
from app.repositories.market_repository import MarketRepository
from app.schemas.volatility_research import (
    VolatilityFeatureRead,
    VolatilityResearchSnapshotRead,
)
from app.services.volatility_research import VolatilityResearchService

router = APIRouter(prefix="/volatility-research", tags=["volatility-research"])


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


async def _response(
    repository: MarketRepository, snapshot: VolatilityResearchSnapshot
) -> VolatilityResearchSnapshotRead:
    rows = await repository.list_volatility_feature_observations(snapshot.snapshot_id)
    return VolatilityResearchSnapshotRead(
        snapshot_id=snapshot.snapshot_id,
        instrument_id=snapshot.instrument_id,
        timeframe=snapshot.timeframe,
        event_time=snapshot.event_time,
        available_at=snapshot.available_at,
        calculated_at=snapshot.calculated_at,
        formula_version=snapshot.formula_version,
        integration_status=snapshot.integration_status,
        price_volatility=snapshot.price_volatility_json,
        options_expectations=snapshot.options_expectations_json,
        tail_pricing=snapshot.tail_pricing_json,
        leverage_crowding=snapshot.leverage_crowding_json,
        liquidation_pressure=snapshot.liquidation_pressure_json,
        basis_funding_structure=snapshot.basis_funding_structure_json,
        quality=snapshot.quality_json,
        timestamp_contract=snapshot.timestamp_contract_json,
        features=[
            VolatilityFeatureRead(
                feature_key=row.feature_key,
                value=_decimal_text(row.value_num),
                unit=row.unit,
                quality_status=row.quality_status,
                missing_reason=row.missing_reason,
                parameters=row.parameters_json,
            )
            for row in rows
        ],
    )


@router.get("/latest", response_model=VolatilityResearchSnapshotRead)
async def latest_volatility_research_snapshot(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> VolatilityResearchSnapshotRead:
    repository = MarketRepository(session)
    snapshot = await VolatilityResearchService(repository).latest_snapshot(
        instrument_id, timeframe
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "data_insufficient", "message": "No published shadow snapshot"},
        )
    return await _response(repository, snapshot)


@router.post("/snapshots", response_model=VolatilityResearchSnapshotRead)
async def calculate_volatility_research_snapshot(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    candle_limit: int = Query(default=1200, ge=120, le=5000),
    session: AsyncSession = Depends(get_db_writer_session),
    _: CurrentUser = Depends(require_roles("admin", "analyst")),
) -> VolatilityResearchSnapshotRead:
    repository = MarketRepository(session)
    try:
        snapshot = await VolatilityResearchService(repository).build_shadow_snapshot(
            instrument_id, timeframe, candle_limit=candle_limit
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "data_insufficient", "message": str(exc)},
        ) from exc
    return await _response(repository, snapshot)
