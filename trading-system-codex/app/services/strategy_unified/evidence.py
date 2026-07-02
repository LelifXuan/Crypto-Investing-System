# ruff: noqa: E501
from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import (
    EvidenceItem,
    HorizonGovernance,
    HorizonView,
    MarketDimension,
    TimeframeNode,
    as_mapping,
    evidence_confidence,
)


def _state_confidence(state: str) -> float:
    return {
        "EVENT_LOCKED": 0.0,
        "DATA_MISSING": 0.0,
        "ONCHAIN_UPSTREAM_MISSING": 0.0,
    }.get(state, 1.0)


class EvidenceTraceBuilder:
    """Single confidence source for the strategy page.

    The earlier implementation read ``MarketDimension.confidence`` /
    ``HorizonView.confidence`` directly, which led to two confidence
    pipelines disagreeing (the screenshot showed "67" on the timeframe stack
    and "0%" on the evidence trace for the same node). Now every evidence
    item's ``confidence`` is recomputed here from
    ``freshness + consistency + coverage``.
    """

    def build(
        self,
        state: Mapping[str, object],
        horizon_views: Mapping[str, HorizonView],
        market_dimensions: Mapping[str, MarketDimension],
        governance: HorizonGovernance,
        nodes: Sequence[TimeframeNode],
    ) -> list[EvidenceItem]:
        traces: list[EvidenceItem] = [
            EvidenceItem(
                conclusion_key="unified_state.code",
                conclusion=str(state.get("code")),
                source_modules=["CrossHorizonSynthesisEngine", "UnifiedRiskGateEngine"],
                source_timeframes=[node.timeframe for node in nodes],
                calculation_rule="strategic_direction + tactical_direction + risk_gate",
                input_features=[
                    "horizon_views.strategic.direction",
                    "horizon_views.tactical.direction",
                    "risk_alerts",
                ],
                confidence=evidence_confidence(
                    freshness=str(state.get("cache_state") or "fresh"),
                    consistency=0.6,
                    coverage=len(nodes) / 6.0,
                ),
                freshness=str(state.get("cache_state") or "unknown"),
                human_explanation=str(state.get("instruction") or "统一状态由跨周期方向与风险门禁合成。"),
            )
        ]
        for key, view in horizon_views.items():
            traces.append(
                EvidenceItem(
                    conclusion_key=f"horizon_views.{key}.direction",
                    conclusion=view.direction,
                    source_modules=view.source_modules or ["MultiTimeframeStructureEngine"],
                    source_timeframes=view.source_timeframes,
                    calculation_rule="weighted_direction_score",
                    input_features=["long_score", "short_score", "structure_state"],
                    confidence=evidence_confidence(
                        freshness="fresh",
                        consistency=1.0 if view.direction != "NEUTRAL" else 0.4,
                        coverage=len(view.source_timeframes) / 2.0,
                    ),
                    freshness="mixed",
                    human_explanation=view.instruction,
                )
            )
        for key, dim in market_dimensions.items():
            details = as_mapping(dim.details)
            traces.append(
                EvidenceItem(
                    conclusion_key=f"market_operation.{key}.bias",
                    conclusion=dim.bias,
                    source_modules=dim.source_modules,
                    source_timeframes=[],
                    calculation_rule=f"{key}_structured_judgment",
                    input_features=list(details.keys()) or ["market_context"],
                    confidence=evidence_confidence(
                        freshness=dim.freshness or "unknown",
                        consistency=_state_confidence(dim.state),
                        coverage=1.0 if details else 0.0,
                    ),
                    freshness=dim.freshness,
                    human_explanation=str(details.get("human_explanation") or "；".join(dim.evidence)),
                )
            )
        traces.append(
            EvidenceItem(
                conclusion_key="horizon_governance.position_cap",
                conclusion=governance.position_cap,
                source_modules=["CrossHorizonSynthesisEngine"],
                source_timeframes=(
                    horizon_views["strategic"].source_timeframes
                    + horizon_views["tactical"].source_timeframes
                ),
                calculation_rule="higher_tf_constraint + tactical_conflict",
                input_features=["strategic.direction", "tactical.direction"],
                confidence=evidence_confidence(
                    freshness="fresh",
                    consistency=1.0,
                    coverage=len(
                        horizon_views["strategic"].source_timeframes
                        + horizon_views["tactical"].source_timeframes
                    )
                    / 4.0,
                ),
                freshness="mixed",
                human_explanation=str(
                    governance.higher_timeframe_constraint.get("rule") or ""
                ),
            )
        )
        return traces