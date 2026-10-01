from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentUser,
    get_db_session,
    get_db_writer_session,
    require_roles,
)
from app.core.db import db_manager
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
    expires_at_for_scan,
    strategy_scan_cache_key,
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
    opportunities = payload.get("opportunity_decisions")
    if isinstance(opportunities, dict):
        for opportunity in opportunities.values():
            if not isinstance(opportunity, dict):
                continue
            opportunity.update(
                {
                    "status": status,
                    "permission": "observe",
                    "order_type": "NONE",
                    "order_status": status,
                    "levels_active": False,
                    "entry_zone": [],
                    "invalidation_price": None,
                    "take_profit_1": None,
                    "horizon_target": None,
                    "expected_move_pct": None,
                    "stop_distance_pct": None,
                    "first_risk_reward": None,
                    "risk_reward": {"value": None, "passed": False},
                    "recommended_leverage": 0,
                    "planned_leverage": 0,
                    "max_leverage": 0,
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
    """Read one validated decision bundle.

    Poisoned-row guard (2026-09-23): ``strategy_bundle:*`` rows written
    before the snapshot/bundle key split carry the raw *snapshot* under
    ``decision`` (no ``strategy_state``) and fail ``StrategyBundleRead``
    validation with 15 errors → HTTP 500. If the cached row is not a
    decision, rebuild synchronously instead of serving it: the rebuild
    path (refresh_bundle → build_bundle_uncached) always produces a
    validated decision and overwrites the bad row.
    """
    service = StrategySignalService(MarketRepository(session))
    bundle = await service.get_bundle(
        _instrument(instrument_id),
        _timeframe(timeframe),
    )
    if not isinstance((bundle or {}).get("decision"), dict) or not (
        bundle.get("decision") or {}
    ).get("strategy_state"):
        bundle = await service.refresh_bundle(
            _instrument(instrument_id),
            _timeframe(timeframe),
            reason="bundle_shape_guard",
        )
    return bundle


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
    session: AsyncSession = Depends(get_db_writer_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    normalized_instrument = _instrument(instrument_id)
    repository = MarketRepository(session)
    cache_key = strategy_unified_cache_key(normalized_instrument)
    if not force:
        cache = await repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        # 2026-07-25: the cache row may say "fresh" while the cached
        # payload's status is "degraded" (e.g. row was written during a
        # cold prewarm, or older rebuild races). Returning a degraded
        # payload as if it were ready means the frontend renders a panel
        # full of empty-state copies ("暂无周期证据 / 数据不足") with no
        # signal that the system is still working. We treat such rows as
        # "stale" so the read-path falls through to the cold-read branch
        # below, which enqueues a rebuild and returns a payload with
        # refresh_limitations + the proper banner-visible prewarm_status.
        if cache is not None and cache.payload_json:
            cached_payload_status = (cache.payload_json or {}).get("status")
            if not all(
                tf in ((cache.payload_json or {}).get("opportunity_decisions") or {})
                for tf in ("1w", "1d", "4h")
            ):
                status = "stale"
            if cached_payload_status == "degraded" and status not in {
                "missing",
                "error",
                "warming",
                "stale",
            }:
                logger.info(
                    "strategy_unified_cache_stale_degraded: instrument=%s, "
                    "row_state=%s, components=%s — falling through to cold read",
                    normalized_instrument,
                    status,
                    (cache.payload_json or {}).get("degraded_components"),
                )
                status = "stale"
        # A degraded payload (empty shell) is never worth serving even as
        # LKG — it carries no operation cards / evidence, so the panel
        # would render empty-state copies either way. LKG-serving applies
        # only to complete snapshots whose TTL simply lapsed. A "ready"
        # payload with partial degraded_components is still LKG-worthy
        # (the frontend banner lists the failing components).
        payload_is_degraded = bool(
            cache is not None
            and (
                (cache.payload_json or {}).get("status") == "degraded"
                or not all(
                    tf in ((cache.payload_json or {}).get("opportunity_decisions") or {})
                    for tf in ("1w", "1d", "4h")
                )
            )
        )
        if (
            cache is not None
            and cache.payload_json
            and status in {"fresh", "stale"}
            and not payload_is_degraded
        ):
            payload = dict(cache.payload_json)
            payload.setdefault("instrument_id", normalized_instrument)
            payload["cache_state"] = status
            # 2026-08-07 (AGENTS.md §九.2): an expired-but-present cache row
            # serves its last-known-good payload with a stale_revalidating
            # marker instead of falling through to an empty degraded shell.
            # The old behaviour (status in {"missing","error","stale"} →
            # cold-read) blanked the strategy detail panel every TTL period;
            # when external data sources were slow the panel stayed stuck on
            # "统一策略服务暂时不可用" even though a complete snapshot existed.
            payload["refresh_state"] = payload.get("refresh_state") or (
                "stale_revalidating" if status == "stale" else "cache_only"
            )
            payload["prewarm_status"] = "ready" if status == "fresh" else "enqueued"
            # The live-price guard's invalidation flag is deliberately dropped.
            #
            # The guard also reports an invalidation when the plan's own levels
            # have been left behind by the mark price. Those levels are
            # structural — they come from the candles, not from the current
            # price — so `build_unified_strategy` reproduces the same geometry
            # and the guard invalidates it again. Enqueueing on every read
            # therefore re-derived the same dead plan forever (a full rebuild is
            # 10-18 s per instrument) while the payload kept claiming a
            # recompute was in flight. The scheduled precompute refresh (120 s /
            # 600 s per timeframe) already re-derives on new candles, and the
            # detail drawer offers an explicit rebuild button.
            payload, _ = await _guard_cached_strategy(repository, normalized_instrument, payload)
            # Only a cache-freshness problem is worth a rebuild here.
            if status != "fresh":
                await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page="strategy",
                        instrument_id=normalized_instrument,
                        timeframe="1d",
                        reason="strategy_unified_stale_read",
                        visible=False,
                        candidates=[
                            "strategy_unified",
                            "strategy",
                            "market_context",
                            "monitoring",
                            "macro",
                            "btc_derivatives",
                        ],
                        priority=3,
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
            expires_at=expires_at_for_page("strategy_unified", now, timeframe="1d"),
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


@router.get("/scan")
async def get_strategy_scan(
    force: bool = Query(default=False),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    """Read or reproject a matrix from the same published strategies as detail."""
    import dataclasses

    from app.services.strategy_unified.opportunity_scanner import (
        OpportunityScanner,
        scan_inputs_newer_than_scan,
    )

    now = datetime.now(timezone.utc)
    cache_key = strategy_scan_cache_key()
    if force:
        # A fresh scan must never publish transient unified calculations: the
        # detail drawer reads published unified snapshots. Otherwise clicking
        # refresh can make the matrix disagree with the drawer immediately.
        try:
            async with db_manager.session() as session:
                repository = MarketRepository(session)
                instruments = await repository.list_instruments()
                instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
                instrument_codes = {
                    i.instrument_id: getattr(i, "base_ccy", None)
                    or getattr(i, "symbol", None)
                    or i.instrument_id
                    for i in instruments
                    if i.instrument_id
                }
                result = await OpportunityScanner(repository).scan_published(
                    instrument_ids, instrument_codes
                )
            payload = dataclasses.asdict(result)
            published_at = datetime.now(timezone.utc)
            expiry = expires_at_for_scan(published_at)
            payload["cache_meta"]["fresh_until"] = expiry.isoformat()
            async with db_manager.writer_session() as session:
                repository = MarketRepository(session)
                await repository.upsert_page_snapshot_cache(
                    cache_key=cache_key,
                    page_type="strategy_scan",
                    payload_json=payload,
                    status="ready",
                    cache_state="fresh",
                    snapshot_at=published_at,
                    data_ts=published_at,
                    expires_at=expiry,
                    source_version=CACHE_SOURCE_VERSION,
                )
            return payload
        except Exception:
            logger.exception("strategy/scan forced execution failed")
            return _scan_unavailable(now, source="error")

    stored: dict = {}
    try:
        async with db_manager.session() as session:
            repository = MarketRepository(session)
            cache = await repository.get_page_snapshot_cache(cache_key)
            stored = cache.payload_json if cache and isinstance(cache.payload_json, dict) else {}
            if stored and (stored.get("matrix") or stored.get("instruments")):
                payload = dict(stored)
                meta = dict(payload.get("cache_meta") or {})
                needs_refresh = cache_status(cache) != "fresh" or await scan_inputs_newer_than_scan(
                    repository, cache
                )
                # Pre-identity scan rows cannot be safely paired with a
                # detail drawer when unified publication changes between reads.
                needs_refresh = needs_refresh or any(
                    item.get("qualified") and not item.get("source_snapshot_key")
                    for item in payload.get("matrix", [])
                    if isinstance(item, dict)
                )
                if needs_refresh:
                    meta["source"] = "stale_revalidating"
                    meta["message"] = "后台正在更新扫描；当前展示上次发布的结果。"
                    payload["matrix"] = [
                        {**item, "cache_state": "stale", "qualified": False}
                        if item.get("cache_state") == "fresh"
                        else item
                        for item in payload.get("matrix", [])
                    ]
                    payload["ranked"] = []
                else:
                    meta["source"] = "cache"
                meta["served_at"] = now.isoformat()
                payload["cache_meta"] = meta
                return payload
    except Exception:
        logger.exception("strategy/scan published snapshot read failed")
        if stored:
            payload = dict(stored)
            payload["cache_meta"] = {
                **(payload.get("cache_meta") or {}),
                "source": "stale_revalidating",
                "message": "扫描状态暂不可核验；当前展示上次发布的结果。",
                "served_at": now.isoformat(),
            }
            payload["matrix"] = [
                {**item, "cache_state": "stale", "qualified": False}
                if item.get("cache_state") == "fresh"
                else item
                for item in payload.get("matrix", [])
            ]
            payload["ranked"] = []
            return payload
        return _scan_unavailable(now, source="error")
    return _scan_unavailable(now, source="warming")


def _scan_unavailable(now: datetime, *, source: str) -> dict:
    message = (
        "扫描快照尚未发布；后台会独立计算并自动更新。"
        if source == "warming"
        else "扫描快照暂不可用，请稍后重试。"
    )
    return {
        "scanned_at": now.isoformat(),
        "instruments": [],
        "timeframes": ["1w", "1d", "4h"],
        "matrix": [],
        "ranked": [],
        "cache_meta": {
            "fresh_until": now.isoformat(),
            "source": source,
            "instruments_scanned": 0,
            "opportunities_found": 0,
            "message": message,
        },
    }
