from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.services.strategy_unified.unified_service import UnifiedStrategyService

logger = logging.getLogger(__name__)

SCAN_TIMEFRAMES = ("1w", "1d", "4h")


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
    direction: str          # "LONG" | "SHORT" | "WAIT"
    direction_label: str    # "做多" | "做空" | "等待"
    confidence: float
    score: float
    summary: str
    risk_reward: float
    leverage_hint: str      # "spot" | "3x" | "5x"
    position_cap: str       # "standard" | "reduced" | "observe"
    primary_driver: str
    conflicts: list[str] = field(default_factory=list)
    # 2026-07-24 v3: per-cell cache_state + data_quality so the renderer
    # can distinguish "data ready, no edge" from "data pending".
    # Without these, "等待" / "无明确交易机会" was conflated with
    # "数据还没准备好" — user thought the system was broken.
    cache_state: str = "unknown"   # "fresh" | "missing" | "stale" | "warming" | "error" | "unknown"
    data_quality: float = 0.0      # 0-100, from payload.confidence_report.confidence_score


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

    async def scan_all(
        self,
        instrument_ids: list[str],
        instrument_codes: dict[str, str],
        *,
        timeframes: tuple[str, ...] = SCAN_TIMEFRAMES,
        force: bool = False,
    ) -> ScanResult:
        """Sequentially scan all instruments × timeframes (shared DB session).

        ``force=False`` reads each cell from cache (fast — ~2-3 s for the full
        universe on a warm DB); ``force=True`` rebuilds every cell from source
        data and is only triggered by the user's explicit refresh.
        """
        now = datetime.now(timezone.utc)
        items: list[ScanItem] = []

        for iid in instrument_ids:
            code = instrument_codes.get(iid, iid)
            for tf in timeframes:
                try:
                    service = UnifiedStrategyService(self._repository)
                    payload = await service.build_unified_strategy(iid, force=force)
                    item = _extract_scan_item(payload, iid, code, tf)
                    if item is not None:
                        items.append(item)
                except Exception:
                    logger.exception("opportunity_scanner: failed %s %s", iid, tf)
        ranked = sorted(
            [it for it in items if it.direction not in ("WAIT", "NO_TRADE", "RANGE_NO_EDGE")],
            key=lambda it: it.score,
            reverse=True,
        )

        return ScanResult(
            scanned_at=now.isoformat(),
            instruments=list(instrument_ids),
            timeframes=list(timeframes),
            matrix=items,
            ranked=ranked,
            cache_meta={
                "fresh_until": (now.replace(second=0, microsecond=0)).isoformat(),
                "source": "live",
                "instruments_scanned": len(instrument_ids),
                "opportunities_found": len(ranked),
                # 2026-07-24 v3: per-cell readiness counts so the
                # frontend banner can distinguish "data补齐中" from
                # "全部数据已就绪，当前无明确交易方向".
                "cells_ready": sum(
                    1 for item in items if item.cache_state == "fresh"
                ),
                "cells_pending": sum(
                    1 for item in items
                    if item.cache_state in {"missing", "warming", "error"}
                ),
            },
        )


def _extract_scan_item(
    payload: dict[str, Any],
    instrument_id: str,
    code: str,
    timeframe: str,
) -> ScanItem:
    """从 UnifiedStrategy 响应中提取单条扫描项。"""
    decision = payload.get("trade_decision") or {}
    # TradeDecision.as_dict() uses "side" for direction (LONG / SHORT / NONE)
    direction = decision.get("side") or "WAIT"
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
    if (
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
    sig_cov = payload.get("signal_coverage") or []
    if isinstance(sig_cov, list) and sig_cov:
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

    # Build modules direction tally from market_operation chain
    market_op = payload.get("market_operation") or {}
    chain = market_op.get("chain") or {}
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    for mod_data in chain.values():
        if not isinstance(mod_data, dict):
            continue
        bias = (mod_data.get("bias") or "").upper()
        if bias == "LONG":
            tally["bullish"] += 1
        elif bias == "SHORT":
            tally["bearish"] += 1
        else:
            tally["neutral"] += 1

    # Risk reward from trade_decision (risk_reward dict contains "value")
    rr_dict = decision.get("risk_reward") or {}
    risk_reward = float(rr_dict.get("value") or 0)

    # Confidence: average of evidence trace item confidences (range 0-100)
    evidence_trace = payload.get("evidence_trace") or []
    confidences = [
        float(item.get("confidence", 0))
        for item in evidence_trace
        if isinstance(item, dict)
    ]
    confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

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

    # Summary from primary_reason message
    primary_reason = decision.get("primary_reason") or {}
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
    )
