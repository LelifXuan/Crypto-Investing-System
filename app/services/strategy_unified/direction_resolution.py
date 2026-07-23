# ruff: noqa: E501
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

DIRECTION_LABELS = {
    "LONG": "看多",
    "SHORT": "看空",
    "NEUTRAL": "中性",
    "WAIT": "等待",
    "WAIT_LONG_TRIGGER": "等待多头触发",
    "WAIT_SHORT_TRIGGER": "等待空头触发",
    "BLOCK": "暂停交易",
}

MODULE_TITLES = {
    "technical": "技术指标",
    "macro": "宏观环境",
    "capital_flow": "资金流",
    "derivatives": "衍生品",
    "onchain": "链上状态",
    "price_structure": "价格结构",
    "event": "事件窗口",
    "data": "数据质量",
}

# Per-module cadence for "next check" timestamps. Higher timeframe modules
# align with their natural refresh cadence; price_structure and event use the
# fast 1H bar so the UI always shows a near-future ISO timestamp.
_MODULE_CHECK_TIMEFRAME = {
    "macro": "1d",
    "capital_flow": "4h",
    "derivatives": "4h",
    "onchain": "4h",
    "price_structure": "1h",
    "event": "1h",
    "data": "1h",
}

ROLE_FACTORS = {
    "structure": 1.25,
    "trend": 1.15,
    "derivatives_confirmation": 1.0,
    "capital_flow": 0.9,
    "macro_pressure": 0.85,
    "onchain_flow": 0.75,
    "momentum": 0.7,
    "crowding": 0.25,
    "key_level": 0.0,
    "volatility": 0.2,
    "overbought_oversold": 0.25,
    "event_lock": 0.0,
    "data_quality": 0.0,
}

FRESHNESS_FACTORS = {
    "fresh": 1.0,
    "ready": 1.0,
    "computed": 0.95,
    "usable_stale": 0.72,
    "mixed": 0.65,
    "unknown": 0.35,
    "stale": 0.0,
    "expired": 0.0,
    "missing": 0.0,
    "upstream_missing": 0.0,
    "degraded": 0.0,
}


@dataclass(slots=True)
class ModuleSignal:
    module: str
    indicator_key: str
    horizon: str
    window: str
    direction: str
    signal_role: str
    action_effect: str
    asset_lens: str = "btc_perp"
    score: float = 50.0
    confidence: float = 50.0
    freshness: str = "unknown"
    reason: str = ""
    source_page: str = ""
    source_module: str = ""
    key_levels: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ModuleSignal":
        return ModuleSignal(
            module=normalize_module(self.module),
            indicator_key=str(self.indicator_key or "unknown"),
            asset_lens=str(self.asset_lens or "btc_perp"),
            horizon=normalize_horizon(self.horizon),
            window=str(self.window or "unknown"),
            direction=normalize_direction(self.direction),
            signal_role=str(self.signal_role or "data_quality").lower(),
            action_effect=str(self.action_effect or "observe").lower(),
            score=to_float(self.score, 50.0),
            confidence=clamp(to_float(self.confidence, 50.0), 0.0, 100.0),
            freshness=str(self.freshness or "unknown").lower(),
            reason=str(self.reason or ""),
            source_page=str(self.source_page or ""),
            source_module=str(self.source_module or self.module or ""),
            key_levels=dict(self.key_levels or {}),
            metadata=dict(self.metadata or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        signal = self.normalized()
        payload = asdict(signal)
        metadata = dict(signal.metadata or {})
        transform = str(
            metadata.get("transform")
            or {
                "structure": "state_gate",
                "trend": "piecewise_saturation",
                "momentum": "percentile_piecewise",
                "crowding": "contrarian_nonlinear",
                "derivatives_confirmation": "price_oi_interaction",
                "key_level": "level_only",
                "volatility": "risk_gate",
                "event_lock": "binary_gate",
            }.get(signal.signal_role, "declared_rule")
        )
        usage_status = str(
            "excluded"
            if signal.freshness in {"stale", "expired", "missing", "upstream_missing"}
            else metadata.get("usage_status")
            or (
                "used"
                if signal.action_effect in {"support", "confirm", "downgrade", "block"}
                and signal.confidence > 0
                else "diagnostic"
            )
        )
        payload.update(
            {
                "signal_id": str(
                    metadata.get("signal_id")
                    or f"{signal.module}:{signal.indicator_key}:{signal.horizon}:{signal.window}"
                ),
                "snapshot_id": str(metadata.get("snapshot_id") or ""),
                "observed_at": str(metadata.get("observed_at") or ""),
                "expires_at": str(metadata.get("expires_at") or ""),
                "semantic_role": signal.signal_role,
                "transform": transform,
                "strength": signal.score,
                "usage_status": usage_status,
                "usage_reason": str(
                    metadata.get("usage_reason")
                    or signal.reason
                    or "declared_signal_role"
                ),
            }
        )
        return payload


@dataclass(slots=True)
class ConflictRecord:
    conflict_type: str
    scope: str
    severity: str
    title: str
    explanation: str
    resolution: str
    affected_horizons: list[str] = field(default_factory=list)
    involved_signals: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OperationCard:
    key: str
    title: str
    direction: str
    action_effect: str
    trading_meaning: str
    permission_effect: str
    position_effect: str
    next_check: str
    confidence: float
    next_check_at_iso: str = ""
    source_modules: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    key_levels: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GovernanceCard:
    key: str
    title: str
    instruction: str
    allowed_actions: list[str]
    blocked_actions: list[str]
    upgrade_path: list[str]
    invalidation_path: list[str]
    position_cap: str
    source_timeframes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DirectionResolutionResult:
    unified_code: str
    strategic_direction: str
    tactical_direction: str
    execution_direction: str
    permission: str
    position_cap: str
    risk_level: str
    instruction: str
    allowed_actions: list[str]
    blocked_actions: list[str]
    operation_cards: list[OperationCard]
    governance_cards: list[GovernanceCard]
    conflicts: list[ConflictRecord]
    next_check: str
    next_check_at_iso: str = ""
    trade_plan_inputs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "unified_code": self.unified_code,
            "strategic_direction": self.strategic_direction,
            "tactical_direction": self.tactical_direction,
            "execution_direction": self.execution_direction,
            "permission": self.permission,
            "position_cap": self.position_cap,
            "risk_level": self.risk_level,
            "instruction": self.instruction,
            "allowed_actions": list(self.allowed_actions),
            "blocked_actions": list(self.blocked_actions),
            "operation_cards": [card.as_dict() for card in self.operation_cards],
            "governance_cards": [card.as_dict() for card in self.governance_cards],
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "next_check": self.next_check,
            "next_check_at_iso": self.next_check_at_iso,
            "trade_plan_inputs": dict(self.trade_plan_inputs),
        }


class DirectionResolutionEngine:
    def resolve(
        self,
        *,
        signals: Sequence[ModuleSignal | Mapping[str, Any]],
        next_check: str = "next_4h_close",
        next_check_at_iso: str = "",
    ) -> DirectionResolutionResult:
        from datetime import datetime, timezone

        from .trade_decision import _next_close_iso

        normalized = [coerce_signal(signal) for signal in signals]
        # Resolve a canonical ISO next-check once for this build. If the
        # caller already supplied an absolute timestamp, trust it; otherwise
        # derive the next 4H bar close from wall clock.
        if not next_check_at_iso:
            next_check_at_iso = (
                next_check
                if "T" in str(next_check)
                else _next_close_iso(datetime.now(timezone.utc), "4h")
            )
        conflicts: list[ConflictRecord] = []
        blocker = self._blocking_conflict(normalized)
        if blocker:
            conflicts.append(blocker)
            operation_cards = self._operation_cards(normalized)
            governance_cards = self._governance_cards("NEUTRAL", "NEUTRAL", "BLOCK", "no_trade", [], ["暂停新开仓", "暂停提高杠杆", "等待事件落地或核心数据补齐"])
            code = "EVENT_LOCKED" if blocker.conflict_type == "event_window_block" else "DATA_DEGRADED"
            return DirectionResolutionResult(
                unified_code=code,
                strategic_direction="NEUTRAL",
                tactical_direction="NEUTRAL",
                execution_direction="BLOCK",
                permission="no_trade",
                position_cap="no_trade",
                risk_level="high",
                instruction=blocker.resolution,
                allowed_actions=[],
                blocked_actions=["暂停新开仓", "暂停提高杠杆", "等待事件落地或核心数据补齐"],
                operation_cards=operation_cards,
                governance_cards=governance_cards,
                conflicts=conflicts,
                next_check=next_check,
                next_check_at_iso=next_check_at_iso,
                trade_plan_inputs={"mode": "no_trade"},
            )

        strategic = self._weighted_direction(normalized, "strategic")
        tactical = self._weighted_direction(normalized, "tactical")
        execution_signal = self._weighted_direction(normalized, "execution")
        execution = self._execution_direction(execution_signal, tactical)
        conflicts.extend(self._same_module_conflicts(normalized))
        conflicts.extend(self._cross_horizon_conflicts(strategic, tactical, normalized))

        position_cap = self._position_cap(strategic, tactical)
        permission = "observe" if position_cap == "observe" else "conditional"
        allowed, blocked = self._actions(strategic, tactical, execution, position_cap)
        code = self._unified_code(strategic, tactical)
        operation_cards = self._operation_cards(normalized)
        governance_cards = self._governance_cards(strategic, tactical, execution, position_cap, allowed, blocked)
        instruction = self._instruction(code, position_cap, permission)
        return DirectionResolutionResult(
            unified_code=code,
            strategic_direction=strategic,
            tactical_direction=tactical,
            execution_direction=execution,
            permission=permission,
            position_cap=position_cap,
            risk_level="medium" if position_cap in {"reduced", "observe"} else "low",
            instruction=instruction,
            allowed_actions=allowed,
            blocked_actions=blocked,
            operation_cards=operation_cards,
            governance_cards=governance_cards,
            conflicts=conflicts,
            next_check=next_check,
            next_check_at_iso=next_check_at_iso,
            trade_plan_inputs={
                "strategic_direction": strategic,
                "tactical_direction": tactical,
                "execution_direction": execution,
                "position_cap": position_cap,
                "requires_legacy_plan": False,
            },
        )

    @staticmethod
    def _blocking_conflict(signals: Sequence[ModuleSignal]) -> ConflictRecord | None:
        blockers = [s for s in signals if s.action_effect == "block"]
        event_blockers = [s for s in blockers if s.module == "event" or s.signal_role == "event_lock"]
        if event_blockers:
            return ConflictRecord(
                conflict_type="event_window_block",
                scope="global",
                severity="blocker",
                title="高影响事件窗口",
                explanation="事件窗口会让方向信号失真，不能用普通多空模型直接开仓。",
                resolution="暂停新开仓，等待事件落地后至少一根 4H 收盘确认。",
                affected_horizons=["tactical", "execution"],
                involved_signals=[s.as_dict() for s in event_blockers],
            )
        data_blockers = [s for s in blockers if s.module == "data" or s.signal_role == "data_quality"]
        if data_blockers:
            return ConflictRecord(
                conflict_type="data_quality_block",
                scope="global",
                severity="blocker",
                title="核心数据不足",
                explanation="核心周期或关键数据缺失时，系统不能给出可靠执行方向。",
                resolution="等待核心周期、宏观或衍生品数据补齐后再恢复交易权限。",
                affected_horizons=["strategic", "tactical", "execution"],
                involved_signals=[s.as_dict() for s in data_blockers],
            )
        return None

    @staticmethod
    def _weighted_direction(signals: Sequence[ModuleSignal], horizon: str) -> str:
        scoped = [s for s in signals if s.horizon == horizon and s.confidence > 0]
        long_score = grouped_effective_weight(scoped, "LONG")
        short_score = grouped_effective_weight(scoped, "SHORT")
        if long_score >= 42 and long_score - short_score >= 6:
            return "LONG"
        if short_score >= 42 and short_score - long_score >= 6:
            return "SHORT"
        return "NEUTRAL"

    @staticmethod
    def _execution_direction(execution_signal: str, tactical: str) -> str:
        if tactical == "LONG":
            return "WAIT_LONG_TRIGGER"
        if tactical == "SHORT":
            return "WAIT_SHORT_TRIGGER"
        return "WAIT"

    @staticmethod
    def _same_module_conflicts(signals: Sequence[ModuleSignal]) -> list[ConflictRecord]:
        conflicts: list[ConflictRecord] = []
        by_module: dict[str, list[ModuleSignal]] = {}
        for signal in signals:
            by_module.setdefault(signal.module, []).append(signal)
        for module, items in by_module.items():
            long_items = [s for s in items if s.direction == "LONG" and s.confidence >= 45]
            short_items = [s for s in items if s.direction == "SHORT" and s.confidence >= 45]
            if long_items and short_items:
                conflicts.append(
                    ConflictRecord(
                        conflict_type="same_module_direction_conflict",
                        scope=module,
                        severity="warning",
                        title=f"{MODULE_TITLES.get(module, module)}内部多空冲突",
                        explanation="同一模块同时出现多头和空头证据，不能压缩成单一 bias。",
                        resolution="该模块只参与降权或确认，不能单独触发交易。",
                        affected_horizons=sorted({s.horizon for s in items}),
                        involved_signals=[s.as_dict() for s in [*long_items[:2], *short_items[:2]]],
                    )
                )
        return conflicts

    @staticmethod
    def _cross_horizon_conflicts(strategic: str, tactical: str, signals: Sequence[ModuleSignal]) -> list[ConflictRecord]:
        if strategic in {"LONG", "SHORT"} and tactical in {"LONG", "SHORT"} and strategic != tactical:
            title = "短空长多" if strategic == "LONG" else "短多长空"
            resolution = "高周期定义仓位上限和长期边界，1d/4h 定义未来数日至数周的战术方向，1h/15m 只负责触发和过滤。"
            return [
                ConflictRecord(
                    conflict_type="cross_horizon_direction_conflict",
                    scope="horizon",
                    severity="info",
                    title=title,
                    explanation="高周期方向与日线/4H 战术方向相反，不能平均成中性。",
                    resolution=resolution,
                    affected_horizons=["strategic", "tactical", "execution"],
                    involved_signals=[s.as_dict() for s in signals if s.horizon in {"strategic", "tactical"}],
                )
            ]
        return []

    @staticmethod
    def _position_cap(strategic: str, tactical: str) -> str:
        if strategic in {"LONG", "SHORT"} and tactical in {"LONG", "SHORT"} and strategic != tactical:
            return "reduced"
        if tactical in {"LONG", "SHORT"}:
            return "standard"
        return "observe"

    @staticmethod
    def _unified_code(strategic: str, tactical: str) -> str:
        if strategic == "LONG" and tactical == "LONG":
            return "STRATEGIC_LONG_TACTICAL_LONG"
        if strategic == "LONG" and tactical == "SHORT":
            return "STRATEGIC_LONG_TACTICAL_SHORT"
        if strategic == "SHORT" and tactical == "SHORT":
            return "STRATEGIC_SHORT_TACTICAL_SHORT"
        if strategic == "SHORT" and tactical == "LONG":
            return "STRATEGIC_SHORT_TACTICAL_LONG"
        return "RANGE_NO_EDGE"

    @staticmethod
    def _actions(strategic: str, tactical: str, execution: str, position_cap: str) -> tuple[list[str], list[str]]:
        allowed: list[str] = []
        blocked: list[str] = []
        if position_cap == "observe":
            return ["等待关键结构突破或回踩确认"], ["方向优势不足，暂不建立主动仓位"]
        if strategic == "LONG":
            allowed.append("长期仓位允许分批关注，但短线必须服从价格结构")
        if strategic == "SHORT":
            allowed.append("长期风险敞口保持克制，短线反弹只按反弹处理")
        if tactical == "LONG":
            allowed.append("等待 4H/1H 突破回踩或支撑反转后执行多头计划")
            blocked.append("1h/15m 单独看多不能推翻日线或4H结构")
        if tactical == "SHORT":
            allowed.append("等待 4H/1H 反抽失败或关键支撑跌破后执行空头计划")
            blocked.append("1h/15m 单独反弹不能推翻日线或4H空头结构")
        if position_cap == "reduced":
            blocked.append("跨周期冲突解除前禁止一次性重仓")
        if execution == "WAIT":
            blocked.append("执行层没有触发，禁止提前开仓")
        return allowed, blocked

    @staticmethod
    def _instruction(unified_code: str, position_cap: str, permission: str) -> str:
        mapping = {
            "STRATEGIC_LONG_TACTICAL_LONG": "高周期和战术周期同向看多，等待执行层突破回踩或支撑反转确认。",
            "STRATEGIC_LONG_TACTICAL_SHORT": "长期背景偏多，但日线/4H 偏空；短中期优先空头或等待空头结构失效，仓位降级。",
            "STRATEGIC_SHORT_TACTICAL_SHORT": "高周期和战术周期同向看空，反弹压力失败后空头计划优先。",
            "STRATEGIC_SHORT_TACTICAL_LONG": "高周期压制下的战术反弹，只按短线处理，不能升级为长期反转。",
            "RANGE_NO_EDGE": "多周期方向优势不足，等待区间突破或关键结构确认。",
        }
        suffix = " 当前权限为观察。" if permission == "observe" else ""
        if position_cap == "reduced":
            suffix = " 当前仓位上限为 reduced，只允许轻仓或分批执行。"
        return mapping.get(unified_code, "等待统一策略重新计算。") + suffix

    def _operation_cards(self, signals: Sequence[ModuleSignal]) -> list[OperationCard]:
        from datetime import datetime, timezone

        from .trade_decision import _next_close_iso

        now = datetime.now(timezone.utc)
        cards: list[OperationCard] = []
        for module in ("macro", "capital_flow", "technical", "derivatives", "onchain", "price_structure", "event", "data"):
            items = [s for s in signals if s.module == module]
            if not items:
                continue
            direction = self._module_direction(items)
            action_effect = self._module_action_effect(items)
            levels: dict[str, float] = {}
            for item in items:
                levels.update(item.key_levels)
            confidence = round(sum(s.confidence for s in items) / max(len(items), 1), 2)
            cards.append(
                OperationCard(
                    key=module,
                    title=MODULE_TITLES.get(module, module),
                    direction=direction,
                    action_effect=action_effect,
                    trading_meaning=module_trading_meaning(module, direction, action_effect, items),
                    permission_effect=permission_effect(action_effect),
                    position_effect=position_effect(action_effect),
                    next_check=next_check_for_module(module, action_effect),
                    next_check_at_iso=_next_close_iso(now, _MODULE_CHECK_TIMEFRAME.get(module, "4h")),
                    confidence=confidence,
                    source_modules=sorted({s.source_module or s.module for s in items}),
                    evidence=[s.reason for s in items if s.reason][:4],
                    key_levels=levels,
                )
            )
        if not cards:
            cards.append(
                OperationCard(
                    key="data",
                    title="数据质量",
                    direction="NEUTRAL",
                    action_effect="observe",
                    trading_meaning="缺少可裁决信号，策略页保持观察。",
                    permission_effect="observe",
                    position_effect="observe",
                    next_check="等待数据补齐",
                    next_check_at_iso=_next_close_iso(now, "1h"),
                    confidence=0,
                )
            )
        return cards

    @staticmethod
    def _module_direction(items: Sequence[ModuleSignal]) -> str:
        long_score = sum(effective_weight(s) for s in items if s.direction == "LONG")
        short_score = sum(effective_weight(s) for s in items if s.direction == "SHORT")
        if long_score >= 42 and long_score - short_score >= 6:
            return "LONG"
        if short_score >= 42 and short_score - long_score >= 6:
            return "SHORT"
        return "NEUTRAL"

    @staticmethod
    def _module_action_effect(items: Sequence[ModuleSignal]) -> str:
        effects = [s.action_effect for s in items]
        for effect in ("block", "downgrade", "confirm", "support", "level_only"):
            if effect in effects:
                return effect
        return "observe"

    @staticmethod
    def _governance_cards(strategic: str, tactical: str, execution: str, position_cap: str, allowed: list[str], blocked: list[str]) -> list[GovernanceCard]:
        upgrade = [
            "1H 连续收盘确认触发方向，且 15M 回踩不快速失效。",
            "4H 收盘确认关键结构位后，战术计划才升级。",
            "1D 收盘改写结构后，才允许上调周期级别和仓位上限。",
        ]
        invalidation = [
            "执行触发后 15M 快速反向收回触发位，撤销本次执行信号。",
            "4H 或 1D 收盘穿越反向关键结构位，原战术方向失效。",
            "宏观事件或核心数据缺失触发门禁，暂停新开仓。",
        ]
        if tactical == "SHORT":
            tactical_instruction = "1d/4h 偏空，等待反抽失败或关键支撑跌破；低周期反弹只能作为过滤，不能改写日线方向。"
        elif tactical == "LONG":
            tactical_instruction = "1d/4h 偏多，等待突破回踩或支撑反转；低周期回落只能作为触发过滤，不能改写日线方向。"
        else:
            tactical_instruction = "1d/4h 未形成战术优势，等待关键结构位确认。"
        return [
            GovernanceCard(
                key="higher_tf",
                title="高周期约束",
                instruction=f"1M/1w 当前为{DIRECTION_LABELS.get(strategic, strategic)}；它决定长期边界和仓位上限，不直接触发短线入场。",
                allowed_actions=allowed,
                blocked_actions=blocked,
                upgrade_path=upgrade,
                invalidation_path=invalidation,
                position_cap=position_cap,
                source_timeframes=["1M", "1w"],
            ),
            GovernanceCard(
                key="tactical_tf",
                title="战术周期计划",
                instruction=tactical_instruction,
                allowed_actions=allowed,
                blocked_actions=blocked,
                upgrade_path=upgrade,
                invalidation_path=invalidation,
                position_cap=position_cap,
                source_timeframes=["1d", "4h"],
            ),
            GovernanceCard(
                key="execution_tf",
                title="执行层触发",
                instruction=f"4H/1H/15M 当前为{DIRECTION_LABELS.get(execution, execution)}；只负责触发、过滤和失败确认。",
                allowed_actions=allowed,
                blocked_actions=blocked,
                upgrade_path=upgrade,
                invalidation_path=invalidation,
                position_cap=position_cap,
                source_timeframes=["4h", "1h", "15m"],
            ),
        ]


def derivatives_subsignals_from_features(features: Mapping[str, Any] | None, *, asset_lens: str = "btc_perp") -> list[ModuleSignal]:
    features = features or {}
    signals: list[ModuleSignal] = []
    funding_state = str(features.get("funding_state") or "").lower()
    if funding_state in {"positive_hot", "funding_positive_hot", "long_crowded"}:
        signals.append(
            ModuleSignal("derivatives", "funding_rate", "tactical", "4h", "NEUTRAL", "crowding", "downgrade", asset_lens, 45, 70, "fresh", "Funding is positive-hot: long crowding risk, not a long confirmation.", "btc_derivatives", "DerivativesRegimeEngine")
        )
    elif funding_state in {"negative_hot", "funding_negative_hot", "short_crowded"}:
        signals.append(
            ModuleSignal("derivatives", "funding_rate", "tactical", "4h", "NEUTRAL", "crowding", "downgrade", asset_lens, 45, 70, "fresh", "Funding is negative-hot: short crowding and squeeze risk, not a short confirmation.", "btc_derivatives", "DerivativesRegimeEngine")
        )

    oi_state = str(features.get("oi_state") or features.get("price_oi_state") or "").lower()
    oi_map = {
        "buildup_long": ("LONG", "Price rises with OI expansion; derivatives confirm long continuation."),
        "price_up_oi_up": ("LONG", "Price rises with OI expansion; derivatives confirm long continuation."),
        "buildup_short": ("SHORT", "Price falls with OI expansion; derivatives confirm short pressure."),
        "price_down_oi_up": ("SHORT", "Price falls with OI expansion; derivatives confirm short pressure."),
        "long_unwind": ("SHORT", "Price falls with OI contraction; long deleveraging downgrades long quality."),
        "price_down_oi_down": ("SHORT", "Price falls with OI contraction; long deleveraging downgrades long quality."),
        "short_covering": ("LONG", "Price rises with OI contraction; short covering is rebound support, not trend confirmation."),
        "price_up_oi_down": ("LONG", "Price rises with OI contraction; short covering is rebound support, not trend confirmation."),
    }
    if oi_state in oi_map:
        direction, reason = oi_map[oi_state]
        effect = (
            "confirm"
            if oi_state in {
                "buildup_long",
                "buildup_short",
                "price_up_oi_up",
                "price_down_oi_up",
            }
            else "downgrade"
        )
        signals.append(ModuleSignal("derivatives", "open_interest", "tactical", "4h", direction, "derivatives_confirmation", effect, asset_lens, 64, 72, "fresh", reason, "btc_derivatives", "DerivativesRegimeEngine"))

    skew_state = str(features.get("skew_state") or "").lower()
    if skew_state in {"call_skew_high", "put_skew_high"}:
        direction = "LONG" if skew_state == "call_skew_high" else "SHORT"
        signals.append(
            ModuleSignal(
                "derivatives",
                "skew_25d",
                "tactical",
                "4h",
                direction,
                "derivatives_confirmation",
                "confirm",
                asset_lens,
                58,
                60,
                "fresh",
                "25D skew is confirmation only and cannot trigger direction without price structure.",
                "btc_derivatives",
                "DerivativesRegimeEngine",
                metadata={
                    "transform": "asymmetric_confirmation_band",
                    "signal_family": "options_sentiment",
                    "observed_at": str(features.get("data_timestamp") or ""),
                },
            )
        )

    ratios = features.get("put_call_ratios") if isinstance(features.get("put_call_ratios"), Mapping) else {}
    put_call_oi = first_float(ratios.get("put_call_oi_ratio"))
    if put_call_oi is not None:
        direction = "SHORT" if put_call_oi >= 1.2 else "LONG" if put_call_oi <= 0.8 else "NEUTRAL"
        signals.append(
            ModuleSignal(
                "derivatives",
                "put_call_oi_ratio",
                "tactical",
                "4h",
                direction,
                "derivatives_confirmation",
                "confirm" if direction != "NEUTRAL" else "observe",
                asset_lens,
                56,
                55,
                "fresh",
                "Put/Call OI uses asymmetric confirmation bands and never triggers alone.",
                "btc_derivatives",
                "DerivativesRegimeEngine",
                metadata={
                    "transform": "asymmetric_ratio_band",
                    "signal_family": "options_sentiment",
                    "observed_at": str(features.get("data_timestamp") or ""),
                },
            )
        )

    hedge_cost_state = str(features.get("hedge_cost_state") or "").lower()
    if hedge_cost_state:
        signals.append(
            ModuleSignal(
                "derivatives",
                "protection_cost",
                "risk_filter",
                "4h",
                "NEUTRAL",
                "volatility",
                "observe",
                asset_lens,
                50,
                60,
                "fresh",
                "Protection cost affects risk and position size, not market direction.",
                "btc_derivatives",
                "DerivativesRegimeEngine",
                metadata={
                    "transform": "risk_only_regime_bucket",
                    "signal_family": "options_risk",
                    "usage_status": "diagnostic",
                    "usage_reason": "risk_only_not_directional",
                    "observed_at": str(features.get("data_timestamp") or ""),
                },
            )
        )

    basis_state = str(features.get("basis_state") or "").lower()
    if basis_state in {"basis_rising", "basis_falling"}:
        signals.append(
            ModuleSignal(
                "derivatives",
                "basis",
                "tactical",
                "4h",
                "LONG" if basis_state == "basis_rising" else "SHORT",
                "derivatives_confirmation",
                "confirm",
                asset_lens,
                54,
                52,
                "fresh",
                "Basis is confirmation only; price structure remains the direction authority.",
                "btc_derivatives",
                "DerivativesRegimeEngine",
                metadata={
                    "transform": "state_gate_confirmation_only",
                    "signal_family": "futures_positioning",
                    "observed_at": str(features.get("data_timestamp") or ""),
                },
            )
        )

    axis = features.get("key_levels_axis") if isinstance(features.get("key_levels_axis"), Mapping) else {}
    for key, aliases in {
        "call_wall": ("call_wall", "call_wall_strike"),
        "put_wall": ("put_wall", "put_wall_strike"),
        "max_pain": ("max_pain", "max_pain_strike"),
    }.items():
        level = first_float(
            *(axis.get(alias) for alias in aliases),
            *(features.get(alias) for alias in aliases),
        )
        if level is not None:
            signals.append(
                ModuleSignal(
                    "derivatives",
                    key,
                    "tactical",
                    "4h",
                    "NEUTRAL",
                    "key_level",
                    "level_only",
                    asset_lens,
                    50,
                    65,
                    "fresh",
                    f"{key} is a reference level; it does not define direction until price follows.",
                    "btc_derivatives",
                    "DerivativesRegimeEngine",
                    {key: level},
                )
            )
    return [signal.normalized() for signal in signals]


def coerce_signal(item: ModuleSignal | Mapping[str, Any]) -> ModuleSignal:
    if isinstance(item, ModuleSignal):
        return item.normalized()
    payload = dict(item or {})
    return ModuleSignal(
        module=str(payload.get("module") or "unknown"),
        indicator_key=str(payload.get("indicator_key") or payload.get("key") or "unknown"),
        asset_lens=str(payload.get("asset_lens") or "btc_perp"),
        horizon=str(payload.get("horizon") or "risk_filter"),
        window=str(payload.get("window") or payload.get("timeframe") or "unknown"),
        direction=str(payload.get("direction") or "NEUTRAL"),
        signal_role=str(payload.get("signal_role") or payload.get("role") or "data_quality"),
        action_effect=str(payload.get("action_effect") or "observe"),
        score=to_float(payload.get("score"), 50.0),
        confidence=to_float(payload.get("confidence"), 50.0),
        freshness=str(payload.get("freshness") or "unknown"),
        reason=str(payload.get("reason") or payload.get("trading_meaning") or ""),
        source_page=str(payload.get("source_page") or ""),
        source_module=str(payload.get("source_module") or payload.get("module") or ""),
        key_levels=dict(payload.get("key_levels") or {}),
        metadata=dict(payload.get("metadata") or {}),
    ).normalized()


def module_trading_meaning(module: str, direction: str, effect: str, items: Sequence[ModuleSignal]) -> str:
    if module == "technical":
        if effect == "downgrade":
            return "技术指标处于极值或高波动区，只降低执行质量，不直接反向开仓。"
        if direction == "LONG":
            return "技术趋势与动量支持多头，但仍需日线/4H结构许可。"
        if direction == "SHORT":
            return "技术趋势与动量支持空头，但仍需日线/4H结构许可。"
        return "技术指标未形成一致方向，仅保留诊断和风险信息。"
    if module == "macro":
        if effect == "block":
            return "宏观事件或流动性冲击触发，新开仓权限下调。"
        if direction == "LONG":
            return "宏观环境对风险资产更友好，但短线入场仍必须服从价格结构。"
        if direction == "SHORT":
            return "宏观环境压制风险偏好，短线多头权限需要降级。"
        return "宏观层未形成单边优势，等待利率、美元和事件窗口确认。"
    if module == "derivatives":
        if effect == "level_only":
            return "衍生品只提供关键价位，不单独定义方向。"
        if effect == "downgrade":
            return "衍生品显示拥挤或确认不足，降低追价和仓位质量。"
        if direction == "LONG":
            return "衍生品确认多头延续，但仍需要价格突破或回踩确认。"
        if direction == "SHORT":
            return "衍生品确认空头压力，但仍需要价格结构同步触发。"
    if module == "capital_flow":
        if direction == "LONG":
            return "资金流支持配置或趋势延续，但不直接触发入场。"
        if direction == "SHORT":
            return "资金流偏流出或风险资产广度转弱，配置置信下调。"
        return "资金流输入不足或分歧较大，暂不参与强方向加权。"
    if module == "onchain":
        if not any(item.confidence > 0 for item in items):
            return "链上数据缺失，只降低战略置信度，不阻断短线价格结构计划。"
        if direction == "LONG":
            return "链上资金或筹码结构支持长期配置关注。"
        if direction == "SHORT":
            return "链上卖压或交易所流入增加，长期多头配置降级。"
        return "链上维度仅作战略观察，不触发短线交易。"
    if module == "price_structure":
        if direction == "LONG":
            return "价格结构支持战术多头，等待执行层触发。"
        if direction == "SHORT":
            return "价格结构支持战术空头，等待反抽失败或破位触发。"
        return "价格结构未形成可执行优势，等待关键结构位确认。"
    if module == "event":
        return "事件窗口优先影响权限，事件落地前降低新开仓优先级。"
    if module == "data":
        return "核心数据不足时不输出强执行方向。"
    return next((item.reason for item in items if item.reason), "该维度未形成可执行方向优势。")


def permission_effect(effect: str) -> str:
    return {
        "block": "no_trade",
        "downgrade": "conditional",
        "confirm": "can_confirm",
        "support": "can_support",
        "level_only": "observe_levels",
    }.get(effect, "observe")


def position_effect(effect: str) -> str:
    return {
        "block": "no_trade",
        "downgrade": "reduce",
        "confirm": "allow_standard_after_trigger",
        "support": "support_existing_plan",
        "level_only": "no_size_change",
    }.get(effect, "observe")


def next_check_for_module(module: str, effect: str) -> str:
    if module == "macro":
        return "等待下一次宏观数据或事件窗口更新"
    if module == "derivatives":
        return "等待 4H 价格与 OI/funding 同步确认"
    if module == "onchain":
        return "Waiting for onchain data refresh"
    if module == "price_structure":
        return "等待下一根 4H 或 1D 收盘确认"
    if module == "event":
        return "等待事件落地后的 4H 收盘"
    if module == "data" or effect == "block":
        return "等待核心数据补齐"
    return "等待下一轮统一策略刷新"


def effective_weight(signal: ModuleSignal) -> float:
    if signal.confidence <= 0:
        return 0.0
    effect = signal.action_effect
    role_factor = ROLE_FACTORS.get(signal.signal_role, 0.5)
    if effect in {"observe", "level_only"}:
        role_factor = min(role_factor, 0.3)
    if effect == "downgrade":
        role_factor = min(role_factor, 0.45)
    return signal.score * (signal.confidence / 100.0) * FRESHNESS_FACTORS.get(signal.freshness, 0.35) * role_factor


def grouped_effective_weight(
    signals: Sequence[ModuleSignal], direction: str, *, family_cap: float = 75.0
) -> float:
    """Cap correlated evidence families before combining independent families."""
    groups: dict[str, float] = {}
    for signal in signals:
        if signal.direction != direction:
            continue
        family = str(
            signal.metadata.get("signal_family")
            or f"{signal.module}:{signal.signal_role}"
        )
        groups[family] = min(
            family_cap, groups.get(family, 0.0) + effective_weight(signal)
        )
    return sum(groups.values())


def normalize_module(value: str) -> str:
    module = str(value or "unknown").lower()
    return {
        "macro_regime": "macro",
        "derivatives_regime": "derivatives",
        "onchain_regime": "onchain",
    }.get(module, module)


def normalize_horizon(value: str) -> str:
    horizon = str(value or "risk_filter").lower()
    if horizon in {"strategic", "tactical", "execution", "risk_filter"}:
        return horizon
    if horizon in {"1m", "30d", "1w"}:
        return "strategic"
    if horizon in {"1d", "4h", "tactical_execution"}:
        return "tactical"
    if horizon in {"1h", "15m"}:
        return "execution"
    return "risk_filter"


def normalize_direction(value: str) -> str:
    direction = str(value or "NEUTRAL").upper()
    if direction in {"LONG", "SHORT", "NEUTRAL", "WAIT", "WAIT_LONG_TRIGGER", "WAIT_SHORT_TRIGGER", "BLOCK"}:
        return direction
    if direction in {"BULLISH", "SUPPORTIVE"}:
        return "LONG"
    if direction in {"BEARISH", "RISK_OFF"}:
        return "SHORT"
    return "NEUTRAL"


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def first_float(*values: Any) -> float | None:
    for value in values:
        try:
            if value is None or value == "":
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
