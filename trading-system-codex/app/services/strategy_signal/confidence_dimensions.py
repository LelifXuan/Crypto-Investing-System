from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ConfidenceBucket:
    key: str
    label: str
    score: float
    weight: float
    impact: str
    reason: str
    missing: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(float(self.score), 2),
            "weight": round(float(self.weight), 4),
            "impact": self.impact,
            "reason": self.reason,
            "missing": self.missing,
        }


def _clamp(value: Any, lower: float = 0.0, upper: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return lower
    if number != number:
        return lower
    return max(lower, min(upper, number))


def _score01(value: Any, default: float = 50.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if abs(number) <= 1.0:
        return _clamp(number * 100.0)
    return _clamp(number)


def _directional_strength(scores: Any) -> float:
    long_score = _score01(getattr(scores, "long_score", 0.0), 0.0)
    short_score = _score01(getattr(scores, "short_score", 0.0), 0.0)
    neutral = _score01(getattr(scores, "neutral_score", 0.0), 0.0)
    return _clamp(max(long_score, short_score) - neutral * 0.20)


def _impact(score: float) -> str:
    if score >= 70:
        return "support"
    if score <= 45:
        return "drag"
    return "neutral"


def _reliability_label(score: float) -> str:
    if score >= 80:
        return "高置信度"
    if score >= 65:
        return "中高置信度"
    if score >= 50:
        return "中等置信度"
    if score >= 35:
        return "低置信度"
    return "证据不足"


def _bucket(key, label, score, weight, reason, missing=False):
    score = _clamp(score)
    return ConfidenceBucket(
        key=key,
        label=label,
        score=score,
        weight=weight,
        impact=_impact(score),
        reason=reason,
        missing=missing,
    )


def build_confidence_report(snapshot: dict[str, Any], scores: Any) -> dict[str, Any]:
    data_quality = _score01(getattr(scores, "data_quality_score", None), 50.0)
    conflict = _score01(getattr(scores, "conflict_score", None), 0.0)
    score_map = snapshot.get("score_map") or snapshot.get("signals") or {}
    data_availability = snapshot.get("data_availability") or {}
    rr_long = _score01(getattr(scores, "rr_long", None), 50.0)
    rr_short = _score01(getattr(scores, "rr_short", None), 50.0)

    def sm(name, default=50.0):
        return _score01(score_map.get(name, default), default)

    derivatives_missing = not any(
        bool(data_availability.get(key))
        for key in ("funding", "open_interest", "oi", "cvd", "orderbook", "depth")
    )
    event_risk = _score01(score_map.get("event_risk", 50.0), 50.0)
    event_confidence = _clamp(100.0 - max(0.0, event_risk - 45.0) * 1.4)
    conflict_confidence = _clamp(100.0 - conflict)
    directional = _directional_strength(scores)

    buckets = [
        _bucket(
            "data_integrity",
            "数据完整性",
            data_quality,
            0.14,
            "K 线、指标、结构、监控快照的覆盖程度。",
            data_quality < 45,
        ),
        _bucket(
            "freshness",
            "数据新鲜度",
            sm("freshness", data_quality),
            0.08,
            "缓存与最新行情的时间差。",
        ),
        _bucket(
            "multi_timeframe",
            "多周期一致性",
            sm("mtf_trend_bullish", 50.0),
            0.10,
            "不同周期是否支持同一方向。",
        ),
        _bucket(
            "structure",
            "结构形态",
            max(sm("bullish_structure"), sm("bearish_structure")),
            0.10,
            "支撑阻力、摆动结构和经典形态证据。",
        ),
        _bucket(
            "momentum",
            "动量与量能",
            max(sm("bullish_momentum"), sm("bearish_momentum"), sm("volume_confirmation")),
            0.10,
            "趋势加速度、RSI/MACD、成交量确认。",
        ),
        _bucket(
            "flow",
            "资金流与订单流",
            max(sm("spot_flow"), sm("cvd_flow"), sm("volume_flow")),
            0.08,
            "CVD、OBV、成交量和主动买卖压力。",
        ),
        _bucket(
            "derivatives",
            "衍生品结构",
            max(sm("funding_score"), sm("oi_confirmation"), 25.0 if derivatives_missing else 50.0),
            0.08,
            "资金费率、未平仓量、杠杆拥挤度。",
            derivatives_missing,
        ),
        _bucket(
            "execution",
            "执行与流动性",
            sm("execution_quality", 55.0),
            0.08,
            "价差、深度、滑点和订单簿可执行性。",
        ),
        _bucket(
            "risk_reward",
            "风险收益比",
            max(rr_long, rr_short),
            0.10,
            "止损距离、目标空间和风险收益比。",
        ),
        _bucket(
            "event_risk",
            "事件风险",
            event_confidence,
            0.07,
            "宏观、监管、交易所、项目公告事件窗口。",
        ),
        _bucket(
            "conflict",
            "信号冲突",
            conflict_confidence,
            0.09,
            "多系统、多周期和指标之间的相互矛盾程度。",
        ),
        _bucket(
            "regime_fit",
            "行情状态适配",
            max(sm("regime_fit_long"), sm("regime_fit_short"), directional),
            0.08,
            "当前趋势/震荡/高波动 regime 与策略模板的匹配度。",
        ),
    ]
    total_weight = sum(b.weight for b in buckets) or 1.0
    weighted = sum(b.score * b.weight for b in buckets) / total_weight
    if data_quality < 40:
        weighted = min(weighted, 48.0)
    elif data_quality < 55:
        weighted = min(weighted, 62.0)
    if derivatives_missing:
        weighted = min(weighted, 74.0)
    confidence_score = round(_clamp(weighted), 2)

    drags = [b.label for b in buckets if b.impact == "drag"][:3]
    summary = (
        f"{_reliability_label(confidence_score)}：主要证据链较完整，但仍需结合止损和仓位控制。"
        if not drags
        else f"{_reliability_label(confidence_score)}：{'、'.join(drags)} 对策略信心形成拖累，已纳入置信度折扣。"
    )

    return {
        "confidence_score": confidence_score,
        "reliability_label": _reliability_label(confidence_score),
        "confidence_buckets": [b.as_dict() for b in buckets],
        "summary": summary,
    }
