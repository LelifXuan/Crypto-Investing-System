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


class MacroRegimeEngine:
    def compute(self, contexts: Mapping[str, Any]) -> MarketDimension:
        daily = pick_context(contexts, primary="1d", fallback=("1w", "4h"))
        macro_features = as_mapping(get_value(daily, "macro_features"))
        macro_overview = as_mapping(get_value(daily, "macro_overview"))
        event_features = as_mapping(get_value(daily, "event_features"))
        operation_bias = str(
            macro_features.get("operation_bias")
            or macro_overview.get("operation_bias")
            or "unknown"
        )
        regime_key = str(
            macro_features.get("regime_key")
            or macro_overview.get("regime_key")
            or "unknown"
        )
        event_state = str(
            event_features.get("event_window_status")
            or event_features.get("event_window_state")
            or "normal"
        )
        lower_bias = f"{operation_bias} {regime_key}".lower()
        if event_state.lower() in {"locked", "event_locked", "high", "risk_off"}:
            state = "EVENT_LOCKED"
            bias = "NEUTRAL"
            score = 50.0
            human = "宏观事件窗口触发，本轮交易权限优先受事件约束。"
            evidence = [human]
        elif any(key in lower_bias for key in ("risk_on", "support", "loose", "bull", "positive")):
            state = "RISK_APPETITE_SUPPORTIVE"
            bias = "LONG"
            score = float(macro_features.get("total_score") or macro_overview.get("total_score") or 62)
            human = "宏观环境风险偏好回升，对多头仓位更友好；但仍需要价格结构或资金流确认后再执行。"
            evidence = [human]
        elif any(key in lower_bias for key in ("risk_off", "tight", "bear", "pressure", "negative")):
            state = "RISK_APPETITE_PRESSURE"
            bias = "SHORT"
            score = float(macro_features.get("total_score") or macro_overview.get("total_score") or 62)
            human = "宏观环境风险偏好下行，追多胜率下降；反弹失败或跌破关键位时应优先控制回撤。"
            evidence = [human]
        else:
            if not macro_features and not macro_overview:
                state = "DATA_MISSING"
                human = "宏观数据缺失，本轮宏观维度不参与强方向判断。"
                score = 50.0
            else:
                state = "MACRO_NEUTRAL"
                human = "宏观信号偏中性，未形成方向性结论。"
                score = 50.0
            bias = "NEUTRAL"
            evidence = [human]
        freshness = str(as_mapping(get_value(daily, "cache_meta")).get("cache_state") or "unknown")
        confidence = evidence_confidence(
            freshness=freshness,
            consistency=1.0 if state not in {"DATA_MISSING", "MACRO_NEUTRAL"} else 0.4,
            coverage=1.0 if macro_features or macro_overview else 0.0,
        )
        return MarketDimension(
            key="macro_regime",
            label="宏观环境",
            state=state,
            bias=bias,
            horizon_impact=["strategic", "tactical"],
            score=score,
            confidence=confidence,
            evidence=evidence,
            source_modules=["MacroOverviewService", "MarketContextBuilder"],
            freshness=freshness,
            details={"operation_bias": operation_bias, "regime_key": regime_key, "event_window_status": event_state, "human_explanation": human},
        )
