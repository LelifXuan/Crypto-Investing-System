from __future__ import annotations

import logging
from datetime import datetime, timezone

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
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    cache_status,
    expires_at_for_page,
    strategy_unified_cache_key,
)
from app.services.market import MarketService
from app.services.precompute import precompute_service
from app.services.strategy_signal.review_engine import ReviewEngine
from app.services.strategy_signal.service import StrategySignalService, StrategySignalUnavailable
from app.services.strategy_unified.shadow_validation import ShadowValidationService
from app.services.strategy_unified.trade_decision import reconcile_cached_strategy
from app.services.strategy_unified.unified_service import UnifiedStrategyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])


def _instrument(value: str) -> str:
    return normalize_instrument_id(value)


def _timeframe(value: str) -> str:
    return normalize_timeframe_for_cache(value)


def _block_cached_strategy_for_price(
    payload: dict[str, object], *, status: str, message: str
) -> dict[str, object]:
    payload["price_freshness"] = status.lower()
    payload["recompute_status"] = "enqueued"
    state = payload.setdefault("unified_state", {})
    if isinstance(state, dict):
        state.update(
            {
                "permission": "no_trade",
                "position_cap": "no_trade",
                "instruction": message,
            }
        )
    decision = payload.get("trade_decision")
    if isinstance(decision, dict):
        decision.update(
            {
                "status": status,
                "permission": "no_trade",
                "order_type": "NONE",
                "order_status": status,
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "levels_active": False,
                "primary_reason": {"code": status, "message": message},
            }
        )
    for plan in payload.get("trade_plans") or []:
        if not isinstance(plan, dict):
            continue
        plan.update(
            {
                "permission": "no_trade",
                "order_type": "NONE",
                "order_status": status,
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "levels_active": False,
            }
        )
    return payload


async def _guard_cached_strategy(
    repository: MarketRepository,
    instrument_id: str,
    payload: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """Reconcile an otherwise valid page cache with the freshest mark price."""
    try:
        mark = await MarketService(repository).get_best_mark(instrument_id, prefer_live=True)
    except Exception as exc:
        logger.warning("strategy_price_guard_unavailable: %s", exc)
        return (
            _block_cached_strategy_for_price(
                payload,
                status="PRICE_UNAVAILABLE",
                message="无法取得实时价格，旧策略已暂停执行并等待重新推演。",
            ),
            False,
        )
    if mark is None:
        return (
            _block_cached_strategy_for_price(
                payload,
                status="PRICE_UNAVAILABLE",
                message="实时价格不可用，旧策略已暂停执行并等待重新推演。",
            ),
            False,
        )
    ts = mark.ts_event
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_seconds = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    if age_seconds > 60:
        payload["price_as_of"] = ts.isoformat()
        payload["price_source"] = str(mark.source or "market_mark")
        payload["price_age_seconds"] = age_seconds
        return (
            _block_cached_strategy_for_price(
                payload,
                status="PRICE_STALE",
                message="实时价格超过 60 秒未更新，暂停执行并等待重新推演。",
            ),
            False,
        )
    guarded, invalidated = reconcile_cached_strategy(
        payload,
        latest_price=mark.mark_price,
        price_as_of=ts.isoformat(),
        price_source=str(mark.source or "market_mark"),
    )
    guarded["price_freshness"] = "fresh"
    guarded["price_age_seconds"] = age_seconds
    return guarded, invalidated


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
    normalized_instrument = _instrument(instrument_id)
    repository = MarketRepository(session)
    cache_key = strategy_unified_cache_key(normalized_instrument)
    if not force:
        cache = await repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        if cache is not None and cache.payload_json and status not in {"missing", "error"}:
            payload = dict(cache.payload_json)
            payload.setdefault("instrument_id", normalized_instrument)
            payload["cache_state"] = status
            payload["refresh_state"] = payload.get("refresh_state") or "cache_only"
            payload["prewarm_status"] = "ready" if status == "fresh" else "enqueued"
            payload, price_invalidated = await _guard_cached_strategy(
                repository, normalized_instrument, payload
            )
            if (
                status != "fresh"
                or price_invalidated
                or payload.get("price_freshness") in {"stale", "price_stale", "price_unavailable"}
            ):
                await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page="strategy",
                        instrument_id=normalized_instrument,
                        timeframe="1d",
                        reason=(
                            "strategy_unified_price_invalidated"
                            if price_invalidated
                            else "strategy_unified_stale_read"
                        ),
                        visible=False,
                        candidates=[
                            "strategy_unified",
                            "strategy",
                            "market_context",
                            "monitoring",
                            "macro",
                            "btc_derivatives",
                        ],
                        priority=1 if price_invalidated else 3,
                    )
                )
            return payload
        response = await precompute_service.enqueue_hint(
            PrecomputeHintRequest(
                current_page="strategy",
                instrument_id=normalized_instrument,
                timeframe="1d",
                reason="strategy_unified_cold_read",
                visible=False,
                candidates=[
                    "strategy_unified",
                    "strategy",
                    "market_context",
                    "monitoring",
                    "macro",
                    "btc_derivatives",
                ],
                priority=2,
            )
        )
        payload = _degraded_payload(normalized_instrument, reason="strategy_unified_cache_missing")
        payload["prewarm_status"] = "enqueued" if response.status != "disabled" else "disabled"
        payload["refresh_state"] = "missing"
        payload["refresh_limitations"] = [
            "Unified strategy snapshot is missing; background prewarm has been queued."
        ]
        return payload
    try:
        payload = await UnifiedStrategyService(repository).build_unified_strategy(
            normalized_instrument,
            force=force,
        )
        # A forced rebuild is still not executable until it passes the same live
        # mark-price guard as a cached response.  This closes the refresh-path gap
        # where a newly calculated strategy could be returned with a stale mark.
        payload, price_invalidated = await _guard_cached_strategy(
            repository, normalized_instrument, payload
        )
        if price_invalidated or payload.get("price_freshness") in {
            "stale",
            "price_stale",
            "price_unavailable",
        }:
            await precompute_service.enqueue_hint(
                PrecomputeHintRequest(
                    current_page="strategy",
                    instrument_id=normalized_instrument,
                    timeframe="1d",
                    reason=(
                        "strategy_unified_price_invalidated"
                        if price_invalidated
                        else "strategy_unified_price_guard_failed"
                    ),
                    visible=False,
                    candidates=["strategy_unified", "market_context"],
                    priority=1,
                )
            )
        now = datetime.now(timezone.utc)
        await repository.upsert_page_snapshot_cache(
            cache_key=cache_key,
            page_type="strategy_unified",
            instrument_id=normalized_instrument,
            payload_json=payload,
            status="ready",
            cache_state="fresh" if payload.get("status") != "degraded" else "stale",
            snapshot_at=now,
            data_ts=now,
            expires_at=expires_at_for_page("strategy_unified", now),
            source_updated_at=now,
            source_version=CACHE_SOURCE_VERSION,
            meta_json={"force": force},
        )
        return payload
    except Exception as exc:
        logger.warning("strategy_unified_service_failed: %s", exc, exc_info=True)
        return _degraded_payload(normalized_instrument, reason=f"{type(exc).__name__}: {exc}")


@router.get("/shadow-validation")
async def get_shadow_validation(
    instrument_id: str = Query(default="btc-usdt-perp"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await ShadowValidationService(MarketRepository(session)).build_report(
        _instrument(instrument_id),
        update_outcomes=False,
    )


@router.post("/shadow-validation/refresh")
async def refresh_shadow_validation(
    instrument_id: str = Query(default="btc-usdt-perp"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    return await ShadowValidationService(MarketRepository(session)).build_report(
        _instrument(instrument_id),
        update_outcomes=True,
    )


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
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id=_instrument(instrument_id),
            timeframe="1d",
            reason="strategy_cold_start",
            visible=False,
            candidates=[
                "strategy_unified",
                "strategy",
                "market_context",
                "monitoring",
                "macro",
                "btc_derivatives",
            ],
            priority=2,
        )
    )
    return {
        "status": response.status,
        "accepted": response.accepted,
        "queued": response.queued,
        "deduped": response.deduped,
        "eta_seconds": 30,
        "queued_keys": response.queued_keys,
    }


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
