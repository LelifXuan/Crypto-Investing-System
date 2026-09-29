from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.config import settings
from app.repositories.market_repository import MarketRepository
from app.services.cache_registry import cache_status, strategy_unified_cache_key
from app.services.strategy_unified.unified_service import UnifiedStrategyService

logger = logging.getLogger(__name__)

SCAN_TIMEFRAMES = ("1w", "1d", "4h")


async def scan_inputs_newer_than_scan(repository: MarketRepository, scan_cache: Any | None) -> bool:
    """Compare published input times with the scan's input watermark."""
    if scan_cache is None:
        return True
    payload = getattr(scan_cache, "payload_json", None)
    scan_meta = payload.get("cache_meta") if isinstance(payload, dict) else {}
    scan_meta = scan_meta if isinstance(scan_meta, dict) else {}
    if "input_snapshot_at" in scan_meta:
        value = scan_meta["input_snapshot_at"]
        watermark = datetime.fromisoformat(value) if value else None
    else:
        watermark = getattr(scan_cache, "data_ts", None) or getattr(scan_cache, "snapshot_at", None)
    if watermark is not None and watermark.tzinfo is None:
        watermark = watermark.replace(tzinfo=timezone.utc)
    instruments = await repository.list_instruments()
    for instrument in instruments:
        iid = getattr(instrument, "instrument_id", None)
        if not iid:
            continue
        row = await repository.get_page_snapshot_cache(strategy_unified_cache_key(iid))
        input_at = getattr(row, "snapshot_at", None)
        if input_at is None:
            continue
        if input_at.tzinfo is None:
            input_at = input_at.replace(tzinfo=timezone.utc)
        if watermark is None or input_at > watermark:
            return True
    return False


# Matrix and ranked rows use the same complete execution-quality gate.
MATRIX_MIN_CONFIDENCE = 85.0
MATRIX_MIN_SCORE = 68.0
MATRIX_MIN_RISK_REWARD = 1.2
MATRIX_MIN_DIRECTION_GAP = 15.0
MATRIX_MIN_SUPPORTING_VOTES = 2


def compute_opportunity_score(
    *,
    confidence: float,
    risk_reward: float,
    direction: str,
    modules_direction_tally: dict[str, int],
    timeframe: str,
) -> float:
    """综合评分: confidence(40%) + risk_reward(25%) + consistency(20%) + timeframe(15%)."""
    if direction in ("WAIT", "NO_TRADE", "RANGE_NO_EDGE"):
        return 0.0

    c_score = confidence * 0.40

    rr_norm = min(risk_reward / 5.0, 1.0) if risk_reward > 0 else 0.0
    rr_score = rr_norm * 100 * 0.25

    total_modules = sum(modules_direction_tally.values())
    if total_modules == 0:
        consistency = 0
    else:
        max_same = max(modules_direction_tally.values())
        if max_same >= 3:
            consistency = 100
        elif max_same == 2:
            # Deadlock: both bullish and bearish have substantial votes
            if (
                modules_direction_tally.get("bullish", 0) >= 2
                and modules_direction_tally.get("bearish", 0) >= 2
            ):
                consistency = 0
            else:
                consistency = 50
        else:
            consistency = 0
    cs_score = consistency * 0.20

    tf_bonus = {"1w": 100, "1d": 70, "4h": 40, "1h": 0, "15m": 0}
    tf_score = tf_bonus.get(timeframe, 0) * 0.15

    return round(c_score + rr_score + cs_score + tf_score, 1)


@dataclass(slots=True)
class ScanItem:
    instrument_id: str
    instrument_code: str
    timeframe: str
    direction: str  # "LONG" | "SHORT" | "WAIT"
    direction_label: str  # "做多" | "做空" | "等待"
    confidence: float
    score: float
    summary: str
    risk_reward: float
    leverage_hint: str  # selected-period recommendation or pending state
    position_cap: str  # "standard" | "reduced" | "observe"
    primary_driver: str
    conflicts: list[str] = field(default_factory=list)
    # 2026-07-24 v3: per-cell cache_state + data_quality so the renderer
    # can distinguish "data ready, no edge" from "data pending".
    # Without these, "等待" / "无明确交易机会" was conflated with
    # "数据还没准备好" — user thought the system was broken.
    cache_state: str = "unknown"  # "fresh" | "missing" | "stale" | "warming" | "error" | "unknown"
    data_quality: float = 0.0  # 0-100, from payload.confidence_report.confidence_score
    qualified: bool = False
    qualification_reasons: list[str] = field(default_factory=list)
    # Execution levels are published only after the selected period passes
    # the canonical trade gate and matches the decision's execution period.
    entry_zone: list[float] = field(default_factory=list)
    stop_loss: float | None = None
    take_profit_1: float | None = None
    horizon_target: float | None = None
    first_risk_reward: float | None = None
    expected_move_pct: float | None = None


@dataclass(slots=True)
class ScanResult:
    scanned_at: str
    instruments: list[str]
    timeframes: list[str]
    matrix: list[ScanItem]
    ranked: list[ScanItem]
    cache_meta: dict[str, Any]


class OpportunityScanner:
    """Batch-scan all instruments x core timeframes for actionable opportunities."""

    def __init__(self, repository: MarketRepository) -> None:
        self._repository = repository

    async def scan_published(
        self,
        instrument_ids: list[str],
        instrument_codes: dict[str, str],
        *,
        timeframes: tuple[str, ...] = SCAN_TIMEFRAMES,
    ) -> ScanResult:
        """Project the matrix from published unified snapshots only.

        The background publisher uses this path so a scan never rebuilds
        strategies, performs network work, or writes audit facts. Missing
        inputs become pending cells rather than fabricated market conclusions.
        """
        items: list[ScanItem] = []
        latest_input_at: datetime | None = None
        for iid in instrument_ids:
            try:
                cache = await self._repository.get_page_snapshot_cache(
                    strategy_unified_cache_key(iid)
                )
            except Exception:
                logger.exception("opportunity_scanner: snapshot read failed for %s", iid)
                cache = None
            input_at = getattr(cache, "snapshot_at", None)
            if input_at is not None:
                if input_at.tzinfo is None:
                    input_at = input_at.replace(tzinfo=timezone.utc)
                latest_input_at = max(latest_input_at, input_at) if latest_input_at else input_at
            payload = cache.payload_json if cache and isinstance(cache.payload_json, dict) else {}
            source_state = cache_status(cache) if cache else "missing"
            for tf in timeframes:
                try:
                    item = _extract_scan_item(payload, iid, instrument_codes.get(iid, iid), tf)
                except (KeyError, TypeError, ValueError):
                    logger.exception("opportunity_scanner: invalid snapshot %s %s", iid, tf)
                    item = _extract_scan_item({}, iid, instrument_codes.get(iid, iid), tf)
                    source_state = "error"
                if source_state in {"missing", "error"}:
                    item.cache_state = "missing"
                    item.qualified = False
                elif source_state != "fresh" and item.cache_state == "fresh":
                    item.cache_state = "stale"
                    item.qualified = False
                    item.qualification_reasons.append("data_not_fresh")
                if not item.qualified:
                    item.direction = "WAIT"
                    item.direction_label = "无机会"
                    item.risk_reward = 0.0
                    item.leverage_hint = "仅观察"
                    item.entry_zone, item.stop_loss, item.take_profit_1 = [], None, None
                    item.horizon_target = None
                    item.first_risk_reward = None
                    item.expected_move_pct = None
                items.append(item)
        result = self._result(items, instrument_ids, timeframes, source="published_snapshots")
        result.cache_meta["input_snapshot_at"] = (
            latest_input_at.isoformat() if latest_input_at else None
        )
        return result

    async def scan_all(
        self,
        instrument_ids: list[str],
        instrument_codes: dict[str, str],
        *,
        timeframes: tuple[str, ...] = SCAN_TIMEFRAMES,
        force: bool = False,
    ) -> ScanResult:
        """Scan each instrument once, then derive independent timeframe cells.

        ``force=False`` reads each cell from cache (fast — ~2-3 s for the full
        universe on a warm DB); ``force=True`` rebuilds every cell from source
        data and is only triggered by the user's explicit refresh.

        ``UnifiedStrategyService`` already returns the complete timeframe
        stack.  Rebuilding it once per matrix cell produced three identical
        confidence values and tripled scan work.  The scanner therefore keeps
        the SQLite-safe serial instrument boundary, but extracts 1w/1d/4h from
        the single published payload for that instrument.
        """
        items: list[ScanItem] = []

        for iid in instrument_ids:
            code = instrument_codes.get(iid, iid)
            try:
                payload = await asyncio.wait_for(
                    UnifiedStrategyService(self._repository).build_unified_strategy(
                        iid, force=force
                    ),
                    timeout=settings.macro_sync_task_timeout_seconds,
                )
                for tf in timeframes:
                    item = _extract_scan_item(payload, iid, code, tf)
                    if item is not None:
                        items.append(item)
            except asyncio.TimeoutError:
                logger.warning("opportunity_scanner: timed out %s", iid)
            except Exception:
                logger.exception("opportunity_scanner: failed %s", iid)

        return self._result(items, instrument_ids, timeframes, source="live")

    @staticmethod
    def _result(
        items: list[ScanItem],
        instrument_ids: list[str],
        timeframes: tuple[str, ...],
        *,
        source: str,
    ) -> ScanResult:
        now = datetime.now(timezone.utc)
        ranked = sorted(
            [
                it
                for it in items
                if it.cache_state == "fresh"
                and it.qualified
                and it.direction in {"LONG", "SHORT"}
                and "invalid_execution_levels" not in it.qualification_reasons
            ],
            key=lambda it: it.score,
            reverse=True,
        )
        qualified_count = sum(1 for item in items if item.qualified)

        return ScanResult(
            scanned_at=now.isoformat(),
            instruments=list(instrument_ids),
            timeframes=list(timeframes),
            matrix=items,
            ranked=ranked,
            cache_meta={
                "fresh_until": (now.replace(second=0, microsecond=0)).isoformat(),
                "source": source,
                "instruments_scanned": len(instrument_ids),
                "opportunities_found": qualified_count,
                "ranked_candidates": len(ranked),
                "matrix_gate": {
                    "min_confidence": MATRIX_MIN_CONFIDENCE,
                    "min_score": MATRIX_MIN_SCORE,
                    "min_risk_reward": MATRIX_MIN_RISK_REWARD,
                    "min_direction_gap": MATRIX_MIN_DIRECTION_GAP,
                },
                # 2026-07-24 v3: per-cell readiness counts so the
                # frontend banner can distinguish "data补齐中" from
                # "全部数据已就绪，当前无明确交易方向".
                "cells_ready": sum(1 for item in items if item.cache_state == "fresh"),
                "cells_pending": sum(
                    1 for item in items if item.cache_state in {"missing", "warming", "error"}
                ),
            },
        )


def _extract_scan_item(
    payload: dict[str, Any],
    instrument_id: str,
    code: str,
    timeframe: str,
) -> ScanItem:
    """Project exactly the decision opened by the corresponding matrix cell."""
    item = _extract_scan_item_legacy(payload, instrument_id, code, timeframe)
    opportunity = (payload.get("opportunity_decisions") or {}).get(timeframe)
    if not isinstance(opportunity, dict):
        # Old snapshots cannot safely claim executable per-period opportunities.
        item.cache_state = "missing"
        item.direction = "WAIT"
        item.direction_label = "无机会"
        item.qualified = False
        item.risk_reward = 0.0
        item.leverage_hint = "仅观察"
        item.entry_zone, item.stop_loss, item.take_profit_1 = [], None, None
        item.horizon_target = None
        item.qualification_reasons.append("period_decision_missing")
        return item
    item.direction = (
        opportunity.get("side") if opportunity.get("side") in {"LONG", "SHORT"} else "WAIT"
    )
    item.direction_label = {"LONG": "做多", "SHORT": "做空"}.get(item.direction, "等待")
    item.summary = str((opportunity.get("primary_reason") or {}).get("message") or "")
    item.primary_driver = str(opportunity.get("trade_timeframe") or timeframe)
    item.conflicts = []
    period_leverage = int(opportunity.get("recommended_leverage") or 0)
    planned_leverage = int(opportunity.get("planned_leverage") or 0)
    item.leverage_hint = (
        f"{period_leverage}x"
        if period_leverage > 0
        else f"计划 {planned_leverage}x"
        if planned_leverage > 0
        else "仅观察"
    )
    item.confidence = round(float(opportunity.get("confidence") or 0), 1)
    item.risk_reward = round(float((opportunity.get("risk_reward") or {}).get("value") or 0), 2)
    item.score = compute_opportunity_score(
        confidence=item.confidence,
        risk_reward=item.risk_reward,
        direction=item.direction,
        modules_direction_tally={
            "bullish": int(item.direction == "LONG")
            + int(opportunity.get("trigger_direction") == "LONG"),
            "bearish": int(item.direction == "SHORT")
            + int(opportunity.get("trigger_direction") == "SHORT"),
            "neutral": 0,
        },
        timeframe=timeframe,
    )
    item.position_cap = opportunity.get("position_cap") or "observe"
    item.qualified = bool(
        opportunity.get("status") == "READY"
        and opportunity.get("permission") == "allow"
        and item.cache_state == "fresh"
    )
    item.qualification_reasons = (
        [] if item.qualified else [str(opportunity.get("status") or "period_decision_unavailable")]
    )
    item.entry_zone = (
        [float(value) for value in opportunity.get("entry_zone") or []] if item.qualified else []
    )
    item.stop_loss = (
        float(opportunity["invalidation_price"])
        if item.qualified and opportunity.get("invalidation_price")
        else None
    )
    item.take_profit_1 = (
        float(opportunity["take_profit_1"])
        if item.qualified and opportunity.get("take_profit_1")
        else None
    )
    item.horizon_target = (
        float(opportunity["horizon_target"])
        if item.qualified and opportunity.get("horizon_target")
        else None
    )
    item.first_risk_reward = (
        float(opportunity["first_risk_reward"])
        if item.qualified and opportunity.get("first_risk_reward")
        else None
    )
    item.expected_move_pct = (
        float(opportunity["expected_move_pct"])
        if item.qualified and opportunity.get("expected_move_pct")
        else None
    )
    target_valid = bool(item.entry_zone and item.take_profit_1 is not None) and (
        (
            item.direction == "LONG"
            and item.horizon_target is not None
            and item.horizon_target > item.take_profit_1 > max(item.entry_zone)
        )
        or (
            item.direction == "SHORT"
            and item.horizon_target is not None
            and item.horizon_target < item.take_profit_1 < min(item.entry_zone)
        )
    )
    if item.qualified and (
        not _valid_stop_geometry(item.direction, item.entry_zone, item.stop_loss)
        or not target_valid
    ):
        item.qualified = False
        item.qualification_reasons = ["invalid_execution_levels"]
        item.entry_zone, item.stop_loss, item.take_profit_1 = [], None, None
        item.horizon_target = None
        item.first_risk_reward = None
        item.expected_move_pct = None
    if not item.qualified:
        # A research bias is not a trading opportunity. Keep the reason for
        # audit, but publish no LONG/SHORT in the opportunity scan until all
        # execution, target, leverage and freshness gates have passed.
        item.direction = "WAIT"
        item.direction_label = "无机会"
        item.risk_reward = 0.0
        item.leverage_hint = "仅观察"
    return item


def _extract_scan_item_legacy(
    payload: dict[str, Any], instrument_id: str, code: str, timeframe: str
) -> ScanItem:
    """Compatibility projection for older published snapshots."""
    node = _timeframe_node(payload, timeframe)
    decision = payload.get("trade_decision") or {}
    # A matrix cell is a timeframe conclusion, not a copy of the global trade
    # decision.  Falling back to the global side keeps old cached/test payloads
    # compatible when ``timeframe_stack`` is absent.
    direction = (node or {}).get("direction") or decision.get("side") or "WAIT"
    if direction == "NEUTRAL":
        direction = "WAIT"
    if direction in ("NONE",):
        direction = "WAIT"
    direction_label = {"LONG": "做多", "SHORT": "做空"}.get(direction, "等待")

    # 2026-07-24 v3: per-cell cache_state + data_quality.
    # The unified payload exposes `status` ("degraded"/"ready_with_warnings"
    # /"ready") and `degraded_components` (list of failing component names).
    # Rule:
    #   - status == "degraded" OR degraded_components non-empty → "missing"
    #   - otherwise → "fresh"
    #   - if payload has no status field at all → "unknown"
    status_raw = (payload.get("status") or "").strip()
    degraded_components = payload.get("degraded_components") or []
    has_published_detail = bool(
        payload.get("timeframe_stack")
        or payload.get("signal_coverage")
        or (payload.get("market_decision_snapshot") or {}).get("snapshot_id")
    )
    node_freshness = str((node or {}).get("freshness") or "").lower()
    if node_freshness in {"missing", "error"}:
        cache_state = "missing"
    elif node_freshness in {"fresh", "ready", "live"}:
        cache_state = "fresh"
    elif node_freshness in {"stale", "usable_stale", "degraded"}:
        cache_state = "stale"
    elif (
        status_raw == "degraded"
        or (isinstance(degraded_components, list) and degraded_components)
        or not has_published_detail
    ):
        cache_state = "missing"
    elif status_raw in {"ready", "ready_with_warnings"}:
        cache_state = "fresh"
    else:
        cache_state = "unknown"

    # data_quality: pull from signal_coverage list (each signal has
    # `confidence` 0-100). Average the confidences so the per-cell
    # data_quality reflects how many signals the cell has, not just
    # one. Fall back to 0.0 if absent.
    node_confidence = _number((node or {}).get("confidence"))
    sig_cov = payload.get("signal_coverage") or []
    if node is not None and node_confidence is not None:
        data_quality = round(node_confidence, 1)
    elif isinstance(sig_cov, list) and sig_cov:
        confidences = []
        for item in sig_cov:
            if isinstance(item, dict):
                c = item.get("confidence")
                if c is None:
                    c = item.get("score")
                try:
                    confidences.append(float(c))
                except (TypeError, ValueError):
                    continue
        data_quality = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    else:
        data_quality = 0.0

    tally = _timeframe_direction_tally(payload, node, timeframe)

    # Risk reward from trade_decision (risk_reward dict contains "value")
    risk_reward = _timeframe_risk_reward(payload, node, timeframe, direction)

    # Confidence: average of evidence trace item confidences (range 0-100)
    evidence_trace = payload.get("evidence_trace") or []
    confidences = [
        float(item.get("confidence", 0)) for item in evidence_trace if isinstance(item, dict)
    ]
    confidence = (
        round(node_confidence, 1)
        if node_confidence is not None
        else round(sum(confidences) / len(confidences), 1)
        if confidences
        else 0.0
    )

    # Primary driver: first evidence item with a directional conclusion
    primary_driver = ""
    for item in evidence_trace:
        if not isinstance(item, dict):
            continue
        conclusion = str(item.get("conclusion") or "")
        if conclusion in ("LONG", "SHORT"):
            primary_driver = str(item.get("conclusion_key") or "")
            break
    if not primary_driver and evidence_trace:
        first_item = evidence_trace[0]
        if isinstance(first_item, dict):
            primary_driver = str(first_item.get("conclusion_key") or "")

    primary_reason = decision.get("primary_reason") or {}
    node_evidence = (node or {}).get("evidence") or []
    node_label = str((node or {}).get("verdict_label") or "").strip()
    # Ranked summary must describe the market conclusion, not the plan
    # validator's verdict: node evidence[0] is the bundle's _explain line
    # ("当前策略状态为…"), which reports INVALID_PLAN_LEVELS when the raw
    # per-timeframe plan geometry fails validation — even though the unified
    # trade plan (built on other timeframes' levels) is perfectly executable.
    # The drawer shows the unified decision for this reason. Skip evidence
    # lines that describe plan validation, fall back to the next line, and
    # only then to the unified primary reason.
    if node_label:
        summary = node_label
        for line in node_evidence:
            text = str(line or "")
            if "策略价位无效" in text or "INVALID_PLAN_LEVELS" in text:
                continue
            summary = f"{summary}：{text}"
            break
    else:
        summary = (
            primary_reason.get("message")
            if isinstance(primary_reason, dict)
            else str(primary_reason)
        ) or ""

    # Conflicts from direction_resolution
    dir_res = payload.get("direction_resolution") or {}
    conflicts_raw = dir_res.get("conflicts") or []
    conflicts = [
        str(c.get("conflict_type") or c.get("type") or "")
        for c in conflicts_raw
        if isinstance(c, dict)
    ]

    # Leverage hint
    leverage_val = decision.get("recommended_leverage") or 0
    if leverage_val >= 5:
        leverage_hint = "5x"
    elif leverage_val >= 3:
        leverage_hint = "3x"
    else:
        leverage_hint = "spot"

    score = compute_opportunity_score(
        confidence=confidence,
        risk_reward=risk_reward,
        direction=direction,
        modules_direction_tally=tally,
        timeframe=timeframe,
    )
    qualified, qualification_reasons = _qualify_matrix_opportunity(
        payload=payload,
        node=node,
        timeframe=timeframe,
        direction=direction,
        confidence=confidence,
        score=score,
        risk_reward=risk_reward,
        cache_state=cache_state,
        position_cap=decision.get("position_cap") or "standard",
        tally=tally,
        conflicts=conflicts,
    )

    entry_zone, stop_loss, take_profit_1 = _cell_execution_levels(payload, direction, timeframe)
    if entry_zone and not _valid_stop_geometry(direction, entry_zone, stop_loss):
        # A stop at or inside the entry zone has zero/negative risk distance.
        # Keep the directional research cell, but never promote or publish
        # these numbers as an executable plan.
        qualified = False
        qualification_reasons.append("invalid_execution_levels")
        entry_zone, stop_loss, take_profit_1 = [], None, None
    if not qualified:
        # The public scan DTO must not expose another horizon's plan as an
        # executable level when the selected cell has no trading permission.
        entry_zone, stop_loss, take_profit_1 = [], None, None

    return ScanItem(
        instrument_id=instrument_id,
        instrument_code=code,
        timeframe=timeframe,
        direction=direction,
        direction_label=direction_label,
        confidence=round(confidence, 1),
        score=score,
        summary=summary,
        risk_reward=round(risk_reward, 2),
        leverage_hint=leverage_hint,
        position_cap=decision.get("position_cap") or "standard",
        primary_driver=primary_driver,
        conflicts=conflicts,
        cache_state=cache_state,
        data_quality=round(data_quality, 1),
        qualified=qualified,
        qualification_reasons=qualification_reasons,
        entry_zone=entry_zone,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
    )


def _timeframe_node(payload: dict[str, Any], timeframe: str) -> dict[str, Any] | None:
    stack = payload.get("timeframe_stack") or []
    if not isinstance(stack, list):
        return None
    return next(
        (
            item
            for item in stack
            if isinstance(item, dict) and str(item.get("timeframe") or "") == timeframe
        ),
        None,
    )


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _add_direction_vote(tally: dict[str, int], direction: Any) -> None:
    normalized = str(direction or "").upper()
    if normalized == "LONG":
        tally["bullish"] += 1
    elif normalized == "SHORT":
        tally["bearish"] += 1
    else:
        tally["neutral"] += 1


def _timeframe_direction_tally(
    payload: dict[str, Any],
    node: dict[str, Any] | None,
    timeframe: str,
) -> dict[str, int]:
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    _add_direction_vote(tally, (node or {}).get("direction"))

    horizon_key = "strategic" if timeframe == "1w" else "tactical"
    horizon = (payload.get("horizon_views") or {}).get(horizon_key) or {}
    _add_direction_vote(tally, horizon.get("direction"))

    decision = payload.get("trade_decision") or {}
    direction_timeframes = set(decision.get("direction_timeframes") or [])
    if timeframe == decision.get("trade_timeframe") or timeframe in direction_timeframes:
        _add_direction_vote(tally, decision.get("side"))
    return tally


def _cell_execution_levels(
    payload: dict[str, Any],
    direction: str,
    timeframe: str,
) -> tuple[list[float], float | None, float | None]:
    """Expose only the plan whose execution period is the selected cell.

    The ranked card prints these numbers instead of the bundle validator's
    verdict line. Candidates: ``TACTICAL_{direction}`` first (the executable
    plan), then any plan whose ``direction`` matches the cell. Plans with an
    empty entry zone are skipped — a stop without an entry is not actionable.
    No direction or no matching plan → empty levels (card hides the line).
    """
    if direction not in {"LONG", "SHORT"}:
        return [], None, None
    if timeframe != (payload.get("trade_decision") or {}).get("trade_timeframe"):
        return [], None, None
    plans = payload.get("trade_plans") or []
    if not isinstance(plans, list):
        return [], None, None

    def _levels(plan: Mapping[str, Any]) -> tuple[list[float], float | None, float | None]:
        zone = [
            value for raw in (plan.get("entry_zone") or []) if (value := _number(raw)) is not None
        ]
        stop = _number(plan.get("stop_loss"))
        take_profit = plan.get("take_profit") or []
        tp1 = None
        if isinstance(take_profit, list):
            for row in take_profit:
                if isinstance(row, Mapping):
                    tp1 = _number(row.get("price"))
                    if tp1 is not None:
                        break
        if tp1 is None:
            tp1 = _number(plan.get("take_profit_1"))
        return zone, stop, tp1

    tactical_type = f"TACTICAL_{direction}"
    ordered = sorted(
        (plan for plan in plans if isinstance(plan, Mapping)),
        key=lambda plan: (
            0
            if str(plan.get("plan_type") or plan.get("type")) == tactical_type
            else 1
            if str(plan.get("direction")) == direction
            else 2
        ),
    )
    for plan in ordered:
        if str(plan.get("direction")) != direction:
            continue
        zone, stop, tp1 = _levels(plan)
        if zone:
            return zone, stop, tp1
    return [], None, None


def _valid_stop_geometry(direction: str, zone: list[float], stop: float | None) -> bool:
    if not zone or stop is None:
        return False
    if direction == "LONG":
        return stop < min(zone)
    if direction == "SHORT":
        return stop > max(zone)
    return False


def _timeframe_risk_reward(
    payload: dict[str, Any],
    node: dict[str, Any] | None,
    timeframe: str,
    direction: str,
) -> float:
    current = _number((node or {}).get("current_price"))
    support = _number((node or {}).get("key_support"))
    resistance = _number((node or {}).get("key_resistance"))
    invalidation = _number((node or {}).get("invalidation"))
    risk = reward = None
    if current is not None and direction == "LONG":
        risk = (
            current - invalidation
            if invalidation is not None and invalidation < current
            else current - support
            if support is not None and support < current
            else None
        )
        reward = resistance - current if resistance is not None and resistance > current else None
    elif current is not None and direction == "SHORT":
        risk = (
            invalidation - current
            if invalidation is not None and invalidation > current
            else resistance - current
            if resistance is not None and resistance > current
            else None
        )
        reward = current - support if support is not None and support < current else None
    if risk is not None and reward is not None and risk > 0 and reward > 0:
        return round(reward / risk, 2)

    # Timeframe-cell RR must come from that cell's own node geometry. The old
    # decision-level fallback copied the *trade plan's* RR (computed on the
    # trade_timeframe, e.g. 4h) into the 1d/4h cells of the same side — so a
    # cell whose own geometry was invalid displayed "2.19" while the drawer
    # for that same cell showed the decision-level number built on another
    # timeframe's levels. The drawer shows the decision-level RR; the matrix
    # must not launder it into a per-timeframe number. No valid geometry →
    # 0.0.
    return 0.0


def _qualify_matrix_opportunity(
    *,
    payload: dict[str, Any],
    node: dict[str, Any] | None,
    timeframe: str,
    direction: str,
    confidence: float,
    score: float,
    risk_reward: float,
    cache_state: str,
    position_cap: str,
    tally: dict[str, int],
    conflicts: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if cache_state != "fresh":
        reasons.append("data_not_fresh")
    if payload.get("status") == "degraded" or payload.get("degraded_components"):
        reasons.append("strategy_degraded")
    if direction not in {"LONG", "SHORT"}:
        reasons.append("no_direction")
    else:
        decision = payload.get("trade_decision") or {}
        if decision.get("side") != direction:
            reasons.append("unified_direction_not_aligned")
        executable_timeframes = set(decision.get("direction_timeframes") or [])
        executable_timeframes.add(decision.get("trade_timeframe"))
        if timeframe not in executable_timeframes:
            reasons.append("timeframe_not_executable")
        if decision.get("permission") not in {"allow", "conditional"}:
            reasons.append("trade_permission_not_granted")
    if confidence < MATRIX_MIN_CONFIDENCE:
        reasons.append("confidence_below_gate")
    if score < MATRIX_MIN_SCORE:
        reasons.append("score_below_gate")
    if risk_reward < MATRIX_MIN_RISK_REWARD:
        reasons.append("risk_reward_below_gate")
    long_score = _number((node or {}).get("long_score")) or 0.0
    short_score = _number((node or {}).get("short_score")) or 0.0
    if abs(long_score - short_score) < MATRIX_MIN_DIRECTION_GAP:
        reasons.append("direction_gap_below_gate")
    supporting_key = "bullish" if direction == "LONG" else "bearish"
    opposing_key = "bearish" if direction == "LONG" else "bullish"
    if tally.get(supporting_key, 0) < MATRIX_MIN_SUPPORTING_VOTES:
        reasons.append("insufficient_alignment")
    if tally.get(opposing_key, 0) > 0:
        reasons.append("direction_conflict")
    if position_cap != "standard":
        reasons.append("position_cap_restricted")
    if conflicts:
        reasons.append("explicit_conflict")
    return not reasons, reasons
