from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest, PrecomputeHintResponse
from app.schemas.strategy import (
    StrategyBundleRead,
    StrategyReviewRead,
    StrategySignalSaveRead,
    StrategySnapshotRequest,
    StrategySnapshotSaveRead,
)
from app.schemas.strategy_unified import StrategyUnifiedRead
from app.services.precompute import precompute_service
from app.services.strategy_signal.review_engine import ReviewEngine
from app.services.strategy_signal.service import StrategySignalService, StrategySignalUnavailable
from app.services.strategy_unified.unified_service import UnifiedStrategyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])


def _instrument(value: str) -> str:
    return normalize_instrument_id(value)


def _timeframe(value: str) -> str:
    return normalize_timeframe_for_cache(value)


@router.get("/bundle", response_model=StrategyBundleRead)
async def get_strategy_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await StrategySignalService(MarketRepository(session)).get_bundle(
        _instrument(instrument_id),
        _timeframe(timeframe),
    )


@router.get("/decision")
async def get_strategy_decision(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    bundle = await StrategySignalService(MarketRepository(session)).get_bundle(
        _instrument(instrument_id),
        _timeframe(timeframe),
    )
    return bundle["decision"]


def _degraded_payload(instrument_id: str, reason: str) -> dict[str, object]:
    """Minimal payload returned when the unified strategy service fails entirely."""
    return {
        "instrument_id": instrument_id,
        "generated_at": None,
        "status": "degraded",
        "degraded": True,
        "degraded_components": [reason],
        "prewarm_status": "idle",
        "refresh_state": "degraded",
        "refresh_limitations": [f"service raised: {reason}"],
        "unified_state": {
            "code": "DATA_DEGRADED",
            "label": "数据质量不足",
            "instruction": "统一策略服务暂时不可用，已自动触发后台预热，请稍候刷新。",
            "permission": "observe",
            "risk_level": "high",
            "current_price": None,
        },
        "horizon_views": {},
        "horizon_governance": {
            "position_cap": "0%",
            "allowed_sides": [],
            "higher_timeframe_constraint": {
                "direction": "NEUTRAL",
                "rule": "上游数据缺失",
                "source_timeframes": [],
            },
            "lower_timeframe_driver": {
                "direction": "NEUTRAL",
                "rule": "上游数据缺失",
                "source_timeframes": [],
            },
            "upgrade_path": [],
            "invalidation_path": [],
        },
        "market_operation": {"chain": {}, "summary": ""},
        "timeframe_stack": [],
        "trade_plans": [],
        "risk_alerts": [
            {
                "label": "统一策略服务异常",
                "category": "service_failure",
                "severity": "warning",
                "evidence": [reason],
            }
        ],
        "risk_groups": {},
        "monitoring_focus": [],
        "event_watch": [],
        "evidence_trace": [],
        "narrative": {"headline": "", "layers": [], "watchlist": [], "action": ""},
        "snapshot_key": None,
        "payload_hash": None,
    }


@router.get("/unified", response_model=StrategyUnifiedRead)
async def get_unified_strategy(
    instrument_id: str = Query(default="btc-usdt-perp"),
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    try:
        payload = await UnifiedStrategyService(MarketRepository(session)).build_unified_strategy(
            _instrument(instrument_id),
            force=force,
        )
        return payload
    except Exception as exc:
        logger.warning("strategy_unified_service_failed: %s", exc, exc_info=True)
        return _degraded_payload(_instrument(instrument_id), reason=f"{type(exc).__name__}: {exc}")


@router.post("/refresh", response_model=PrecomputeHintResponse)
async def refresh_strategy_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    del session
    return await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id=_instrument(instrument_id),
            timeframe=_timeframe(timeframe),
            reason="manual_strategy_refresh",
            visible=True,
            candidates=["strategy"],
            priority=1,
        )
    )


@router.post("/prewarm")
async def prewarm_strategy_dependencies(
    instrument_id: str = Query(default="btc-usdt-perp"),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    """Fire-and-forget background refresh of monitoring/derivatives/macro.

    Called by the SPA on mount when the strategy payload is missing or
    degraded. Returns immediately; actual work happens in the background
    worker via precompute_service.enqueue_hint().
    """
    precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id=_instrument(instrument_id),
            timeframe="1d",
            reason="strategy_cold_start",
            visible=False,
            candidates=["monitoring", "btc-derivatives", "macro-overview"],
            priority=2,
        )
    )
    return {"status": "enqueued", "eta_seconds": 30}


@router.post("/signals", response_model=StrategySignalSaveRead)
async def save_strategy_signal(
    payload: StrategySnapshotRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    try:
        return await StrategySignalService(MarketRepository(session)).save_signal(
            _instrument(payload.instrument_id),
            _timeframe(payload.timeframe),
        )
    except StrategySignalUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/decision/snapshot", response_model=StrategySnapshotSaveRead)
async def save_strategy_decision_snapshot(
    payload: StrategySnapshotRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    try:
        saved = await StrategySignalService(MarketRepository(session)).save_signal(
            _instrument(payload.instrument_id),
            _timeframe(payload.timeframe),
        )
    except StrategySignalUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "decision_id": saved["signal_key"],
        "input_hash": saved["input_hash"],
        "model_version": saved["model_version"],
        "config_version": saved["config_version"],
        "payload": saved["payload"],
    }


@router.get("/review", response_model=StrategyReviewRead)
async def get_strategy_review(
    instrument_id: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await ReviewEngine(MarketRepository(session)).build_review(
        _instrument(instrument_id) if instrument_id else None,
        _timeframe(timeframe) if timeframe else None,
    )
