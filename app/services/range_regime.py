from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

RANGE_LABELS = {
    "UPWARD_RANGE": "上行震荡",
    "DOWNWARD_RANGE": "下行震荡",
    "NEUTRAL_RANGE": "中性震荡",
    "NONE": "",
}
RANGE_REGIMES = {
    "range",
    "ranging",
    "balance",
    "balanced",
    "compression",
    "no_edge",
    "range_no_edge",
    "ready_neutral",
    "context_neutral",
}
BAD_DATA_STATES = {
    "missing", "error", "stale", "expired", "updating", "data_unavailable",
    "data_insufficient", "unavailable", "invalid",
}


@dataclass(slots=True)
class RangeClassification:
    range_state: str = "NONE"
    range_label: str = ""
    range_score: float = 0.0
    range_basis: list[str] = field(default_factory=list)
    range_conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_range_regime(regime: Any) -> bool:
    return str(regime or "").strip().lower() in RANGE_REGIMES


def classify_range(
    *,
    regime: Any,
    structure_direction: str | None = None,
    structure_score: float | None = None,
    long_score: float | None = None,
    short_score: float | None = None,
    composite_score: float | None = None,
    data_status: str | None = None,
) -> RangeClassification:
    if not is_range_regime(regime) or str(data_status or "").lower() in BAD_DATA_STATES:
        return RangeClassification()

    evidence_score, evidence_basis = _evidence_score(
        structure_score=structure_score,
        long_score=long_score,
        short_score=short_score,
        composite_score=composite_score,
    )
    primary = str(structure_direction or "").upper()
    if primary not in {"UP", "DOWN", "NEUTRAL"}:
        primary = ""

    conflicts: list[str] = []
    has_confirmation = any(
        value is not None
        for value in (structure_score, long_score, short_score, composite_score)
    )
    if primary == "UP" and evidence_score < -5:
        conflicts.append("价格结构抬升，但综合方向证据偏向下行。")
    elif primary == "DOWN" and evidence_score > 5:
        conflicts.append("价格结构下移，但综合方向证据偏向上行。")
    elif primary == "UP" and has_confirmation and evidence_score < 5:
        conflicts.append("价格结构抬升，但综合方向证据尚未确认上行倾向。")
    elif primary == "DOWN" and has_confirmation and evidence_score > -5:
        conflicts.append("价格结构下移，但综合方向证据尚未确认下行倾向。")

    if conflicts:
        state = "NEUTRAL_RANGE"
        score = 0.0
    elif primary == "UP":
        state = "UPWARD_RANGE"
        score = max(5.0, evidence_score)
    elif primary == "DOWN":
        state = "DOWNWARD_RANGE"
        score = min(-5.0, evidence_score)
    elif primary == "NEUTRAL":
        state = "NEUTRAL_RANGE"
        score = 0.0
    elif evidence_score >= 5:
        state = "UPWARD_RANGE"
        score = evidence_score
    elif evidence_score <= -5:
        state = "DOWNWARD_RANGE"
        score = evidence_score
    else:
        state = "NEUTRAL_RANGE"
        score = evidence_score

    basis = []
    if primary:
        primary_basis = {
            "UP": "确认摆动高点和低点同步抬升。",
            "DOWN": "确认摆动高点和低点同步下移。",
            "NEUTRAL": "确认摆动高低点未形成同向迁移。",
        }
        basis.append(primary_basis[primary])
    else:
        basis.append("价格结构证据不足，使用综合方向分作为兼容回退。")
    if evidence_basis:
        basis.append(evidence_basis)
    return RangeClassification(
        range_state=state,
        range_label=RANGE_LABELS[state],
        range_score=round(max(-100.0, min(100.0, score)), 2),
        range_basis=basis,
        range_conflicts=conflicts,
    )


def classify_swing_range(
    *,
    regime: Any,
    pivots: Iterable[Any],
    candles: list[Any],
    structure_score: float | None = None,
    data_status: str | None = None,
) -> RangeClassification:
    pivot_list = list(pivots)
    highs = [item for item in pivot_list if getattr(item, "kind", "") == "high"]
    lows = [item for item in pivot_list if getattr(item, "kind", "") == "low"]
    direction = None
    movement_basis = "确认摆动高低点不足，无法建立价格结构方向。"
    if len(highs) >= 2 and len(lows) >= 2:
        atr = _average_true_range(candles)
        threshold = atr * 0.15
        epsilon = max(1e-9, atr * 1e-9)
        high_delta = float(highs[-1].price) - float(highs[-2].price)
        low_delta = float(lows[-1].price) - float(lows[-2].price)
        movement_basis = (
            f"最近高点变化 {high_delta:+.2f}、低点变化 {low_delta:+.2f}；"
            f"最小确认阈值为 0.15 ATR（{threshold:.2f}）。"
        )
        if high_delta > threshold + epsilon and low_delta > threshold + epsilon:
            direction = "UP"
        elif high_delta < -threshold - epsilon and low_delta < -threshold - epsilon:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"
    result = classify_range(
        regime=regime,
        structure_direction=direction,
        structure_score=structure_score,
        data_status=data_status,
    )
    if result.range_state != "NONE":
        result.range_basis.insert(0, movement_basis)
    return result


def _evidence_score(
    *,
    structure_score: float | None,
    long_score: float | None,
    short_score: float | None,
    composite_score: float | None,
) -> tuple[float, str]:
    if long_score is not None and short_score is not None:
        gap = float(long_score) - float(short_score)
        return gap, f"多空方向分差为 {gap:+.1f}。"
    if structure_score is not None:
        value = float(structure_score)
        normalized = value * 100 if -1 <= value <= 1 else value
        return normalized, f"价格结构方向分为 {normalized:+.1f}。"
    if composite_score is not None:
        normalized = (float(composite_score) - 50.0) * 2.0
        return normalized, f"综合市场分为 {float(composite_score):.1f}。"
    return 0.0, "方向证据处于中性死区。"


def _average_true_range(candles: list[Any], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    selected = candles[-(period + 1) :]
    ranges: list[float] = []
    for previous, current in zip(selected, selected[1:], strict=False):
        high = float(getattr(current, "high", 0.0))
        low = float(getattr(current, "low", 0.0))
        previous_close = float(getattr(previous, "close", 0.0))
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(ranges) / len(ranges) if ranges else 0.0
