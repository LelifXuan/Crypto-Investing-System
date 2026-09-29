# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping

from app.services.onchain.metric_reader import read_metric

from .contracts import (
    MarketDimension,
    as_mapping,
    evidence_confidence,
    get_value,
    pick_context,
)

# Direction thresholds on change features (INV-002: direction comes from
# change, never from an absolute positive level). Stablecoin mcap is a slow
# aggregate: ±1% over ~7d (or ±0.3% over ~1d) is a meaningful flow signal.
_STABLECOIN_THRESHOLD_PCT = {"7d": 1.0, "1d": 0.3}
# DEX volume expansion means engagement, not directional conviction: it may
# only add a weak inflow vote at +40%/+20%; contraction cools activity but is
# NOT an outflow direction on its own.
_DEX_EXPANSION_THRESHOLD_PCT = {"7d": 40.0, "1d": 20.0}


def _first_present(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


class CapitalFlowEngine:
    def compute(self, contexts: Mapping[str, Any]) -> MarketDimension:
        primary = pick_context(contexts, primary="1d", fallback=("1w", "4h"))
        market_data = as_mapping(get_value(primary, "market_data"))
        onchain = as_mapping(get_value(primary, "onchain_features"))
        onchain_metrics = as_mapping(get_value(onchain, "metrics"))
        flows = as_mapping(get_value(onchain, "capital_flow_inputs"))
        flow_bias = str(
            market_data.get("flow_bias")
            or market_data.get("capital_flow_bias")
            or "unknown"
        )
        state, bias, score = "DATA_INSUFFICIENT", "NEUTRAL", 0.0
        human_lines: list[str] = []
        structured = False

        # P1-QNT-002: read the metric payload through the shared contract
        # helper. Usability (value present, fresh observation, sufficient
        # quality) is judged per metric — an outer context rebuilt moments ago
        # does not make an old on-chain observation fresh.
        stablecoin = read_metric(onchain_metrics, "stablecoin_total_mcap")
        dex_volume = read_metric(onchain_metrics, "dex_volume_24h")
        stablecoin_delta = _first_present(
            flows.get("stablecoin_change_7d_pct"),
            flows.get("stablecoin_change_1d_pct"),
        )
        dex_delta = _first_present(
            flows.get("dex_volume_change_7d_pct"),
            flows.get("dex_volume_change_1d_pct"),
        )

        if stablecoin.usable and stablecoin_delta is not None:
            window = "7d" if flows.get("stablecoin_change_7d_pct") is not None else "1d"
            threshold = _STABLECOIN_THRESHOLD_PCT[window]
            if stablecoin_delta >= threshold:
                state, bias, score = "CAPITAL_INFLOW", "LONG", 62.0
                human_lines.append(
                    f"稳定币市值 {window} 变化 +{stablecoin_delta:.2f}%，现货资金面偏宽松。"
                )
            elif stablecoin_delta <= -threshold:
                state, bias, score = "CAPITAL_OUTFLOW", "SHORT", 62.0
                human_lines.append(
                    f"稳定币市值 {window} 变化 {stablecoin_delta:.2f}%，现货资金面收紧。"
                )
            else:
                state, bias, score = "CAPITAL_NEUTRAL", "NEUTRAL", 50.0
                human_lines.append(
                    f"稳定币市值 {window} 变化 {stablecoin_delta:.2f}%，未越过 ±{threshold}% 流向门槛。"
                )
            structured = True
        elif dex_volume.usable and dex_delta is not None and (
            dex_delta >= _DEX_EXPANSION_THRESHOLD_PCT[
                "7d" if flows.get("dex_volume_change_7d_pct") is not None else "1d"
            ]
        ):
            state, bias, score = "CAPITAL_INFLOW", "LONG", 55.0
            human_lines.append(
                f"DEX 成交量显著放大（{dex_delta:.1f}%），链上活跃度上升仅作弱流入证据。"
            )
            structured = True

        if not structured:
            # Text-level flow_bias is diagnostic only: an untracked word can
            # not back a directional position (fail closed, INV-002).
            if flow_bias != "unknown":
                state, bias, score = "CAPITAL_NEUTRAL", "NEUTRAL", 50.0
                human_lines.append(f"资金流状态={flow_bias}，仅作描述，不参与方向加权。")
            else:
                human_lines.append("资金流缺少稳定币/成交量的变化量输入，仅凭绝对水平不推断方向。")
            for reading, label in ((stablecoin, "稳定币市值"), (dex_volume, "DEX 成交量")):
                if not reading.usable and reading.value is not None:
                    human_lines.append(
                        f"{label}观测不可用（{reading.unusable_reason}），已从方向判断剔除。"
                    )
                elif reading.value is not None and stablecoin_delta is None and label == "稳定币市值":
                    human_lines.append(
                        f"{label}仅有总量水平 {reading.value:.0f}，缺少变化量样本，不构成流向证据。"
                    )

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
                # Levels are display-only diagnostics; direction never reads them.
                "stablecoin_total_mcap": stablecoin.value,
                "dex_volume_24h": dex_volume.value,
                "stablecoin_change_pct": stablecoin_delta,
                "dex_volume_change_pct": dex_delta,
                "stablecoin_metric_usable": stablecoin.usable,
                "dex_metric_usable": dex_volume.usable,
                "human_explanation": " ".join(human_lines),
            },
        )
