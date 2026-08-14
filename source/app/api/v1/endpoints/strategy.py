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
            if (
                cached_payload_status == "degraded"
                and status not in {"missing", "error", "warming", "stale"}
            ):
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
            and (cache.payload_json or {}).get("status") == "degraded"
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


@router.get("/scan")
async def get_strategy_scan(
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    """Scan all configured instruments × core timeframes for opportunities.

    Cold-load reliability (2026-07-24):
    - On a cold cache + force=false, do NOT block the request for the
      ~60+ s it takes to rebuild every cell's unified strategy. Instead,
      enqueue a prewarm and return a fast `warming` response.
    - Wrap every operation in try/except so any unhandled error degrades
      to HTTP 200 with cache_meta.source="error" rather than a 5xx that
      the frontend flattens into the "扫描失败" banner.

    Bounded warming (2026-08-07): a warming cache row is authoritative
    only for its 10s short-circuit window. After that the endpoint treats
    it as missing and runs one cache-only scan (returns a real matrix in
    ~2-3 s on a warm DB) instead of returning the empty warming payload
    forever. force=true rebuilds every cell from source data.
    """
    from app.schemas.market import PrecomputeHintRequest
    from app.services.strategy_unified.opportunity_scanner import (
        SCAN_TIMEFRAMES,
        OpportunityScanner,
    )

    repository = MarketRepository(session)
    cache_key = strategy_scan_cache_key()
    now = datetime.now(timezone.utc)

    # Cache-first
    if not force:
        try:
            cache = await repository.get_page_snapshot_cache(cache_key)
        except Exception:
            logger.exception("strategy/scan cache lookup failed")
            cache = None
        status = cache_status(cache) if cache else "missing"
        # A warming cache row is only authoritative while its short-circuit
        # window is open (10s). Once it expires, treat it as missing so the
        # cold-load branch below produces a real matrix instead of returning
        # the warming payload forever — the pre-2026-08-07 behaviour looped
        # the frontend's warming poll with an empty matrix indefinitely.
        if cache is not None and (cache.cache_state or cache.status) in {
            "warming",
            "updating",
            "refreshing",
        }:
            expires_at = getattr(cache, "expires_at", None)
            if expires_at is not None and expires_at <= now:
                status = "missing"
        if cache is not None and cache.payload_json and status not in {"missing", "error"}:
            payload = dict(cache.payload_json)
            payload.setdefault("cache_meta", {})
            # 2026-07-24 v2: preserve the warming signal so the
            # frontend's poll loop keeps the warming banner up.
            # Otherwise the empty matrix would be misinterpreted as
            # "no opportunities found" on the very first request
            # after the warming short-circuit fires.
            if payload["cache_meta"].get("source") != "warming":
                payload["cache_meta"]["source"] = "cache"
            return payload

    # Cold-load short-circuit: kick off the background prewarm (so fresher
    # cells arrive), then run ONE cache-only scan immediately. scan_all
    # reads every cell from its bundle cache — on a warm DB that returns a
    # real matrix in ~2-3 s, which is far better than an infinite warming
    # banner. If the scan fails for any reason, fall back to the warming
    # response so the frontend's poll loop keeps its banner up.
    if not force:
        try:
            await precompute_service.enqueue_hint(
                PrecomputeHintRequest(
                    current_page="strategy",
                    instrument_id="btc-usdt-perp",
                    timeframe="1d",
                    reason="strategy_scan_cold",
                    visible=False,
                    candidates=[
                        "strategy_unified",
                        "monitoring",
                        "macro",
                        "btc_derivatives",
                    ],
                    priority=3,
                )
            )
        except Exception:
            logger.exception("strategy/scan prewarm enqueue failed")

        try:
            instruments = await repository.list_instruments()
            instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
            instrument_codes = {}
            for i in instruments:
                code = (
                    getattr(i, "base_ccy", None)
                    or getattr(i, "symbol", None)
                    or i.instrument_id
                )
                instrument_codes[i.instrument_id] = code

            scanner = OpportunityScanner(repository)
            result = await scanner.scan_all(instrument_ids, instrument_codes)

            import dataclasses
            result_dict = dataclasses.asdict(result)
            result_dict["cache_meta"] = dict(result_dict.get("cache_meta") or {})
            result_dict["cache_meta"]["message"] = (
                "基于当前缓存生成；后台正在补齐最新数据，可稍后手动刷新。"
            )
            try:
                await repository.upsert_page_snapshot_cache(
                    cache_key=cache_key,
                    page_type="strategy_scan",
                    payload_json=result_dict,
                    status="ready",
                    cache_state="fresh",
                    snapshot_at=now,
                    data_ts=now,
                    expires_at=expires_at_for_scan(now),
                    source_version=CACHE_SOURCE_VERSION,
                )
            except Exception:
                logger.exception("strategy/scan cold cache write failed")
            return result_dict
        except Exception:
            logger.exception(
                "strategy/scan cold scan failed; falling back to warming"
            )

        warming_payload = {
            "scanned_at": now.isoformat(),
            "instruments": [],
            "timeframes": list(SCAN_TIMEFRAMES),
            "matrix": [],
            "ranked": [],
            "cache_meta": {
                "fresh_until": now.isoformat(),
                "source": "warming",
                "instruments_scanned": 0,
                "opportunities_found": 0,
                "message": "首次访问，正在后台预热数据缓存，预计 5-10 秒后自动出结果。",
            },
        }
        try:
            from datetime import timedelta
            await repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="strategy_scan",
                payload_json=warming_payload,
                status="warming",
                cache_state="warming",
                snapshot_at=now,
                data_ts=now,
                expires_at=now + timedelta(seconds=10),
                source_version=CACHE_SOURCE_VERSION,
            )
        except Exception:
            logger.exception("strategy/scan warming cache write failed")
        return warming_payload

    # force=true: do the full scan, but never let an exception escape
    # as an HTTP 5xx.
    try:
        instruments = await repository.list_instruments()
        instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
        instrument_codes = {}
        for i in instruments:
            code = (
                getattr(i, "base_ccy", None)
                or getattr(i, "symbol", None)
                or i.instrument_id
            )
            instrument_codes[i.instrument_id] = code

        scanner = OpportunityScanner(repository)
        result = await scanner.scan_all(instrument_ids, instrument_codes, force=force)

        import dataclasses
        result_dict = dataclasses.asdict(result)
    except Exception:
        logger.exception("strategy/scan forced execution failed")
        return {
            "scanned_at": now.isoformat(),
            "instruments": [],
            "timeframes": [],
            "matrix": [],
            "ranked": [],
            "cache_meta": {
                "fresh_until": now.isoformat(),
                "source": "error",
                "instruments_scanned": 0,
                "opportunities_found": 0,
                "message": "扫描服务暂时不可用，请稍后重试。",
            },
        }

    try:
        await repository.upsert_page_snapshot_cache(
            cache_key=cache_key,
            page_type="strategy_scan",
            payload_json=result_dict,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=now,
            expires_at=expires_at_for_scan(now),
            source_version=CACHE_SOURCE_VERSION,
        )
    except Exception:
        logger.exception("strategy/scan cache write failed; returning fresh result anyway")

    return result_dict
