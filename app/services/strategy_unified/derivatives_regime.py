# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    MarketDimension,
    as_mapping,
    evidence_confidence,
    get_value,
    pick_context,
)

_FUNDING_TO_BIAS = {
    "positive_hot": ("NEUTRAL", 50.0, "资金费率显著为正，多头拥挤，多头延续需谨慎。"),
    "negative_hot": ("NEUTRAL", 50.0, "资金费率显著为负，空头拥挤，反弹概率上升。"),
    "neutral": ("NEUTRAL", 50.0, "资金费率中性，多空力量均衡。"),
}

_OI_TO_BIAS = {
    "buildup_long": ("LONG", 60.0, "持仓量上升伴随价格上行，多头累积。"),
    "price_up_oi_up": ("LONG", 60.0, "持仓量上升伴随价格上行，多头累积。"),
    "buildup_short": ("SHORT", 60.0, "持仓量上升伴随价格下行，空头累积。"),
    "price_down_oi_up": ("SHORT", 60.0, "持仓量上升伴随价格下行，空头累积。"),
    "price_up_oi_down": ("NEUTRAL", 48.0, "价格上涨但持仓量下降，更接近空头回补而非新趋势。"),
    "price_down_oi_down": ("NEUTRAL", 48.0, "价格下跌但持仓量下降，更接近多头去杠杆。"),
    "unwind": ("NEUTRAL", 48.0, "持仓量下降，杠杆资金离场，趋势衰减。"),
    "stable": ("NEUTRAL", 50.0, "持仓量变化不显著。"),
}

_SKEW_TO_BIAS = {
    "call_skew_high": ("LONG", 58.0, "看涨期权偏度偏高，市场愿为上行付溢价。"),
    "put_skew_high": ("SHORT", 58.0, "看跌期权偏度偏高，市场为下行保护付溢价。"),
    "skew_neutral": ("NEUTRAL", 50.0, "期权偏度中性。"),
}

_BASIS_TO_BIAS = {
    "basis_rising": ("LONG", 58.0, "基差走阔，多头情绪或资金费率上行。"),
    "basis_falling": ("SHORT", 58.0, "基差收窄，空头情绪或资金费率下行。"),
    "neutral": ("NEUTRAL", 50.0, "基差中性。"),
}


class DerivativesRegimeEngine:
    def compute(self, contexts: Mapping[str, Any]) -> MarketDimension:
        primary = pick_context(contexts, primary="4h", fallback=("1d", "1h"))
        features = as_mapping(get_value(primary, "derivatives_features"))
        bias = "NEUTRAL"
        score = 0.0
        state = str(features.get("snapshot_state") or "DATA_MISSING")
        summary_text = str(
            as_mapping(features.get("key_levels_axis")).get("summary")
            or features.get("summary")
            or ""
        )
        human_lines: list[str] = []
        matched_structured = False
        directional_votes: list[tuple[str, float]] = []
        for field, mapping in (
            ("funding_state", _FUNDING_TO_BIAS),
            ("oi_state", _OI_TO_BIAS),
            ("skew_state", _SKEW_TO_BIAS),
            ("basis_state", _BASIS_TO_BIAS),
        ):
            value = str(features.get(field) or "").lower()
            matched = mapping.get(value)
            if matched is None:
                continue
            candidate_bias, candidate_score, line = matched
            human_lines.append(line)
            matched_structured = True
            # Funding crowding and option skew are confirmation/risk inputs;
            # they cannot define the aggregate direction without price + OI.
            if field in {"oi_state", "basis_state"} and candidate_bias in {"LONG", "SHORT"}:
                directional_votes.append((candidate_bias, candidate_score))
        long_votes = [value for direction, value in directional_votes if direction == "LONG"]
        short_votes = [value for direction, value in directional_votes if direction == "SHORT"]
        if long_votes and not short_votes:
            bias, score = "LONG", sum(long_votes) / len(long_votes)
        elif short_votes and not long_votes:
            bias, score = "SHORT", sum(short_votes) / len(short_votes)
        else:
            bias, score = "NEUTRAL", 50.0 if matched_structured else 0.0
        if not matched_structured:
            summary_lower = summary_text.lower()
            if any(token in summary_lower for token in ("bull", "long", "support", "call")):
                bias = "LONG"
                score = 60.0
            elif any(token in summary_lower for token in ("bear", "short", "pressure", "put")):
                bias = "SHORT"
                score = 60.0
            else:
                bias = "NEUTRAL"
                score = 50.0 if state not in {"DATA_MISSING", "missing", "degraded"} else 0.0
        if not human_lines:
            human_lines.append(summary_text or "衍生品 funding / OI / 期权墙 / Max Pain 输入不足。")
        if state.lower() == "live":
            display_state = "DERIVATIVES_READY"
        else:
            display_state = state if state != "DATA_MISSING" else "DATA_MISSING"
        freshness = str(as_mapping(get_value(primary, "cache_meta")).get("cache_state") or "unknown")
        confidence = evidence_confidence(
            freshness=freshness,
            consistency=1.0 if matched_structured else 0.3,
            coverage=sum(
                0.25
                for key in ("funding_state", "oi_state", "skew_state", "basis_state")
                if features.get(key)
            ),
        )
        return MarketDimension(
            key="derivatives_regime",
            label="衍生品",
            state=display_state,
            bias=bias,
            horizon_impact=["tactical", "execution"],
            score=score,
            confidence=confidence,
            evidence=human_lines,
            source_modules=["BtcDerivativesService", "MarketContextBuilder"],
            freshness=freshness,
            details={
                "funding_state": features.get("funding_state"),
                "oi_state": features.get("oi_state"),
                "skew_state": features.get("skew_state"),
                "basis_state": features.get("basis_state"),
                "key_levels_axis": as_mapping(features.get("key_levels_axis")),
                "hedge_cost_state": features.get("hedge_cost_state"),
                "skew_25d": as_mapping(features.get("skew_25d")),
                "put_call_ratios": as_mapping(features.get("put_call_ratios")),
                "call_wall_strike": features.get("call_wall_strike"),
                "put_wall_strike": features.get("put_wall_strike"),
                "max_pain_strike": features.get("max_pain_strike"),
                "data_timestamp": features.get("data_timestamp"),
                "human_explanation": " ".join(human_lines),
            },
        )
