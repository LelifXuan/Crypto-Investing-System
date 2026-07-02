# ruff: noqa: E501
from __future__ import annotations

import logging
from typing import Any, Mapping

from app.core.timeframes import normalize_instrument_id
from app.repositories.market_repository import MarketRepository

from .capital_flow import CapitalFlowEngine
from .contracts import TIMEFRAME_SPECS, dict_payload, now_iso, payload_hash
from .cross_horizon import CrossHorizonSynthesisEngine
from .data_loader import UnifiedDataLoader
from .derivatives_regime import DerivativesRegimeEngine
from .evidence import EvidenceTraceBuilder
from .macro_regime import MacroRegimeEngine
from .mtf_structure import MultiTimeframeStructureEngine
from .narrative import NarrativeRenderer
from .onchain_regime import OnchainRegimeEngine
from .risk_gate import UnifiedRiskGateEngine, group_risk_alerts
from .trade_plan import UnifiedTradePlanEngine

logger = logging.getLogger(__name__)


def TIMEFRAME_STACK_LIST() -> list[str]:
    return [spec.logical for spec in TIMEFRAME_SPECS]


def _make_fallback_dimension(key: str, label: str) -> "MarketDimension":  # noqa: F821
    """Build a per-dimension fallback MarketDimension with correct key/label."""
    from .contracts import MarketDimension
    return MarketDimension(
        key=key,
        label=label,
        state="DATA_MISSING",  # recognized by evidence._state_confidence
        bias="NEUTRAL",
        horizon_impact=[],
        score=50,
        confidence=0,
        evidence=[],
        source_modules=[],
        freshness="missing",
        details={"reason": "上游数据缺失", "degraded": True},
    )


class UnifiedStrategyService:
    """Orchestrate the unified multi-horizon strategy stack."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.loader = UnifiedDataLoader(repository)
        self.structure_engine = MultiTimeframeStructureEngine()
        self.macro_engine = MacroRegimeEngine()
        self.capital_engine = CapitalFlowEngine()
        self.derivatives_engine = DerivativesRegimeEngine()
        self.onchain_engine = OnchainRegimeEngine()
        self.cross_horizon_engine = CrossHorizonSynthesisEngine()
        self.risk_gate_engine = UnifiedRiskGateEngine()
        self.trade_plan_engine = UnifiedTradePlanEngine()
        self.evidence_builder = EvidenceTraceBuilder()
        self.narrative_renderer = NarrativeRenderer()

    async def build_unified_strategy(
        self,
        instrument_id: str = "btc-usdt-perp",
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        instrument = normalize_instrument_id(instrument_id)
        degraded_components: list[str] = []

        # Load contexts and bundles (data_loader already wraps in try/except)
        loaded = await self.loader.load(instrument, force=force)
        contexts: Mapping[str, Any] = loaded["contexts"]
        bundles: Mapping[str, Mapping[str, Any]] = loaded["bundles"]

        # Build nodes (defensive)
        try:
            nodes = self.structure_engine.build_nodes(contexts, bundles)
        except Exception as exc:
            logger.warning("structure_engine_failed: %s", exc, exc_info=True)
            nodes = []
            degraded_components.append("structure")

        # Compute market dimensions, each independent
        def _safe_dimension(engine, key: str, fallback_dim):
            try:
                return engine.compute(contexts)
            except Exception as exc:
                logger.warning("%s_engine_failed: %s", key, exc, exc_info=True)
                degraded_components.append(key)
                return fallback_dim

        market_dimensions = {
            "macro_regime": _safe_dimension(
                self.macro_engine, "macro_regime", _make_fallback_dimension("macro_regime", "宏观")
            ),
            "capital_flow": _safe_dimension(
                self.capital_engine, "capital_flow", _make_fallback_dimension("capital_flow", "资金")
            ),
            "derivatives_regime": _safe_dimension(
                self.derivatives_engine, "derivatives_regime", _make_fallback_dimension("derivatives_regime", "衍生品")
            ),
            "onchain_regime": _safe_dimension(
                self.onchain_engine, "onchain_regime", _make_fallback_dimension("onchain_regime", "链上")
            ),
            "price_structure": self._safe_price_structure(
                nodes, _make_fallback_dimension("price_structure", "价格结构"), degraded_components
            ),
        }

        # Cross-horizon synthesis (defensive)
        try:
            horizon_views = self.cross_horizon_engine.build_horizon_views(nodes)
            governance = self.cross_horizon_engine.build_governance(horizon_views, nodes)
        except Exception as exc:
            logger.warning("cross_horizon_failed: %s", exc, exc_info=True)
            horizon_views = {}
            governance = self._empty_governance()
            degraded_components.append("cross_horizon")

        # Risk gate
        try:
            risk_alerts = self.risk_gate_engine.build(nodes, market_dimensions)
        except Exception as exc:
            logger.warning("risk_gate_failed: %s", exc, exc_info=True)
            risk_alerts = []
            degraded_components.append("risk_gate")

        next_check_time = self._next_check_time(contexts)
        unified_state = self.cross_horizon_engine.build_unified_state(
            horizon_views, governance, [r.as_dict() for r in risk_alerts], nodes, next_check_time,
        )

        # Trade plans
        try:
            trade_plans = self.trade_plan_engine.build_plans(
                unified_state, horizon_views, governance, nodes, bundles,
            )
        except Exception as exc:
            logger.warning("trade_plan_failed: %s", exc, exc_info=True)
            trade_plans = []
            degraded_components.append("trade_plan")

        market_operation = self._market_operation(market_dimensions, nodes)

        # Evidence trace
        try:
            evidence_trace = self.evidence_builder.build(
                unified_state, horizon_views, market_dimensions, governance, nodes,
            )
        except Exception as exc:
            logger.warning("evidence_builder_failed: %s", exc, exc_info=True)
            evidence_trace = []
            degraded_components.append("evidence")

        # Narrative
        try:
            narrative = self.narrative_renderer.render(
                unified_state, horizon_views, trade_plans, risk_alerts, market_operation,
            )
        except Exception as exc:
            logger.warning("narrative_failed: %s", exc, exc_info=True)
            narrative = {"headline": "", "layers": [], "watchlist": [], "action": "策略推演部分组件异常，等待后台预热。"}
            degraded_components.append("narrative")

        is_degraded = bool(degraded_components)
        base_payload: dict[str, Any] = {
            "instrument_id": instrument,
            "generated_at": now_iso(),
            "status": "degraded" if is_degraded else self._payload_status(risk_alerts),
            "degraded": is_degraded,
            "degraded_components": degraded_components,
            "prewarm_status": "idle",
            "refresh_state": loaded["refresh_state"],
            "refresh_limitations": loaded["refresh_limitations"],
            "unified_state": unified_state,
            "horizon_views": dict_payload(horizon_views),
            "horizon_governance": governance.as_dict(),
            "market_operation": market_operation,
            "timeframe_stack": dict_payload(nodes),
            "trade_plans": dict_payload(trade_plans),
            "risk_alerts": dict_payload(risk_alerts),
            "risk_groups": group_risk_alerts(risk_alerts),
            "monitoring_focus": self._monitoring_focus(unified_state, horizon_views, nodes),
            "event_watch": self._event_watch(contexts),
            "evidence_trace": dict_payload(evidence_trace),
            "narrative": narrative,
        }
        digest = payload_hash(base_payload)
        base_payload["payload_hash"] = digest
        base_payload["snapshot_key"] = f"{instrument}:{digest}"
        return base_payload

    def _safe_price_structure(self, nodes, fallback_dim, degraded_components):
        try:
            return self._price_structure_dimension(nodes)
        except Exception as exc:
            logger.warning("price_structure_dimension_failed: %s", exc, exc_info=True)
            degraded_components.append("price_structure")
            return fallback_dim

    @staticmethod
    def _empty_governance():
        from .contracts import HorizonGovernance
        return HorizonGovernance(
            higher_timeframe_constraint={"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            lower_timeframe_driver={"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            position_cap="0%",
            allowed_sides=[],
            upgrade_path=[],
            invalidation_path=[],
        )

    def _market_operation(self, market_dimensions: Mapping[str, Any], nodes: list[Any]) -> dict[str, Any]:
        chain = {
            "macro_regime": market_dimensions["macro_regime"].as_dict(),
            "capital_flow": market_dimensions["capital_flow"].as_dict(),
            "derivatives_regime": market_dimensions["derivatives_regime"].as_dict(),
            "onchain_regime": market_dimensions["onchain_regime"].as_dict(),
            "price_structure": market_dimensions["price_structure"].as_dict(),
        }
        return {
            "chain": chain,
            "macro_regime": chain["macro_regime"],
            "capital_flow": chain["capital_flow"],
            "derivatives_regime": chain["derivatives_regime"],
            "onchain_regime": chain["onchain_regime"],
            "price_structure": chain["price_structure"],
            "summary": " → ".join(f"{item['label']}:{item['bias']}" for item in chain.values()),
        }

    def _price_structure_dimension(self, nodes: list[Any]):
        from .contracts import MarketDimension

        strategic = [node.direction for node in nodes if node.timeframe in {"1M", "1w"}]
        tactical = [node.direction for node in nodes if node.timeframe in {"1d", "4h"}]
        if tactical.count("LONG") > tactical.count("SHORT"):
            bias = "LONG"
        elif tactical.count("SHORT") > tactical.count("LONG"):
            bias = "SHORT"
        else:
            bias = "NEUTRAL"
        return MarketDimension(
            key="price_structure",
            label="价格结构",
            state="PRICE_STRUCTURE_READY",
            bias=bias,
            horizon_impact=["strategic", "tactical", "execution"],
            score=60 if bias != "NEUTRAL" else 50,
            confidence=70,
            evidence=[f"战略栈={strategic}", f"战术栈={tactical}"],
            source_modules=["MultiTimeframeStructureEngine"],
            freshness="mixed",
            details={
                "strategic": [node.as_dict() for node in nodes if node.timeframe in {"1M", "1w"}],
                "tactical": [node.as_dict() for node in nodes if node.timeframe in {"1d", "4h"}],
                "execution": [node.as_dict() for node in nodes if node.timeframe in {"1h", "15m"}],
            },
        )

    @staticmethod
    def _payload_status(risk_alerts: list[Any]) -> str:
        if any(item.severity == "blocker" for item in risk_alerts):
            return "degraded"
        if any(item.severity == "warning" for item in risk_alerts):
            return "ready_with_warnings"
        return "ready"

    @staticmethod
    def _next_check_time(contexts: Mapping[str, Any]) -> str | None:
        for context in contexts.values():
            event_features = getattr(context, "event_features", None)
            if isinstance(event_features, Mapping) and event_features.get("next_check_time"):
                return str(event_features["next_check_time"])
        return None

    @staticmethod
    def _event_watch(contexts: Mapping[str, Any]) -> list[dict[str, Any]]:
        items = []
        for tf, context in contexts.items():
            event_features = getattr(context, "event_features", None)
            if not isinstance(event_features, Mapping):
                continue
            status = event_features.get("event_window_status")
            events = event_features.get("events") or []
            if status and not UnifiedStrategyService._is_routine_event_status(status):
                items.append({
                    "timeframe": tf,
                    "event_window_status": status,
                    "events": events,
                    "impact_layer": "tactical/execution",
                    "trading_rule": "事件窗口内暂停新开高杠杆仓位。",
                    "next_check_time": event_features.get("next_check_time"),
                })
        return items

    @staticmethod
    def _is_routine_event_status(status: Any) -> bool:
        normalized = str(status or "").strip().lower()
        return normalized in {"", "normal", "clear", "none", "ready", "no_event", "no-event", "qingxi", "清晰"}

    @staticmethod
    def _monitoring_focus(state: Mapping[str, Any], horizon_views: Mapping[str, Any], nodes: list[Any]) -> list[dict[str, Any]]:
        focus = [
            {
                "label": "统一策略权限",
                "reason": str(state.get("instruction") or ""),
                "source_module": "CrossHorizonSynthesisEngine",
                "priority": "high" if state.get("permission") == "no_trade" else "medium",
                "horizon": "unified",
            }
        ]
        for node in nodes:
            if node.timeframe in {"1d", "4h", "1h"}:
                focus.append({
                    "label": f"{node.timeframe} 关键结构",
                    "reason": f"方向 {node.direction}，结构 {node.structure_state}",
                    "source_module": "MultiTimeframeStructureEngine",
                    "priority": "medium",
                    "horizon": node.timeframe,
                })
        return focus[:5]
