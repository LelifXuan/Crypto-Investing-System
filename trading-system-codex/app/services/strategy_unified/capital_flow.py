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


class CapitalFlowEngine:
    def compute(self, contexts: Mapping[str, Any]) -> MarketDimension:
        primary = pick_context(contexts, primary="1d", fallback=("1w", "4h"))
        market_data = as_mapping(get_value(primary, "market_data"))
        onchain = as_mapping(get_value(primary, "onchain_features"))
        onchain_metrics = as_mapping(get_value(onchain, "metrics"))
        flow_bias = str(
            market_data.get("flow_bias")
            or market_data.get("capital_flow_bias")
            or "unknown"
        )
        lower = flow_bias.lower()
        state, bias, score = "DATA_MISSING", "NEUTRAL", 0.0
        human_lines: list[str] = []
        structured = False
        stablecoin_change = onchain_metrics.get("stablecoin_total_mcap")
        dex_volume = onchain_metrics.get("dex_volume_24h")
        if isinstance(stablecoin_change, (int, float)) and stablecoin_change > 0:
            state, bias, score = "CAPITAL_INFLOW", "LONG", 62.0
            human_lines.append(f"稳定币市值上升 {stablecoin_change:.2f}，现货资金面偏宽松。")
            structured = True
        elif isinstance(stablecoin_change, (int, float)) and stablecoin_change < 0:
            state, bias, score = "CAPITAL_OUTFLOW", "SHORT", 62.0
            human_lines.append(f"稳定币市值下降 {stablecoin_change:.2f}，现货资金面收紧。")
            structured = True
        elif isinstance(dex_volume, (int, float)) and dex_volume > 0:
            state, bias, score = "CAPITAL_INFLOW", "LONG", 60.0
            human_lines.append(f"DEX 24h 交易量约 {dex_volume:.0f}，链上交易活跃。")
            structured = True
        if not structured:
            if any(token in lower for token in ("inflow", "support", "long", "positive", "risk_on")):
                state, bias, score = "CAPITAL_INFLOW", "LONG", 62.0
                human_lines.append(f"资金流状态={flow_bias}，偏正向。")
            elif any(token in lower for token in ("outflow", "pressure", "short", "negative", "risk_off")):
                state, bias, score = "CAPITAL_OUTFLOW", "SHORT", 62.0
                human_lines.append(f"资金流状态={flow_bias}，偏负向。")
            elif flow_bias != "unknown":
                state, bias, score = "CAPITAL_NEUTRAL", "NEUTRAL", 50.0
                human_lines.append(f"资金流状态={flow_bias}。")
            else:
                human_lines.append("资金流缺少 ETF、稳定币、现货成交或 dominance 明确输入。")
        freshness = str(as_mapping(get_value(primary, "cache_meta")).get("cache_state") or "unknown")
        confidence = evidence_confidence(
            freshness=freshness,
            consistency=1.0 if structured else 0.3,
            coverage=1.0 if structured else 0.0,
        )
        return MarketDimension(
            key="capital_flow",
            label="资金流",
            state=state,
            bias=bias,
            horizon_impact=["strategic", "tactical"],
            score=score,
            confidence=confidence,
            evidence=human_lines,
            source_modules=["MarketContextBuilder", "OnchainFeatureEngine"],
            freshness=freshness,
            details={
                "flow_bias": flow_bias,
                "spot_volume_state": market_data.get("spot_volume_state"),
                "stablecoin_total_mcap": stablecoin_change,
                "dex_volume_24h": dex_volume,
                "human_explanation": " ".join(human_lines),
            },
        )