from __future__ import annotations

from datetime import UTC, datetime

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

router = APIRouter(prefix="/structure/tab", tags=["structure"])


def _validate_timeframe(timeframe: str) -> str:
    if timeframe not in SUPPORTED_STRUCTURE_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"unsupported timeframe: {timeframe}")
    return timeframe


def _structure_service(session: AsyncSession):
    from app.services.structure import StructureSnapshotService

    return StructureSnapshotService(MarketRepository(session))


@router.get("/snapshot", response_model=StructureTabSnapshotRead)
async def get_structure_snapshot(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    include_geometry: bool = Query(default=True),
    include_diagnostics: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = _structure_service(session)
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
    validated_timeframe = _validate_timeframe(timeframe)
    try:
        service = _structure_service(session)
    except Exception as exc:
        return StructureTabBundleRead.model_validate(
            {
                "snapshot": None,
                "candles": [],
                "events": [],
                "alerts": [],
                "diagnostics": {
                    "detector_version": "unavailable",
                    "compute_mode": "low_confidence",
                    "candles_loaded": 0,
                    "profile_precision": "none",
                    "geometry_count": 0,
                    "event_count": 0,
                    "alert_count": 0,
                    "generated_at": datetime.now(UTC),
                    "notes": [f"结构模块暂不可用：{exc}"],
                },
                "cache_state": "missing",
                "is_stale": False,
                "status_message": "暂无结构快照，已加入后台预计算队列。",
            }
        )
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
            bundle.status_message = "暂无结构快照，已加入后台预计算队列。"
        elif bundle.cache_state == "stale":
            bundle.status_message = "结构快照可能滞后，后台正在准备新数据。"
    return bundle


@router.get("/events", response_model=list[StructureEventRead])
async def get_structure_events(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=80, le=200),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = _structure_service(session)
    return await service.list_events(instrument_id, _validate_timeframe(timeframe), limit=limit)


@router.get("/alerts", response_model=list[StructureAlertRead])
async def get_structure_alerts(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=80, le=200),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = _structure_service(session)
    return await service.list_alerts(instrument_id, _validate_timeframe(timeframe), limit=limit)


@router.get("/diagnostics", response_model=StructureDiagnosticsRead)
async def get_structure_diagnostics(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    service = _structure_service(session)
    return await service.get_diagnostics(instrument_id, _validate_timeframe(timeframe))


@router.post("/refresh", response_model=StructureRefreshResponse)
async def refresh_structure_snapshot(
    instrument_id: str = Query(...),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = _structure_service(session)
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
