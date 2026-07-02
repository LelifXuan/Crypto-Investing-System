# ruff: noqa: E501
from __future__ import annotations

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


def TIMEFRAME_STACK_LIST() -> list[str]:
    return [spec.logical for spec in TIMEFRAME_SPECS]


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
        loaded = await self.loader.load(instrument, force=force)
        contexts: Mapping[str, Any] = loaded["contexts"]
        bundles: Mapping[str, Mapping[str, Any]] = loaded["bundles"]
        nodes = self.structure_engine.build_nodes(contexts, bundles)
        market_dimensions = {
            "macro_regime": self.macro_engine.compute(contexts),
            "capital_flow": self.capital_engine.compute(contexts),
            "derivatives_regime": self.derivatives_engine.compute(contexts),
            "onchain_regime": self.onchain_engine.compute(contexts),
            "price_structure": self._price_structure_dimension(nodes),
        }
        horizon_views = self.cross_horizon_engine.build_horizon_views(nodes)
        governance = self.cross_horizon_engine.build_governance(horizon_views, nodes)
        risk_alerts = self.risk_gate_engine.build(nodes, market_dimensions)
        next_check_time = self._next_check_time(contexts)
        unified_state = self.cross_horizon_engine.build_unified_state(
            horizon_views,
            governance,
            [risk.as_dict() for risk in risk_alerts],
            nodes,
            next_check_time,
        )
        trade_plans = self.trade_plan_engine.build_plans(
            unified_state,
            horizon_views,
            governance,
            nodes,
            bundles,
        )
        market_operation = self._market_operation(market_dimensions, nodes)
        evidence_trace = self.evidence_builder.build(
            unified_state,
            horizon_views,
            market_dimensions,
            governance,
            nodes,
        )
        narrative = self.narrative_renderer.render(
            unified_state,
            horizon_views,
            trade_plans,
            risk_alerts,
            market_operation,
        )
        base_payload: dict[str, Any] = {
            "instrument_id": instrument,
            "generated_at": now_iso(),
            "status": self._payload_status(risk_alerts),
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
