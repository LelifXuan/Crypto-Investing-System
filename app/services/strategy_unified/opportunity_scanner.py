from __future__ import annotations

import asyncio
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
            if modules_direction_tally.get("bullish", 0) >= 2 and modules_direction_tally.get("bearish", 0) >= 2:
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
    ) -> ScanResult:
        """并行扫描所有品种x级别。"""
        now = datetime.now(timezone.utc)

        async def _scan_one(instrument_id: str, code: str, tf: str) -> ScanItem | None:
            try:
                service = UnifiedStrategyService(self._repository)
                payload = await service.build_unified_strategy(instrument_id, force=False)
                return _extract_scan_item(payload, instrument_id, code, tf)
            except Exception:
                logger.exception("opportunity_scanner: failed %s %s", instrument_id, tf)
                return None

        tasks = [
            _scan_one(iid, instrument_codes.get(iid, iid), tf)
            for iid in instrument_ids
            for tf in timeframes
        ]
        results = await asyncio.gather(*tasks)

        items = [r for r in results if r is not None]
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
    )
