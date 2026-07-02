from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Direction = Literal["bullish", "bearish", "neutral"]
StrategyBias = Literal["long", "short", "neutral", "none", "conflicted", "risk_off"]
StrategyEffect = Literal["supports_strategy", "opposes_strategy", "watch_only", "none"]
RecommendedAction = Literal["allow", "downgrade", "block_chasing", "observe"]

MICROSTRUCTURE_TERMS = {
    "cvd",
    "delta",
    "open_interest",
    "oi",
    "order_book",
    "orderbook",
    "depth",
    "slippage",
    "spread_bps",
    "chip_structure",
    "microstructure",
}


@dataclass(slots=True)
class DivergenceRisk:
    status: str
    evidence_level: str
    direction: Direction
    score: float
    confidence: float
    leaders: list[str]
    strategy_effect: StrategyEffect
    recommended_action: RecommendedAction
    summary: str
    confirmation: str | None = None
    invalidation: str | None = None
    risk_reasons: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_reasons"] = payload.get("risk_reasons") or []
        return payload


def _get(obj: Any, path: str, default: Any = None) -> Any:
    current = obj
    for key in path.split("."):
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return default if current is None else current


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_strategy_bias(value: Any) -> StrategyBias:
    raw = str(value or "neutral").lower().strip()
    mapping = {
        "bullish": "long",
        "long_bias": "long",
        "wait_long_confirmation": "long",
        "long_triggered": "long",
        "bearish": "short",
        "short_bias": "short",
        "wait_short_confirmation": "short",
        "short_triggered": "short",
        "no_edge": "neutral",
        "observe": "neutral",
        "risk_off": "risk_off",
        "conflict": "conflicted",
        "conflicted": "conflicted",
    }
    allowed = {"long", "short", "neutral", "none", "conflicted", "risk_off"}
    mapped = mapping.get(raw, raw)
    return mapped if mapped in allowed else "neutral"  # type: ignore[return-value]


def _overall_direction(overall: dict[str, Any], score: float) -> Direction:
    tone = str(overall.get("tone") or "").lower()
    title = str(overall.get("title") or "")
    if tone in {"bullish", "bearish", "neutral"}:
        return tone  # type: ignore[return-value]
    if "底背离" in title or score > 0.05:
        return "bullish"
    if "顶背离" in title or score < -0.05:
        return "bearish"
    return "neutral"


def _first_signal_text(signals: list[dict[str, Any]], key: str, direction: Direction) -> str | None:
    if direction == "neutral":
        return None
    preferred = [item for item in signals if str(item.get("direction") or "").lower() == direction]
    for item in preferred or signals:
        value = item.get(key)
        if value:
            return str(value)
    return None


def _effect(
    direction: Direction,
    strategy_bias: StrategyBias,
    confidence: float,
) -> tuple[StrategyEffect, RecommendedAction]:
    if direction == "neutral" or strategy_bias in {"neutral", "none", "conflicted", "risk_off"}:
        return "watch_only", "observe"
    if direction == "bullish" and strategy_bias == "long":
        return "supports_strategy", "allow" if confidence >= 0.45 else "observe"
    if direction == "bearish" and strategy_bias == "short":
        return "supports_strategy", "allow" if confidence >= 0.45 else "observe"
    if confidence >= 0.45:
        return "opposes_strategy", "block_chasing"
    return "opposes_strategy", "downgrade"


def _summary(
    *,
    timeframe: str,
    direction: Direction,
    leaders: list[str],
    strategy_bias: StrategyBias,
    effect: StrategyEffect,
    fallback_message: str,
) -> str:
    if direction == "neutral":
        return fallback_message or "未发现有效背离风险。"

    indicator_text = " / ".join(leaders[:4]) if leaders else "多指标"
    divergence_label = "底背离" if direction == "bullish" else "顶背离"
    base = f"{timeframe} 出现 {indicator_text} {divergence_label}。"
    if effect == "opposes_strategy":
        if strategy_bias == "short" and direction == "bullish":
            return base + "该信号削弱当前追空质量，等待背离失效或反弹确认后再评估。"
        if strategy_bias == "long" and direction == "bearish":
            return base + "该信号削弱当前追多质量，等待背离失效或回落确认后再评估。"
        return base + "该信号与当前策略方向相反，当前策略应降级观察。"
    if effect == "supports_strategy":
        return base + "该信号与当前策略方向一致，但仍只作为风险过滤依据，不直接作为入场信号。"
    return base + "当前仅作为风险观察，不改变基础策略结论。"


def build_divergence_risk(
    divergence_summary: dict[str, Any] | None,
    *,
    strategy_bias: Any = "neutral",
    timeframe: str | None = None,
    min_active_confidence: float = 0.15,
    strong_confidence: float = 0.45,
) -> dict[str, Any]:
    if not divergence_summary:
        return DivergenceRisk(
            status="none",
            evidence_level="technical_proxy",
            direction="neutral",
            score=0.0,
            confidence=0.0,
            leaders=[],
            strategy_effect="none",
            recommended_action="observe",
            summary="未发现有效背离风险。",
            risk_reasons=[],
        ).to_dict()

    overall = _get(divergence_summary, "overall", {}) or {}
    signals = _get(divergence_summary, "signals", []) or []
    if not isinstance(signals, list):
        signals = []
    score = _as_float(overall.get("score"), 0.0)
    confidence = _as_float(overall.get("confidence"), 0.0)
    leaders = [str(item) for item in (overall.get("leaders") or [])]
    direction = _overall_direction(overall, score)
    active = bool(signals) and confidence >= min_active_confidence and direction != "neutral"
    tf = timeframe or str(_get(divergence_summary, "timeframe", "当前周期"))

    if not active:
        return DivergenceRisk(
            status="none",
            evidence_level="technical_proxy",
            direction="neutral",
            score=score,
            confidence=confidence,
            leaders=leaders,
            strategy_effect="none",
            recommended_action="observe",
            summary=str(overall.get("message") or "未发现有效背离风险。"),
            risk_reasons=[],
        ).to_dict()

    bias = normalize_strategy_bias(strategy_bias)
    effect, action = _effect(direction, bias, confidence)
    if action == "downgrade" and confidence >= strong_confidence:
        action = "block_chasing"
    confirmation = _first_signal_text(signals, "confirmation", direction)
    invalidation = _first_signal_text(signals, "invalidation", direction)
    summary = _summary(
        timeframe=tf,
        direction=direction,
        leaders=leaders,
        strategy_bias=bias,
        effect=effect,
        fallback_message=str(overall.get("message") or ""),
    )
    risk_reasons = ["背离只属于技术代理风险，不直接作为入场信号。"]
    if effect == "opposes_strategy":
        risk_reasons.append("背离方向与当前策略方向相反，禁止直接追单，等待确认或失效。")
    if confirmation:
        risk_reasons.append(f"确认条件：{confirmation}")
    if invalidation:
        risk_reasons.append(f"失效条件：{invalidation}")

    return DivergenceRisk(
        status="active",
        evidence_level="technical_proxy",
        direction=direction,
        score=score,
        confidence=confidence,
        leaders=leaders,
        strategy_effect=effect,
        recommended_action=action,
        summary=summary,
        confirmation=confirmation,
        invalidation=invalidation,
        risk_reasons=risk_reasons,
    ).to_dict()


def score_divergence_for_snapshot(risk: dict[str, Any]) -> dict[str, float]:
    direction = str(risk.get("direction") or "neutral")
    confidence = max(0.0, min(1.0, _as_float(risk.get("confidence"), 0.0)))
    active = str(risk.get("status") or "") == "active"
    opposite = str(risk.get("strategy_effect") or "") == "opposes_strategy"
    return {
        "technical_risk_availability": 100.0 if risk else 0.0,
        "divergence_support_long": round(confidence * 100, 2)
        if active and direction == "bullish"
        else 50.0,
        "divergence_support_short": round(confidence * 100, 2)
        if active and direction == "bearish"
        else 50.0,
        "opposite_divergence_risk_score": round(confidence * 100, 2)
        if active and opposite
        else 0.0,
    }


def contains_microstructure_terms(payload: Any) -> bool:
    text = str(payload).lower()
    return any(term in text for term in MICROSTRUCTURE_TERMS)
