# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    MarketDimension,
    as_mapping,
    evidence_confidence,
    get_value,
    to_float,
)

_ONCHAIN_TO_BIAS = {
    "fresh": ("NEUTRAL", 60.0, "链上数据新鲜，按指标组合给出观察结论。"),
    "stale": ("NEUTRAL", 35.0, "链上数据已过期，仅作低权重观察项。"),
    "upstream_missing": ("NEUTRAL", 0.0, "链上数据上游缺失，本轮不参与强方向判断。"),
}


class OnchainRegimeEngine:
    def compute(self, contexts: Mapping[str, Any]) -> MarketDimension:
        primary = contexts.get("1w") or contexts.get("1d") or {}
        if not isinstance(primary, Mapping):
            primary = {}
        features = as_mapping(get_value(primary, "onchain_features"))
        data_status = str(features.get("data_status") or "upstream_missing")
        bias_raw = str(features.get("bias") or "NEUTRAL").upper()
        bias = bias_raw if bias_raw in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL"
        score = to_float(features.get("score"), 0.0)
        summary = str(
            features.get("summary")
            or "上游监控页未产出链上数据，链上维度本轮不参与强方向判断。"
        )
        missing_inputs = list(features.get("missing_inputs") or [])
        state_info = _ONCHAIN_TO_BIAS.get(data_status, _ONCHAIN_TO_BIAS["upstream_missing"])
        state = {
            "fresh": "ONCHAIN_MONITORING_READY",
            "stale": "ONCHAIN_MONITORING_STALE",
            "upstream_missing": "ONCHAIN_UPSTREAM_MISSING",
        }.get(data_status, "ONCHAIN_UPSTREAM_MISSING")
        evidence = [summary, state_info[2]]
        if data_status == "upstream_missing":
            evidence.append(
                "链上维度不参与强方向加权，需先由监控 / 链上页面补齐。"
            )
        freshness = data_status
        final_confidence = evidence_confidence(
            freshness=freshness,
            consistency=1.0 if data_status == "fresh" else 0.4,
            coverage=1.0 if data_status == "fresh" else (0.5 if data_status == "stale" else 0.0),
        )
        return MarketDimension(
            key="onchain_regime",
            label="链上状态",
            state=state,
            bias=bias,
            horizon_impact=["strategic", "risk_filter"],
            score=score if data_status == "fresh" else 0.0,
            confidence=final_confidence,
            evidence=evidence,
            source_modules=list(features.get("source_modules") or ["IndicatorObservation"]),
            freshness=freshness,
            details={
                **features,
                "missing_inputs": missing_inputs,
                "strategy_impact": self._strategy_impact(data_status, missing_inputs),
                "human_explanation": " ".join(evidence),
            },
        )

    @staticmethod
    def _strategy_impact(data_status: str, missing_inputs: Any) -> str:
        if data_status == "fresh":
            return "链上维度可参与长期流动性和风险偏好确认，但不直接触发短线入场。"
        if data_status == "stale":
            return "链上维度降为低权重观察，长期配置置信度下调。"
        missing = ", ".join(str(item) for item in (missing_inputs or [])) or "链上观测数据"
        return f"缺少 {missing}；链上维度不参与强方向加权，需先由监控 / 链上页面补齐。"
