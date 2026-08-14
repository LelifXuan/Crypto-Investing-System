# ruff: noqa: E501
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.core.timeframes import normalize_instrument_id
from app.db.models.market import StrategyDecision
from app.repositories.market_repository import MarketRepository

from .capital_flow import CapitalFlowEngine
from .contracts import TIMEFRAME_SPECS, dict_payload, first_float, now_iso, payload_hash
from .cross_horizon import CrossHorizonSynthesisEngine
from .data_loader import UnifiedDataLoader
from .derivatives_regime import DerivativesRegimeEngine
from .direction_resolution import (
    DirectionResolutionEngine,
    ModuleSignal,
    derivatives_subsignals_from_features,
)
from .evidence import EvidenceTraceBuilder
from .macro_regime import MacroRegimeEngine
from .mtf_structure import MultiTimeframeStructureEngine
from .narrative import NarrativeRenderer
from .onchain_regime import OnchainRegimeEngine
from .risk_gate import UnifiedRiskGateEngine, group_risk_alerts
from .shadow_validation import ShadowValidationService
from .trade_decision import TradeDecisionEngine, _next_close_iso
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
        self.trade_decision_engine = TradeDecisionEngine()
        self.evidence_builder = EvidenceTraceBuilder()
        self.narrative_renderer = NarrativeRenderer()
        self.direction_resolution_engine = DirectionResolutionEngine()

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
        decision_snapshot = self._decision_snapshot(instrument, contexts, nodes)

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
        direction_signals = self._direction_signals(market_dimensions, nodes, risk_alerts)
        direction_signals.extend(self._technical_signals(contexts))
        for signal in direction_signals:
            signal.metadata.setdefault("snapshot_id", decision_snapshot["snapshot_id"])
            self._annotate_signal_provenance(
                signal, contexts, decision_snapshot["observed_at"]
            )
        direction_resolution = self.direction_resolution_engine.resolve(
            signals=direction_signals,
            next_check=next_check_time or "next_4h_close",
            next_check_at_iso=next_check_time if next_check_time and "T" in next_check_time else "",
        )
        cross_validation = self._cross_validation(direction_signals)
        if (
            cross_validation["status"] == "conflicted"
            and direction_resolution.position_cap == "standard"
        ):
            direction_resolution.position_cap = "reduced"
            direction_resolution.permission = "conditional"
            direction_resolution.risk_level = "medium"
        unified_state = self.cross_horizon_engine.build_unified_state(
            horizon_views, governance, [r.as_dict() for r in risk_alerts], nodes, next_check_time,
        )

        trade_decision = self.trade_decision_engine.build(
            nodes=nodes,
            bundles=bundles,
            risk_alerts=risk_alerts,
            position_cap=governance.position_cap,
            next_check=next_check_time,
        )
        unified_state["permission"] = trade_decision.permission
        unified_state["position_cap"] = trade_decision.position_cap
        unified_state["instruction"] = trade_decision.primary_reason["message"]

        # Trade plans
        try:
            trade_plans = self.trade_plan_engine.build_plans(
                unified_state,
                horizon_views,
                governance,
                nodes,
                bundles,
                trade_decision.as_dict(),
            )
        except Exception as exc:
            logger.warning("trade_plan_failed: %s", exc, exc_info=True)
            trade_plans = []
            degraded_components.append("trade_plan")

        market_operation = self._market_operation(market_dimensions, nodes, None)
        market_operation["summary"] = unified_state["instruction"]
        market_operation["operation_cards"] = [
            {**card.as_dict(), "evaluation_mode": "shadow"}
            for card in direction_resolution.operation_cards
        ]

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
                unified_state, horizon_views, trade_plans, risk_alerts, market_operation, nodes,
            )
        except Exception as exc:
            logger.warning("narrative_failed: %s", exc, exc_info=True)
            narrative = {"headline": "", "layers": [], "watchlist": [], "action": "策略推演部分组件异常，等待后台预热。"}
            degraded_components.append("narrative")

        is_degraded = bool(degraded_components)
        strategy_as_of = now_iso()
        base_payload: dict[str, Any] = {
            "instrument_id": instrument,
            "generated_at": strategy_as_of,
            "status": "degraded" if is_degraded else self._payload_status(risk_alerts),
            "degraded": is_degraded,
            "degraded_components": degraded_components,
            "prewarm_status": "idle",
            "refresh_state": loaded["refresh_state"],
            "refresh_limitations": loaded["refresh_limitations"],
            "model_version": "legacy-cross-horizon-v2",
            "active_model_version": "legacy-cross-horizon-v2",
            "candidate_model_version": "auditable-rules-v3-shadow",
            "strategy_as_of": strategy_as_of,
            "price_as_of": decision_snapshot["price_as_of"],
            "price_source": decision_snapshot["price_source"],
            "market_decision_snapshot": decision_snapshot,
            "signal_coverage": self._build_signal_coverage(
                direction_signals, contexts, decision_snapshot
            ),
            "cross_validation": cross_validation,
            "shadow_evaluation": {
                "status": "recording",
                "affects_active_decision": False,
                "candidate_model_version": "auditable-rules-v3-shadow",
                "candidate_conclusion": direction_resolution.as_dict(),
                "cross_validation": cross_validation,
                "cutover_mode": "manual",
            },
            "recompute_status": "complete",
            "unified_state": unified_state,
            "horizon_views": dict_payload(horizon_views),
            "horizon_governance": self._horizon_governance_payload(governance, direction_resolution),
            "market_operation": market_operation,
            "direction_resolution": {
                **direction_resolution.as_dict(),
                "evaluation_mode": "shadow",
                "affects_active_decision": False,
            },
            "trade_decision": trade_decision.as_dict(),
            "timeframe_stack": dict_payload(nodes),
            "trade_plans": dict_payload(trade_plans),
            "risk_alerts": dict_payload(risk_alerts),
            "risk_groups": group_risk_alerts(risk_alerts),
            "monitoring_focus": self._monitoring_focus(unified_state, horizon_views, nodes),
            "event_watch": self._event_watch(contexts),
            "evidence_trace": dict_payload(evidence_trace),
            "narrative": narrative,
        }
        base_payload["audit_persistence"] = await self._persist_decision_facts(
            instrument=instrument,
            snapshot=decision_snapshot,
            active_state=unified_state,
            trade_decision=trade_decision.as_dict(),
            shadow_resolution=direction_resolution.as_dict(),
            signals=[signal.as_dict() for signal in direction_signals],
            cross_validation=cross_validation,
            active_confidence=float(
                getattr(horizon_views.get("tactical"), "confidence", 0.0) or 0.0
            ),
            shadow_confidence=self._shadow_confidence(direction_signals),
        )
        base_payload["shadow_evaluation"]["validation"] = (
            await self._shadow_validation_summary(instrument)
        )
        digest = payload_hash(base_payload)
        base_payload["payload_hash"] = digest
        base_payload["snapshot_key"] = f"{instrument}:{digest}"
        return base_payload

    async def _shadow_validation_summary(self, instrument: str) -> dict[str, Any]:
        if not all(
            hasattr(self.repository, method)
            for method in ("list_strategy_decisions", "list_strategy_decision_outcomes")
        ):
            return {"status": "collecting", "reason": "audit_repository_unavailable"}
        try:
            return await ShadowValidationService(self.repository).build_report(
                instrument,
                update_outcomes=False,
            )
        except Exception as exc:
            logger.warning("shadow_validation_summary_failed: %s", exc, exc_info=True)
            return {"status": "collecting", "reason": type(exc).__name__}

    async def _persist_decision_facts(
        self,
        *,
        instrument: str,
        snapshot: Mapping[str, Any],
        active_state: Mapping[str, Any],
        trade_decision: Mapping[str, Any],
        shadow_resolution: Mapping[str, Any],
        signals: list[dict[str, Any]],
        cross_validation: Mapping[str, Any],
        active_confidence: float,
        shadow_confidence: float,
    ) -> dict[str, Any]:
        if not all(
            hasattr(self.repository, method)
            for method in ("get_strategy_decision", "add_strategy_decision")
        ):
            return {"status": "not_available", "decision_ids": []}
        # The decision fact is created now.  The market observation time remains in
        # ``snapshot_json``; using it as the decision time would let validation pick
        # candles that were already complete before the strategy was actually emitted.
        decision_ts = datetime.now(timezone.utc)
        current_price = self._decimal_or_none(snapshot.get("price"))
        input_hash = payload_hash(dict(snapshot))
        rows = [
            {
                "mode": "active",
                "model_version": "legacy-cross-horizon-v2",
                "action": str(trade_decision.get("status") or "NO_DIRECTION"),
                "direction": str(trade_decision.get("side") or "NONE"),
                "payload": {
                    "unified_state": dict(active_state),
                    "trade_decision": dict(trade_decision),
                },
                "conflicts": [],
                "confidence": active_confidence,
            },
            {
                "mode": "shadow",
                "model_version": "auditable-rules-v3-shadow",
                "action": str(shadow_resolution.get("permission") or "observe"),
                "direction": str(shadow_resolution.get("tactical_direction") or "NEUTRAL"),
                "payload": {
                    "direction_resolution": dict(shadow_resolution),
                    "cross_validation": dict(cross_validation),
                },
                "conflicts": list(shadow_resolution.get("conflicts") or []),
                "confidence": shadow_confidence,
            },
        ]
        decision_ids: list[str] = []
        try:
            for row in rows:
                decision_id = (
                    f"strategy:{row['mode']}:{payload_hash({'input': input_hash, 'model': row['model_version']})[:24]}"
                )
                decision_ids.append(decision_id)
                if await self.repository.get_strategy_decision(decision_id) is not None:
                    continue
                await self.repository.add_strategy_decision(
                    StrategyDecision(
                        decision_id=decision_id,
                        instrument_id=instrument,
                        timeframe="4h",
                        decision_ts=decision_ts,
                        current_price=current_price,
                        action=row["action"],
                        direction=row["direction"],
                        confidence_score=Decimal(str(row["confidence"])),
                        execution_score=None,
                        risk_score=None,
                        capital_ceiling_pct=None,
                        position_side=None,
                        position_notional=None,
                        model_version=row["model_version"],
                        config_version="manual-cutover-v1",
                        input_hash=input_hash,
                        evidence_json=signals,
                        conflict_json=row["conflicts"],
                        action_plan_json=dict(trade_decision),
                        payload_json={
                            "evaluation_mode": row["mode"],
                            "safety_gate_passed": self._safety_gate_consistent(
                                trade_decision
                            ),
                            "market_decision_snapshot": dict(snapshot),
                            **row["payload"],
                        },
                    )
                )
        except Exception as exc:
            logger.warning("strategy_decision_audit_persist_failed: %s", exc, exc_info=True)
            return {
                "status": "failed",
                "decision_ids": decision_ids,
                "reason": type(exc).__name__,
            }
        return {"status": "recorded", "decision_ids": decision_ids}

    @staticmethod
    def _shadow_confidence(signals: list[ModuleSignal]) -> float:
        values = [
            signal.confidence
            for signal in signals
            if signal.horizon == "tactical"
            and signal.direction in {"LONG", "SHORT"}
            and signal.action_effect in {"support", "confirm"}
            and signal.freshness not in {"stale", "expired", "missing", "upstream_missing"}
        ]
        return round(sum(values) / len(values), 4) if values else 0.0

    @staticmethod
    def _safety_gate_consistent(trade_decision: Mapping[str, Any]) -> bool:
        status = str(trade_decision.get("status") or "")
        permission = str(trade_decision.get("permission") or "")
        risk_reward = trade_decision.get("risk_reward") or {}
        invalid_status = status in {
            "SETUP_INVALIDATED",
            "STOP_HIT",
            "INVALID_PLAN_LEVELS",
            "PRICE_STALE",
            "PRICE_UNAVAILABLE",
        }
        if invalid_status and permission != "no_trade":
            return False
        if isinstance(risk_reward, Mapping) and risk_reward.get("valid") is False:
            return permission == "no_trade"
        return True

    @staticmethod
    def _parse_utc(value: Any) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() else None

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

    def _market_operation(
        self,
        market_dimensions: Mapping[str, Any],
        nodes: list[Any],
        direction_resolution: Any | None = None,
    ) -> dict[str, Any]:
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

    @staticmethod
    def _apply_direction_resolution_to_state(state: Mapping[str, Any], direction_resolution: Any) -> dict[str, Any]:
        payload = dict(state or {})
        payload["code"] = direction_resolution.unified_code
        payload["permission"] = direction_resolution.permission
        payload["risk_level"] = direction_resolution.risk_level
        payload["instruction"] = direction_resolution.instruction
        payload["allowed_actions"] = list(direction_resolution.allowed_actions)
        payload["blocked_actions"] = list(direction_resolution.blocked_actions)
        payload["position_cap"] = direction_resolution.position_cap
        return payload

    @staticmethod
    def _horizon_governance_payload(governance: Any, direction_resolution: Any) -> dict[str, Any]:
        payload = governance.as_dict()
        payload["governance_cards"] = [
            {**card.as_dict(), "evaluation_mode": "shadow"}
            for card in direction_resolution.governance_cards
        ]
        payload["shadow_allowed_actions"] = list(direction_resolution.allowed_actions)
        payload["shadow_blocked_actions"] = list(direction_resolution.blocked_actions)
        return payload

    def _price_structure_dimension(self, nodes: list[Any]):
        from .contracts import MarketDimension

        tactical = [node.direction for node in nodes if node.timeframe in {"1d", "4h"}]
        if tactical.count("LONG") > tactical.count("SHORT"):
            bias = "LONG"
        elif tactical.count("SHORT") > tactical.count("LONG"):
            bias = "SHORT"
        else:
            bias = "NEUTRAL"
        if bias == "LONG":
            evidence = [
                "日线与 4H 结构更偏多，多头计划需要等待回踩不破或重新站上关键位。",
                "高周期结构仅作为方向背景，执行仍以 1H/15M 触发为准。",
            ]
        elif bias == "SHORT":
            evidence = [
                "日线与 4H 结构更偏空，反弹失败时空头计划优先级更高。",
                "高周期结构仅作为方向背景，执行仍以 1H/15M 触发为准。",
            ]
        else:
            evidence = [
                "高周期与战术周期没有形成单边共振，当前价格结构更适合等待区间突破。",
                "若 1H/15M 出现触发，也需要日线或 4H 后续确认再提高仓位。",
            ]
        return MarketDimension(
            key="price_structure",
            label="价格结构",
            state="PRICE_STRUCTURE_READY",
            bias=bias,
            horizon_impact=["strategic", "tactical", "execution"],
            score=60 if bias != "NEUTRAL" else 50,
            confidence=70,
            evidence=evidence,
            source_modules=["MultiTimeframeStructureEngine"],
            freshness="mixed",
            details={
                "strategic": [node.as_dict() for node in nodes if node.timeframe in {"1M", "1w"}],
                "tactical": [node.as_dict() for node in nodes if node.timeframe in {"1d", "4h"}],
                "execution": [node.as_dict() for node in nodes if node.timeframe in {"1h", "15m"}],
            },
        )

    def _direction_signals(
        self,
        market_dimensions: Mapping[str, Any],
        nodes: list[Any],
        risk_alerts: list[Any],
    ) -> list[ModuleSignal]:
        signals: list[ModuleSignal] = []
        for node in nodes:
            signals.append(self._signal_from_node(node))
        for key, dimension in market_dimensions.items():
            signals.extend(self._signals_from_dimension(key, dimension))
        for alert in risk_alerts:
            signal = self._signal_from_risk_alert(alert)
            if signal is not None:
                signals.append(signal)
        return signals

    @staticmethod
    def _decision_snapshot(
        instrument: str, contexts: Mapping[str, Any], nodes: list[Any]
    ) -> dict[str, Any]:
        timestamps: list[str] = []
        prices: list[tuple[float, str, str]] = []
        dependency_states: dict[str, Any] = {}
        input_snapshots: dict[str, list[dict[str, Any]]] = {
            "technical": [],
            "structure": [],
            "derivatives": [],
        }
        for timeframe, context in contexts.items():
            cache_meta = getattr(context, "cache_meta", {}) or {}
            dependencies = cache_meta.get("dependencies", {}) if isinstance(cache_meta, Mapping) else {}
            dependency_states[timeframe] = dependencies
            for dependency_name, dependency in (
                dependencies.items() if isinstance(dependencies, Mapping) else []
            ):
                if isinstance(dependency, Mapping) and dependency.get("source_updated_at"):
                    timestamps.append(str(dependency["source_updated_at"]))
                if not isinstance(dependency, Mapping):
                    continue
                category = (
                    "technical"
                    if dependency_name == "technical_indicators"
                    else "structure"
                    if dependency_name == "chip_structure"
                    else "derivatives"
                    if dependency_name == "btc_derivatives"
                    else ""
                )
                if category:
                    input_snapshots[category].append(
                        {
                            "timeframe": timeframe,
                            "snapshot_id": str(dependency.get("snapshot_id") or ""),
                            "observed_at": dependency.get("source_updated_at"),
                            "expires_at": dependency.get("expires_at"),
                            "freshness": dependency.get("freshness_state"),
                            "source_page": dependency.get("source_page"),
                        }
                    )
            derivatives = getattr(context, "derivatives_features", {}) or {}
            derivative_price = first_float(derivatives.get("spot_price"))
            derivative_ts = str(derivatives.get("data_timestamp") or "")
            if derivative_price is not None:
                prices.append((derivative_price, "btc_derivatives", derivative_ts))
            market = getattr(context, "market_data", {}) or {}
            market_price = first_float(market.get("current_price"))
            if market_price is not None:
                prices.append(
                    (
                        market_price,
                        str(market.get("price_source") or "market_context"),
                        str(market.get("price_as_of") or ""),
                    )
                )
        for node in nodes:
            price = first_float(getattr(node, "current_price", None))
            if price is not None:
                prices.append((price, "strategy_timeframe", ""))
        observed_at = max(timestamps) if timestamps else now_iso()
        price, price_source, price_as_of = (
            max(prices, key=lambda item: UnifiedStrategyService._timestamp_rank(item[2]))
            if prices
            else (None, "", "")
        )
        price_as_of = price_as_of or observed_at
        identity = {
            "instrument_id": instrument,
            "price": str(Decimal(str(price))) if price is not None else None,
            "price_as_of": price_as_of,
            "observed_at": observed_at,
            "dependencies": dependency_states,
            "input_snapshots": input_snapshots,
        }
        return {
            **identity,
            "snapshot_id": f"{instrument}:{payload_hash(identity)[:16]}",
            "price_source": price_source,
        }

    @staticmethod
    def _timestamp_rank(value: str) -> float:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return float("-inf")

    @staticmethod
    def _annotate_signal_provenance(
        signal: ModuleSignal,
        contexts: Mapping[str, Any],
        fallback_observed_at: str,
    ) -> None:
        dependency_name = {
            "technical": "technical_indicators",
            "price_structure": "chip_structure",
            "derivatives": "btc_derivatives",
        }.get(signal.module)
        context = contexts.get(signal.window)
        if context is None and signal.module == "derivatives":
            context = contexts.get("4h") or contexts.get("1d")
        dependency: Mapping[str, Any] = {}
        if context is not None and dependency_name:
            cache_meta = getattr(context, "cache_meta", {}) or {}
            if isinstance(cache_meta, Mapping):
                candidate = (cache_meta.get("dependencies") or {}).get(dependency_name, {})
                dependency = candidate if isinstance(candidate, Mapping) else {}
        signal.metadata.setdefault(
            "input_snapshot_id", str(dependency.get("snapshot_id") or "")
        )
        signal.metadata.setdefault(
            "observed_at",
            str(dependency.get("source_updated_at") or fallback_observed_at),
        )
        signal.metadata.setdefault("expires_at", str(dependency.get("expires_at") or ""))
        dependency_freshness = str(dependency.get("freshness_state") or "")
        if dependency_freshness:
            signal.freshness = dependency_freshness

    @classmethod
    def _build_signal_coverage(
        cls,
        signals: list[ModuleSignal],
        contexts: Mapping[str, Any],
        snapshot: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        coverage = [signal.as_dict() for signal in signals]
        composite_usage = {
            (item["window"], item["indicator_key"]): item
            for item in coverage
        }
        rows: list[dict[str, Any]] = []

        def add_inputs(
            *,
            timeframe: str,
            source_page: str,
            source_module: str,
            values: Mapping[str, Any],
            dependency_name: str,
            mappings: Mapping[str, tuple[str, str, str]],
        ) -> None:
            context = contexts.get(timeframe)
            cache_meta = getattr(context, "cache_meta", {}) if context is not None else {}
            dependency = (
                (cache_meta.get("dependencies") or {}).get(dependency_name, {})
                if isinstance(cache_meta, Mapping)
                else {}
            )
            for key, value in values.items():
                if value is None or value == {} or value == []:
                    continue
                semantic_role, transform, parent = mappings.get(
                    key,
                    ("diagnostic", "identity", ""),
                )
                resolved_parent = (
                    f"{timeframe}_structure" if parent == "__structure__" else parent
                )
                parent_signal = composite_usage.get((timeframe, resolved_parent), {})
                parent_status = str(parent_signal.get("usage_status") or "diagnostic")
                used = parent_status in {"used", "downgrade", "block"} and bool(parent)
                rows.append(
                    {
                        "signal_id": f"input:{source_page}:{timeframe}:{key}",
                        "indicator_key": key,
                        "source_page": source_page,
                        "source_module": source_module,
                        "snapshot_id": snapshot.get("snapshot_id"),
                        "input_snapshot_id": dependency.get("snapshot_id"),
                        "observed_at": dependency.get("source_updated_at"),
                        "expires_at": dependency.get("expires_at"),
                        "horizon": (
                            "strategic"
                            if timeframe in {"1M", "1w"}
                            else "tactical"
                            if timeframe in {"1d", "4h"}
                            else "execution"
                        ),
                        "window": timeframe,
                        "semantic_role": semantic_role,
                        "transform": transform,
                        "direction": parent_signal.get("direction", "NEUTRAL"),
                        "strength": parent_signal.get("strength", 0),
                        "confidence": parent_signal.get("confidence", 0),
                        "freshness": dependency.get("freshness_state", "unknown"),
                        "usage_status": "used" if used else "diagnostic",
                        "usage_reason": (
                            f"component_of:{resolved_parent}"
                            if used
                            else "only_diagnostic_or_conditions_not_met"
                        ),
                        "value": value,
                        "coverage_kind": "input_indicator",
                    }
                )

        technical_mapping = {
            **{
                key: ("direction_input", "adx_gate_then_piecewise_saturation", "ema_adx_trend")
                for key in ("ema_20", "ema_50", "ema_200", "adx_14")
            },
            **{
                key: (
                    "confirmation",
                    "historical_percentile_asymmetric_gate",
                    "rsi_macd_momentum",
                )
                for key in (
                    "rsi_14",
                    "macd_hist",
                    "rsi_14_percentile",
                    "macd_hist_percentile",
                    "rsi_14_change",
                    "macd_hist_change",
                )
            },
            **{
                key: ("risk_gate", "historical_percentile_risk_gate", "volatility_regime")
                for key in (
                    "natr_14",
                    "bb_width",
                    "natr_14_percentile",
                    "bb_width_percentile",
                )
            },
            "atr_14": ("diagnostic", "raw_volatility", ""),
            "percent_b": ("diagnostic", "identity", ""),
            "obv_slope": ("diagnostic", "identity", ""),
            "history_points": ("diagnostic", "data_quality_count", ""),
        }
        structure_mapping = {
            "direction": ("direction_input", "structure_state_gate", "__structure__"),
            "bias": ("direction_input", "structure_state_gate", "__structure__"),
            "long_score": ("direction_input", "bounded_structure_score", "__structure__"),
            "short_score": ("direction_input", "bounded_structure_score", "__structure__"),
            "confidence": ("confirmation", "quality_gate", "__structure__"),
            "key_support": ("key_level", "level_only", ""),
            "key_resistance": ("key_level", "level_only", ""),
        }
        derivatives_mapping = {
            "funding_state": ("contrarian_crowding", "contrarian_nonlinear", "funding_rate"),
            "oi_state": ("confirmation", "price_oi_interaction", "open_interest"),
            "skew_state": ("confirmation", "asymmetric_confirmation_band", "skew_25d"),
            "basis_state": ("confirmation", "state_gate", "basis"),
            "hedge_cost_state": ("risk_gate", "risk_only_regime_bucket", "protection_cost"),
            "call_wall_strike": ("key_level", "level_only", "call_wall"),
            "put_wall_strike": ("key_level", "level_only", "put_wall"),
            "max_pain_strike": ("key_level", "level_only", "max_pain"),
            "put_call_ratios": ("confirmation", "asymmetric_ratio_band", "put_call_oi_ratio"),
        }
        for timeframe, context in contexts.items():
            indicators = getattr(context, "indicator_features", {}) or {}
            vwap = getattr(context, "vwap_features", {}) or {}
            structure = getattr(context, "structure_features", {}) or {}
            add_inputs(
                timeframe=timeframe,
                source_page="indicators",
                source_module="AnalysisBundleService",
                values={**indicators, **vwap},
                dependency_name="technical_indicators",
                mappings=technical_mapping,
            )
            add_inputs(
                timeframe=timeframe,
                source_page="structure",
                source_module="ChipStructureService",
                values=structure,
                dependency_name="chip_structure",
                mappings=structure_mapping,
            )
        derivative_context = contexts.get("4h") or contexts.get("1d")
        if derivative_context is not None:
            derivatives = getattr(derivative_context, "derivatives_features", {}) or {}
            add_inputs(
                timeframe="4h",
                source_page="btc_derivatives",
                source_module="BtcDerivativesService",
                values={
                    key: value
                    for key, value in derivatives.items()
                    if key in derivatives_mapping
                },
                dependency_name="btc_derivatives",
                mappings=derivatives_mapping,
            )
        return [*coverage, *rows]

    @staticmethod
    def _technical_signals(contexts: Mapping[str, Any]) -> list[ModuleSignal]:
        signals: list[ModuleSignal] = []
        for timeframe in ("1d", "4h", "1h", "15m"):
            context = contexts.get(timeframe)
            if context is None:
                continue
            features = getattr(context, "indicator_features", {}) or {}
            if not features:
                continue
            cache_meta = getattr(context, "cache_meta", {}) or {}
            dependency = (
                cache_meta.get("dependencies", {}).get("technical_indicators", {})
                if isinstance(cache_meta, Mapping)
                else {}
            )
            freshness = str(dependency.get("freshness_state") or "unknown")
            observed_at = str(dependency.get("source_updated_at") or "")
            expires_at = str(dependency.get("expires_at") or "")
            input_snapshot_id = str(dependency.get("snapshot_id") or "")
            horizon = "tactical" if timeframe in {"1d", "4h"} else "execution"
            ema20 = first_float(features.get("ema_20"))
            ema50 = first_float(features.get("ema_50"))
            ema200 = first_float(features.get("ema_200"))
            adx = first_float(features.get("adx_14")) or 0.0
            trend_direction = "NEUTRAL"
            if adx >= 25 and None not in {ema20, ema50, ema200}:
                if ema20 > ema50 > ema200:
                    trend_direction = "LONG"
                elif ema20 < ema50 < ema200:
                    trend_direction = "SHORT"
            trend_confidence = min(90.0, 55.0 + max(0.0, adx - 25.0) * 1.5)
            signals.append(
                ModuleSignal(
                    module="technical",
                    indicator_key="ema_adx_trend",
                    horizon=horizon,
                    window=timeframe,
                    direction=trend_direction,
                    signal_role="trend",
                    action_effect="support" if trend_direction != "NEUTRAL" else "observe",
                    score=min(78.0, 58.0 + max(0.0, adx - 25.0)),
                    confidence=trend_confidence if trend_direction != "NEUTRAL" else 40.0,
                    freshness=freshness,
                    reason="EMA 排列只有在 ADX 达到趋势门槛后才参与方向确认。",
                    source_page="indicators",
                    source_module="AnalysisBundleService",
                    metadata={
                        "transform": "adx_gate_then_piecewise_saturation",
                        "signal_family": f"trend:{horizon}",
                        "observed_at": observed_at,
                        "expires_at": expires_at,
                        "input_snapshot_id": input_snapshot_id,
                        "usage_status": "used" if trend_direction != "NEUTRAL" else "diagnostic",
                        "usage_reason": (
                            "ema_order_confirmed_by_adx"
                            if trend_direction != "NEUTRAL"
                            else "adx_gate_not_satisfied_or_ema_order_mixed"
                        ),
                    },
                )
            )
            rsi = first_float(features.get("rsi_14"))
            macd = first_float(features.get("macd_hist"))
            rsi_percentile = first_float(features.get("rsi_14_percentile"))
            macd_percentile = first_float(features.get("macd_hist_percentile"))
            macd_change = first_float(features.get("macd_hist_change"))
            momentum_direction = "NEUTRAL"
            momentum_effect = "observe"
            percentile_ready = rsi_percentile is not None and macd_percentile is not None
            if percentile_ready and macd is not None:
                if 0.55 <= rsi_percentile < 0.90 and macd_percentile >= 0.55 and macd > 0 and (macd_change or 0) >= 0:
                    momentum_direction, momentum_effect = "LONG", "confirm"
                elif 0.10 < rsi_percentile <= 0.45 and macd_percentile <= 0.45 and macd < 0 and (macd_change or 0) <= 0:
                    momentum_direction, momentum_effect = "SHORT", "confirm"
                elif rsi_percentile >= 0.90 or rsi_percentile <= 0.10:
                    momentum_effect = "downgrade"
            elif rsi is not None and macd is not None:
                if 55 <= rsi < 70 and macd > 0:
                    momentum_direction, momentum_effect = "LONG", "confirm"
                elif 30 < rsi <= 45 and macd < 0:
                    momentum_direction, momentum_effect = "SHORT", "confirm"
                elif rsi >= 70 or rsi <= 30:
                    momentum_effect = "downgrade"
            momentum_strength = (
                min(76.0, 55.0 + abs((rsi_percentile or 0.5) - 0.5) * 60.0)
                if percentile_ready
                else 60.0
            )
            signals.append(
                ModuleSignal(
                    module="technical",
                    indicator_key="rsi_macd_momentum",
                    horizon=horizon,
                    window=timeframe,
                    direction=momentum_direction,
                    signal_role="momentum" if momentum_effect != "downgrade" else "overbought_oversold",
                    action_effect=momentum_effect,
                    score=momentum_strength if momentum_direction != "NEUTRAL" else 45.0,
                    confidence=68.0 if rsi is not None and macd is not None else 0.0,
                    freshness=freshness,
                    reason="RSI 使用非对称区间并与 MACD 同向后才确认；极值只用于拥挤降级。",
                    source_page="indicators",
                    source_module="AnalysisBundleService",
                    metadata={
                        "transform": (
                            "historical_percentile_asymmetric_rsi_x_macd_gate"
                            if percentile_ready
                            else "asymmetric_rsi_band_x_macd_gate_fallback"
                        ),
                        "signal_family": f"momentum:{horizon}",
                        "observed_at": observed_at,
                        "expires_at": expires_at,
                        "input_snapshot_id": input_snapshot_id,
                        "usage_status": "used" if momentum_effect != "observe" else "diagnostic",
                        "usage_reason": (
                            "percentile_and_macd_confirmation"
                            if percentile_ready and momentum_effect != "observe"
                            else "insufficient_history_fallback"
                            if not percentile_ready
                            else "momentum_conditions_not_met"
                        ),
                    },
                )
            )
            volatility = first_float(features.get("natr_14"), features.get("bb_width"))
            volatility_percentile = first_float(
                features.get("natr_14_percentile"), features.get("bb_width_percentile")
            )
            volatility_effect = (
                "downgrade"
                if volatility_percentile is not None and volatility_percentile >= 0.85
                else "observe"
            )
            signals.append(
                ModuleSignal(
                    module="technical",
                    indicator_key="volatility_regime",
                    horizon="risk_filter",
                    window=timeframe,
                    direction="NEUTRAL",
                    signal_role="volatility",
                    action_effect=volatility_effect,
                    score=(
                        min(80.0, 50.0 + (volatility_percentile - 0.5) * 60.0)
                        if volatility_percentile is not None
                        else 50.0
                    ),
                    confidence=60.0 if volatility is not None else 0.0,
                    freshness=freshness,
                    reason="波动率只影响风险和仓位，不单独产生多空方向。",
                    source_page="indicators",
                    source_module="AnalysisBundleService",
                    metadata={
                        "transform": "historical_percentile_risk_gate",
                        "signal_family": "volatility",
                        "observed_at": observed_at,
                        "expires_at": expires_at,
                        "input_snapshot_id": input_snapshot_id,
                        "usage_status": "used" if volatility_effect == "downgrade" else "diagnostic",
                        "usage_reason": (
                            "high_volatility_percentile_reduces_execution_quality"
                            if volatility_effect == "downgrade"
                            else "risk_only_not_directional"
                        ),
                    },
                )
            )
        return [signal.normalized() for signal in signals]

    @staticmethod
    def _cross_validation(signals: list[ModuleSignal]) -> dict[str, Any]:
        module_votes: dict[str, dict[str, Any]] = {}
        for signal in signals:
            if signal.horizon not in {"tactical", "execution"}:
                continue
            if signal.direction not in {"LONG", "SHORT"} or signal.confidence <= 0:
                continue
            row = module_votes.setdefault(
                signal.module, {"long": 0.0, "short": 0.0, "signals": []}
            )
            key = "long" if signal.direction == "LONG" else "short"
            row[key] += signal.score * signal.confidence / 100.0
            row["signals"].append(signal.indicator_key)
        matrix: list[dict[str, Any]] = []
        directions: dict[str, str] = {}
        for module, row in module_votes.items():
            direction = (
                "LONG"
                if row["long"] > row["short"] + 6
                else "SHORT"
                if row["short"] > row["long"] + 6
                else "NEUTRAL"
            )
            directions[module] = direction
            matrix.append({"module": module, "direction": direction, **row})
        directional = {value for value in directions.values() if value != "NEUTRAL"}
        conflicts = []
        if len(directional) > 1:
            conflicts.append(
                {
                    "type": "cross_module_direction_conflict",
                    "modules": directions,
                    "resolution": "降低执行权限并等待价格结构确认，不将冲突简单平均。",
                }
            )
        return {
            "status": "conflicted" if conflicts else "confirmed" if directional else "insufficient",
            "matrix": matrix,
            "conflicts": conflicts,
            "price_confirmation_required": True,
        }

    @staticmethod
    def _signal_from_node(node: Any) -> ModuleSignal:
        horizon = "strategic" if node.timeframe in {"1M", "1w"} else "tactical" if node.timeframe in {"1d", "4h"} else "execution"
        score = max(float(node.long_score or 0), float(node.short_score or 0), 50.0)
        direction = str(node.direction or "NEUTRAL")
        if horizon == "execution":
            direction = (
                "WAIT_LONG_TRIGGER"
                if direction == "LONG"
                else "WAIT_SHORT_TRIGGER"
                if direction == "SHORT"
                else "WAIT"
            )
        confidence = float(node.confidence or 0)
        return ModuleSignal(
            module="price_structure",
            indicator_key=f"{node.timeframe}_structure",
            horizon=horizon,
            window=node.timeframe,
            direction=direction,
            signal_role="structure" if horizon != "execution" else "momentum",
            action_effect=(
                "confirm"
                if horizon == "execution" and confidence > 0
                else "support"
                if direction in {"LONG", "SHORT"} and confidence > 0
                else "observe"
            ),
            score=score,
            confidence=confidence,
            freshness=str(node.freshness or "unknown"),
            reason="价格结构给出周期方向；低周期只用于触发和过滤，高周期决定边界。",
            source_page="strategy_unified",
            source_module="MultiTimeframeStructureEngine",
            key_levels={
                key: value
                for key, value in {
                    "support": node.key_support,
                    "resistance": node.key_resistance,
                    "invalidation": node.invalidation,
                }.items()
                if value is not None
            },
        )

    def _signals_from_dimension(self, key: str, dimension: Any) -> list[ModuleSignal]:
        if key == "derivatives_regime":
            derived = derivatives_subsignals_from_features(getattr(dimension, "details", {}) or {})
            if derived:
                return derived
        module = {
            "macro_regime": "macro",
            "capital_flow": "capital_flow",
            "derivatives_regime": "derivatives",
            "onchain_regime": "onchain",
            "price_structure": "price_structure",
        }.get(key, key)
        horizon = "strategic" if module in {"macro", "capital_flow", "onchain"} else "tactical"
        role = {
            "macro": "macro_pressure",
            "capital_flow": "capital_flow",
            "derivatives": "derivatives_confirmation",
            "onchain": "onchain_flow",
            "price_structure": "structure",
        }.get(module, "data_quality")
        state = str(getattr(dimension, "state", "") or "").lower()
        confidence = float(getattr(dimension, "confidence", 0) or 0)
        direction = str(getattr(dimension, "bias", "NEUTRAL") or "NEUTRAL").upper()
        action_effect = "support" if direction in {"LONG", "SHORT"} and confidence > 0 else "observe"
        if "missing" in state or "degraded" in state or confidence <= 0:
            action_effect = "observe"
            direction = "NEUTRAL"
            confidence = 0
            if module == "onchain":
                role = "data_quality"
        return [
            ModuleSignal(
                module=module,
                indicator_key=key,
                horizon=horizon,
                window="1d" if horizon == "strategic" else "4h",
                direction=direction,
                signal_role=role,
                action_effect=action_effect,
                score=float(getattr(dimension, "score", 50) or 50),
                confidence=confidence,
                freshness=str(getattr(dimension, "freshness", "unknown") or "unknown"),
                reason=self._dimension_reason(dimension),
                source_page="strategy_unified",
                source_module="/".join(getattr(dimension, "source_modules", []) or []),
            )
        ]

    @staticmethod
    def _dimension_reason(dimension: Any) -> str:
        details = getattr(dimension, "details", {}) or {}
        if isinstance(details, Mapping) and details.get("human_explanation"):
            return str(details["human_explanation"])
        evidence = getattr(dimension, "evidence", []) or []
        if evidence:
            return str(evidence[0])
        return "该维度暂未形成可执行方向优势。"

    @staticmethod
    def _signal_from_risk_alert(alert: Any) -> ModuleSignal | None:
        severity = str(getattr(alert, "severity", "") or "").lower()
        if severity != "blocker":
            return None
        category = str(getattr(alert, "category", "") or "data").lower()
        return ModuleSignal(
            module="event" if category == "event" else "data",
            indicator_key=getattr(alert, "key", "") or getattr(alert, "label", "") or category,
            horizon="risk_filter",
            window="global",
            direction="NEUTRAL",
            signal_role="event_lock" if category == "event" else "data_quality",
            action_effect="block",
            score=0,
            confidence=0,
            freshness="missing",
            reason=str(getattr(alert, "message", "") or getattr(alert, "action", "") or ""),
            source_page="strategy_unified",
            source_module=str(getattr(alert, "source_module", "") or "UnifiedRiskGateEngine"),
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
                value = event_features["next_check_time"]
                # Prefer absolute ISO timestamps when upstream supplies them so
                # the UI does not have to re-resolve the next bar close.
                if "T" in str(value):
                    return str(value)
        # Fallback: next 4H bar close so the trigger conditions always render
        # an absolute timestamp instead of the legacy "next_4h_close" placeholder.
        return _next_close_iso(datetime.now(timezone.utc), "4h")

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
                direction_label = {
                    "LONG": "看多",
                    "SHORT": "看空",
                    "NEUTRAL": "方向未确认",
                }.get(node.direction, "状态待确认")
                structure_label = {
                    "BULLISH": "上涨结构",
                    "BEARISH": "下跌结构",
                    "UPWARD_RANGE": "上行震荡",
                    "DOWNWARD_RANGE": "下行震荡",
                    "NEUTRAL_RANGE": "中性震荡",
                    "TRANSITION": "转换中",
                    "DATA_UNAVAILABLE": "数据不足",
                }.get(node.timeframe_state, node.range_label or "状态待确认")
                focus.append({
                    "label": f"{node.timeframe} 关键结构",
                    "reason": f"当前方向：{direction_label}；结构：{structure_label}。",
                    "source_module": "MultiTimeframeStructureEngine",
                    "priority": "medium",
                    "horizon": node.timeframe,
                })
        return focus[:5]
