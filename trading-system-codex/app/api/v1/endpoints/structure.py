from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.schemas.structure import (
    SUPPORTED_STRUCTURE_TIMEFRAMES,
    StructureAlertRead,
    StructureDiagnosticsRead,
    StructureEventRead,
    StructureRefreshResponse,
    StructureTabBundleRead,
    StructureTabSnapshotRead,
)
from app.services.precompute import precompute_service
from app.services.structure import StructureSnapshotService

router = APIRouter(prefix="/structure/tab", tags=["structure"])


def _validate_timeframe(timeframe: str) -> str:
    if timeframe not in SUPPORTED_STRUCTURE_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"unsupported timeframe: {timeframe}")
    return timeframe


@router.get("/snapshot", response_model=StructureTabSnapshotRead)
async def get_structure_snapshot(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    include_geometry: bool = Query(default=True),
    include_diagnostics: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = StructureSnapshotService(MarketRepository(session))
    try:
        return await service.get_snapshot(
            instrument_id,
            _validate_timeframe(timeframe),
            include_geometry=include_geometry,
            include_diagnostics=include_diagnostics,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bundle", response_model=StructureTabBundleRead)
async def get_structure_bundle(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    include_geometry: bool = Query(default=True),
    candles_limit: int = Query(default=220, ge=50, le=400),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = StructureSnapshotService(MarketRepository(session))
    validated_timeframe = _validate_timeframe(timeframe)
    bundle = await service.get_bundle(
        instrument_id,
        validated_timeframe,
        include_geometry=include_geometry,
        candles_limit=candles_limit,
    )
    if bundle.cache_state in {"missing", "stale"}:
        await precompute_service.enqueue_hint(
            PrecomputeHintRequest(
                current_page="market-structure",
                instrument_id=instrument_id,
                timeframe=validated_timeframe,
                reason="structure_bundle_read",
                priority=4,
            )
        )
        if bundle.cache_state == "missing":
            bundle.status_message = "暂无快照，已加入预计算队列"
        elif bundle.cache_state == "stale":
            bundle.status_message = "快照可用，但可能略滞后"
    return bundle


@router.get("/events", response_model=list[StructureEventRead])
async def get_structure_events(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=80, le=200),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = StructureSnapshotService(MarketRepository(session))
    return await service.list_events(instrument_id, _validate_timeframe(timeframe), limit=limit)


@router.get("/alerts", response_model=list[StructureAlertRead])
async def get_structure_alerts(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=80, le=200),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = StructureSnapshotService(MarketRepository(session))
    return await service.list_alerts(instrument_id, _validate_timeframe(timeframe), limit=limit)


@router.get("/diagnostics", response_model=StructureDiagnosticsRead)
async def get_structure_diagnostics(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = StructureSnapshotService(MarketRepository(session))
    return await service.get_diagnostics(instrument_id, _validate_timeframe(timeframe))


@router.post("/refresh", response_model=StructureRefreshResponse)
async def refresh_structure_snapshot(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = StructureSnapshotService(MarketRepository(session))
    validated_timeframe = _validate_timeframe(timeframe)
    response = await service.refresh_response(instrument_id, validated_timeframe)
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-structure",
            instrument_id=instrument_id,
            timeframe=validated_timeframe,
            reason="structure_refresh",
            priority=2,
        )
    )
    return response
