# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping

from app.services.range_regime import classify_range

from .contracts import (
    TIMEFRAME_SPECS,
    UNIFIED_LABELS,
    TimeframeNode,
    as_mapping,
    direction_from_scores,
    evidence_confidence,
    first_float,
    freshness_from_context,
    get_value,
    list_floats,
    nested,
    to_float,
    uniq,
    verdict_for_node,
)


class MultiTimeframeStructureEngine:
    def build_nodes(
        self,
        contexts: Mapping[str, Any],
        bundles: Mapping[str, Mapping[str, Any]],
    ) -> list[TimeframeNode]:
        return [self._node(spec, contexts.get(spec.logical), bundles.get(spec.logical) or {}) for spec in TIMEFRAME_SPECS]

    def _node(self, spec, context: Any, bundle: Mapping[str, Any]) -> TimeframeNode:  # noqa: ANN001
        decision = as_mapping(bundle.get("decision"))
        plan = as_mapping(decision.get("primary_strategy"))
        long_score = to_float(decision.get("long_score"))
        short_score = to_float(decision.get("short_score"))
        neutral_score = to_float(decision.get("neutral_score"))
        direction = direction_from_scores(long_score, short_score)
        entry_zone = list_floats(plan.get("entry_zone") or plan.get("entry_price_range"))
        support = first_float(
            plan.get("support"),
            plan.get("key_support"),
            nested(context, "structure_features", "key_support"),
            min(entry_zone) if entry_zone else None,
        )
        resistance = first_float(
            plan.get("resistance"),
            plan.get("key_resistance"),
            nested(context, "structure_features", "key_resistance"),
            max(entry_zone) if entry_zone else None,
        )
        state = str(decision.get("strategy_state") or nested(context, "structure_features", "structure_state") or "UNKNOWN")
        freshness = freshness_from_context(context, bundle)
        source_modules = self._source_modules(context, decision, bundle)
        confidence = self._node_confidence(
            freshness=freshness,
            state=state,
            direction=direction,
            long_score=long_score,
            short_score=short_score,
            source_modules=source_modules,
        )
        verdict_code = verdict_for_node(state, direction, spec.logical)
        verdict_label = UNIFIED_LABELS.get(verdict_code, verdict_code)
        range_classification = classify_range(
            regime=state,
            long_score=long_score,
            short_score=short_score,
            data_status=freshness,
        )
        timeframe_state = self._timeframe_state(
            direction, state, freshness, range_classification.range_state
        )
        return TimeframeNode(
            timeframe=spec.logical,
            cache_timeframe=spec.cache,
            role=spec.role,
            role_label=spec.role_label,
            horizon=spec.horizon,
            direction=direction,
            bias=direction,
            structure_state=state,
            state=state,
            verdict_code=verdict_code,
            verdict_label=verdict_label,
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            neutral_score=round(neutral_score, 2),
            confidence=round(confidence, 2),
            current_price=first_float(bundle.get("current_price")),
            key_support=support,
            key_resistance=resistance,
            invalidation=first_float(plan.get("stop_price"), plan.get("stop_loss")),
            timeframe_state=timeframe_state,
            **range_classification.as_dict(),
            evidence=self._evidence(spec.logical, context, decision, plan, direction),
            source_modules=source_modules,
            freshness=freshness,
            data_quality=as_mapping(get_value(context, "data_quality")),
            raw_status={
                "legacy_status": bundle.get("status"),
                "cache_state": bundle.get("cache_state"),
                "freshness_state": bundle.get("freshness_state"),
            },
        )

    @staticmethod
    def _timeframe_state(
        direction: str, state: str, freshness: str, range_state: str = "NONE"
    ) -> str:
        if freshness in {"missing", "error"}:
            return "DATA_UNAVAILABLE"
        normalized = str(state or "").upper()
        if "TRANSITION" in normalized or "WAIT" in normalized:
            return "TRANSITION"
        if range_state != "NONE":
            return range_state
        if direction == "LONG":
            return "BULLISH"
        if direction == "SHORT":
            return "BEARISH"
        return "DATA_UNAVAILABLE" if normalized in {"", "UNKNOWN", "CONTEXT_MISSING"} else "TRANSITION"

    @staticmethod
    def _evidence(
        timeframe: str,
        context: Any,
        decision: Mapping[str, Any],
        plan: Mapping[str, Any],
        direction: str,
    ) -> list[str]:
        evidence = [str(item) for item in decision.get("explain", []) if item]
        state = nested(context, "structure_features", "structure_state")
        if state:
            evidence.append(f"{timeframe} 结构状态：{state}")
        if plan.get("entry_condition"):
            evidence.append(f"{timeframe} 入场条件：{plan['entry_condition']}")
        if not evidence:
            evidence.append(f"{timeframe} 方向={direction}，由 long/short score 计算。")
        return evidence[:6]

    @staticmethod
    def _source_modules(context: Any, decision: Mapping[str, Any], bundle: Mapping[str, Any]) -> list[str]:
        modules = list(bundle.get("source_modules") or decision.get("source_modules") or [])
        if not modules:
            modules.append("StrategySignalService")
        if bundle.get("cache_state") == "context_fallback":
            modules.append("MarketContextBuilder")
        if get_value(context, "chip_structure"):
            modules.append("ChipStructureService")
        if get_value(context, "macro_overview") or get_value(context, "macro_features"):
            modules.append("MacroOverviewService")
        if get_value(context, "derivatives_features"):
            modules.append("BtcDerivativesService")
        if decision:
            modules.append("StrategyGenerator")
        return uniq(modules)

    @staticmethod
    def _node_confidence(
        *,
        freshness: str,
        state: str,
        direction: str,
        long_score: float,
        short_score: float,
        source_modules: list[str],
    ) -> float:
        state_key = str(state or "").upper()
        if state_key in {"CONTEXT_MISSING", "DATA_MISSING", "DATA_DEGRADED"}:
            return 0.0
        gap = abs(long_score - short_score)
        if direction in {"LONG", "SHORT"}:
            consistency = min(1.0, max(0.65, gap / 24.0))
        else:
            # A neutral/range call is still a conclusion when scores are balanced.
            consistency = max(0.45, 1.0 - min(gap, 20.0) / 20.0)
        coverage = 1.0 if source_modules else 0.5
        return evidence_confidence(
            freshness=freshness,
            consistency=consistency,
            coverage=coverage,
        )
