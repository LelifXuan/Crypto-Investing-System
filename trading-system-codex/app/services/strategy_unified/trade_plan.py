# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import (
    TIMEFRAME_SPECS,
    HorizonGovernance,
    HorizonView,
    TimeframeNode,
    TradePlan,
    as_mapping,
    first_float,
    list_floats,
    node_by_tf,
    price_zone,
)


class UnifiedTradePlanEngine:
    def build_plans(
        self,
        state: Mapping[str, Any],
        horizon_views: Mapping[str, HorizonView],
        governance: HorizonGovernance,
        nodes: Sequence[TimeframeNode],
        bundles: Mapping[str, Mapping[str, Any]],
    ) -> list[TradePlan]:
        if state.get("permission") == "no_trade" or governance.position_cap == "no_trade":
            return [self._no_trade_plan()]
        plans: list[TradePlan] = []
        strategic = horizon_views["strategic"]
        tactical = horizon_views["tactical"]
        execution = horizon_views["execution"]
        if strategic.direction == "LONG":
            plans.append(self._strategic_accumulation_plan(strategic, tactical, nodes, governance))
        elif strategic.direction == "SHORT":
            plans.append(self._strategic_risk_reduction_plan(strategic, nodes, governance))
        if tactical.direction in {"LONG", "SHORT"}:
            plans.append(self._tactical_trade_plan(tactical, execution, nodes, bundles, governance))
        else:
            plans.append(self._wait_range_plan(execution, nodes, governance))
        plans.append(self._execution_trigger_plan(execution, tactical, nodes, governance))
        return plans

    def _no_trade_plan(self) -> TradePlan:
        return TradePlan("no_trade", "NO_TRADE", "NO_TRADE", "禁止交易计划", "禁止交易计划", "NO_TRADE", "current", [s.logical for s in TIMEFRAME_SPECS], "风险门禁触发，当前不建立新交易计划。", [], None, [], "-", "解除风险门禁后重新计算统一策略。", "暂停新开仓。", "no_trade")

    def _strategic_accumulation_plan(self, strategic: HorizonView, tactical: HorizonView, nodes: Sequence[TimeframeNode], governance: HorizonGovernance) -> TradePlan:
        weekly = node_by_tf(nodes, "1w")
        daily = node_by_tf(nodes, "1d")
        invalidation_price = (
            (weekly.invalidation if weekly else None)
            or (weekly.key_support if weekly else None)
        )
        invalidation_text = (
            f"周线跌破 {invalidation_price:.2f} 长期支撑区并无法收回，长期多头计划终止。"
            if invalidation_price is not None
            else "周线跌破长期支撑区并无法收回，长期多头计划终止。"
        )
        return TradePlan(
            id="strategic_accumulation",
            type="STRATEGIC_ACCUMULATION",
            plan_type="STRATEGIC_ACCUMULATION",
            label="长期配置计划",
            title="长期配置计划",
            direction="LONG",
            horizon=strategic.horizon,
            source_timeframes=strategic.source_timeframes,
            entry_logic="周线支撑区分批关注；日线空头结构失效后提高配置权重。",
            entry_zone=price_zone(weekly.key_support if weekly else None, daily.key_support if daily else None),
            stop_loss=(weekly.invalidation if weekly else None) or (weekly.key_support if weekly else None),
            take_profit=[],
            take_profit_text="长期配置不设固定止盈，按周线结构和宏观风险重新评估。",
            invalidation=invalidation_text,
            position_rule="只使用现货或低杠杆；日线空头结构延续阶段只允许观察仓或分批关注。",
            permission="conditional" if tactical.direction == "SHORT" else "allow",
            evidence=strategic.evidence[:4],
            trigger={"required": "1d 空头结构失效或 4H 重新站回关键位"},
            risk_reward={"mode": "strategic"},
        )

    def _strategic_risk_reduction_plan(self, strategic: HorizonView, nodes: Sequence[TimeframeNode], governance: HorizonGovernance) -> TradePlan:
        weekly = node_by_tf(nodes, "1w")
        return TradePlan("strategic_risk_reduction", "STRATEGIC_RISK_REDUCTION", "STRATEGIC_RISK_REDUCTION", "长期降风险计划", "长期降风险计划", "SHORT", strategic.horizon, strategic.source_timeframes, "高周期看空时降低风险资产净暴露。", price_zone(weekly.key_resistance if weekly else None), weekly.key_resistance if weekly else None, [], "按周线压力区滚动复核。", "周线收回压力区并连续确认。", "不提高风险预算；反弹只作为减仓或对冲窗口。", "conditional", strategic.evidence[:4])

    def _tactical_trade_plan(self, tactical: HorizonView, execution: HorizonView, nodes: Sequence[TimeframeNode], bundles: Mapping[str, Mapping[str, Any]], governance: HorizonGovernance) -> TradePlan:
        side = "short" if tactical.direction == "SHORT" else "long"
        legacy = self._legacy_plan(bundles, side=side)
        daily = node_by_tf(nodes, "1d")
        h4 = node_by_tf(nodes, "4h")
        take_profit = [
            {"label": "TP1", "price": first_float(legacy.get("take_profit_1"))},
            {"label": "TP2", "price": first_float(legacy.get("take_profit_2"))},
        ]
        take_profit = [item for item in take_profit if item["price"] is not None]
        if not take_profit:
            anchor = (
                h4.key_resistance
                if tactical.direction == "LONG" and h4 and h4.key_resistance
                else h4.key_support
                if tactical.direction == "SHORT" and h4 and h4.key_support
                else None
            )
            if anchor is not None:
                take_profit = [{"label": "TP1", "price": float(anchor)}]
        stop_loss = first_float(legacy.get("stop_price"), legacy.get("stop_loss"), daily.invalidation if daily else None)
        entry_zone = list_floats(legacy.get("entry_zone") or legacy.get("entry_price_range")) or price_zone(h4.key_support if h4 else None, h4.key_resistance if h4 else None)
        invalidation_price = stop_loss or (h4.key_support if tactical.direction == "LONG" else h4.key_resistance if h4 else None)
        invalidation_text = (
            f"4H 收盘跌破 {invalidation_price:.2f} 战术支撑位，或日线方向重新回到高周期同向。"
            if invalidation_price is not None
            else "4H 收盘越过战术结构失效位，或日线方向重新回到高周期同向。"
        )
        plan_type = f"TACTICAL_{tactical.direction}"
        return TradePlan(
            id=plan_type.lower(),
            type=plan_type,
            plan_type=plan_type,
            label="短中期战术交易计划",
            title="短中期战术交易计划",
            direction=tactical.direction,
            horizon=tactical.horizon,
            source_timeframes=tactical.source_timeframes,
            entry_logic=str(legacy.get("entry_condition") or legacy.get("entry_logic") or "等待 4H 收盘确认。"),
            entry_zone=entry_zone,
            stop_loss=stop_loss,
            take_profit=take_profit,
            take_profit_text=" / ".join(f"{item['label']} {item['price']:.2f}" for item in take_profit) or "等待价格结构生成目标位。",
            invalidation=invalidation_text,
            position_rule="战略/战术冲突时只允许降仓位条件执行；顺周期时可使用标准战术风险预算。",
            permission="conditional",
            evidence=tactical.evidence[:4],
            trigger={"execution_direction": execution.direction},
            risk_reward={"legacy_rr": legacy.get("risk_reward_ratio")},
        )

    def _wait_range_plan(self, execution: HorizonView, nodes: Sequence[TimeframeNode], governance: HorizonGovernance) -> TradePlan:
        return TradePlan("wait_range", "WAIT_RANGE", "WAIT_RANGE", "区间等待计划", "区间等待计划", "NEUTRAL", "1W-8W", execution.source_timeframes, "多周期方向优势不足，等待区间突破或关键结构确认。", [], None, [], "-", "任一高周期重新形成明确方向后失效。", "不主动开新方向仓位。", "observe", execution.evidence[:3])

    def _execution_trigger_plan(self, execution: HorizonView, tactical: HorizonView, nodes: Sequence[TimeframeNode], governance: HorizonGovernance) -> TradePlan:
        h1 = node_by_tf(nodes, "1h")
        return TradePlan("execution_trigger", "EXECUTION_TRIGGER", "EXECUTION_TRIGGER", "执行触发计划", "执行触发计划", execution.direction, execution.horizon, execution.source_timeframes, "1H 给出方向触发，15M 只用于过滤追价和确认入场质量。", price_zone(h1.key_support if h1 else None, h1.key_resistance if h1 else None), h1.invalidation if h1 else None, [], "执行触发计划不单独设置止盈，跟随战术计划。", "15M 触发后快速收回触发位，或 1H 收盘反向。", "执行层不提高仓位上限，只决定是否触发战术计划。", "conditional", execution.evidence[:4], {"filter_timeframe": "15m", "confirm_timeframe": "1h"}, {"mode": "execution_filter"})

    @staticmethod
    def _legacy_plan(bundles: Mapping[str, Mapping[str, Any]], *, side: str) -> dict[str, Any]:
        key = "short_plan" if side == "short" else "long_plan"
        for tf in ("4h", "1d", "1h"):
            decision = as_mapping(as_mapping(bundles.get(tf)).get("decision"))
            plan = as_mapping(decision.get(key)) or as_mapping(decision.get("primary_strategy"))
            if plan:
                return plan
        return {}
