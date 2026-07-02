# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import (
    EXECUTION_WEIGHTS,
    STRATEGIC_WEIGHTS,
    TACTICAL_WEIGHTS,
    HorizonGovernance,
    HorizonView,
    TimeframeNode,
    direction_from_scores,
    evidence_confidence,
    weighted,
)


class CrossHorizonSynthesisEngine:
    def build_horizon_views(self, nodes: Sequence[TimeframeNode]) -> dict[str, HorizonView]:
        strategic = self._view("strategic", "战略方向", "1Y-3Y", [n for n in nodes if n.timeframe in STRATEGIC_WEIGHTS], STRATEGIC_WEIGHTS)
        tactical = self._view("tactical", "战术方向", "1W-8W", [n for n in nodes if n.timeframe in TACTICAL_WEIGHTS], TACTICAL_WEIGHTS)
        execution = self._view("execution", "执行触发", "1D-5D", [n for n in nodes if n.timeframe in EXECUTION_WEIGHTS], EXECUTION_WEIGHTS)
        if execution.direction == "LONG":
            execution.direction = "WAIT_LONG_TRIGGER"
            execution.state = "EXECUTION_WAIT_LONG_TRIGGER"
            execution.instruction = "执行层等待多头触发；1H/15M 只用于突破回踩、支撑反转与追价过滤。"
        elif execution.direction == "SHORT":
            execution.direction = "WAIT_SHORT_TRIGGER"
            execution.state = "EXECUTION_WAIT_SHORT_TRIGGER"
            execution.instruction = "执行层等待空头触发；1H/15M 只用于反抽失败、破位确认与追空过滤。"
        else:
            execution.direction = "WAIT"
            execution.state = "EXECUTION_WAIT"
            execution.instruction = "执行层无有效触发，等待 4H/1H 结构确认。"
        return {"strategic": strategic, "tactical": tactical, "execution": execution}

    def build_governance(
        self,
        horizon_views: Mapping[str, HorizonView],
        nodes: Sequence[TimeframeNode],
    ) -> HorizonGovernance:
        strategic = horizon_views["strategic"]
        tactical = horizon_views["tactical"]
        execution = horizon_views["execution"]
        conflict = strategic.direction in {"LONG", "SHORT"} and tactical.direction in {"LONG", "SHORT"} and strategic.direction != tactical.direction
        if conflict:
            position_cap = "reduced"
            allowed_sides = [strategic.direction, tactical.direction]
        elif strategic.direction in {"LONG", "SHORT"}:
            position_cap = "standard"
            allowed_sides = [strategic.direction]
        else:
            position_cap = "observe"
            allowed_sides = []
        if strategic.direction == "NEUTRAL" and tactical.direction == "NEUTRAL":
            position_cap = "observe"
        return HorizonGovernance(
            higher_timeframe_constraint={
                "direction": strategic.direction,
                "source_timeframes": strategic.source_timeframes,
                "rule": "1M/1w 决定战略边界、允许方向与仓位上限。",
            },
            lower_timeframe_driver={
                "direction": execution.direction,
                "source_timeframes": execution.source_timeframes,
                "rule": "4H/1H/15M 只负责触发、过滤和推动上级结构升级，不单独推翻高周期。",
            },
            position_cap=position_cap,
            allowed_sides=allowed_sides,
            upgrade_path=[
                "1H 连续确认执行触发",
                "4H 收盘站回/跌破关键结构位",
                "1d 结构状态改写后重新计算战术方向",
            ],
            invalidation_path=[
                "执行触发后价格收回关键失效位",
                "1d 与 4H 同时转为相反结构",
                "宏观事件或数据门禁触发 no_trade",
            ],
        )

    def build_unified_state(
        self,
        horizon_views: Mapping[str, HorizonView],
        governance: HorizonGovernance,
        risk_alerts: Sequence[Mapping[str, Any]],
        nodes: Sequence[TimeframeNode],
        next_check_time: str | None,
    ) -> dict[str, Any]:
        strategic = horizon_views["strategic"]
        tactical = horizon_views["tactical"]
        if any(item["severity"] == "blocker" and item["category"] == "event" for item in risk_alerts):
            code = "EVENT_LOCKED"
        elif any(item["severity"] == "blocker" and item["category"] == "data" for item in risk_alerts):
            code = "DATA_DEGRADED"
        elif any(item["severity"] == "blocker" for item in risk_alerts):
            code = "RISK_OFF"
        elif strategic.direction == "LONG" and tactical.direction == "LONG":
            code = "STRATEGIC_LONG_TACTICAL_LONG"
        elif strategic.direction == "LONG" and tactical.direction == "SHORT":
            code = "STRATEGIC_LONG_TACTICAL_SHORT"
        elif strategic.direction == "SHORT" and tactical.direction == "SHORT":
            code = "STRATEGIC_SHORT_TACTICAL_SHORT"
        elif strategic.direction == "SHORT" and tactical.direction == "LONG":
            code = "STRATEGIC_SHORT_TACTICAL_LONG"
        else:
            code = "RANGE_NO_EDGE"
        labels = {
            "STRATEGIC_LONG_TACTICAL_LONG": "顺周期多头",
            "STRATEGIC_LONG_TACTICAL_SHORT": "短空长多",
            "STRATEGIC_SHORT_TACTICAL_SHORT": "顺周期空头",
            "STRATEGIC_SHORT_TACTICAL_LONG": "空头趋势中的战术反弹",
            "RANGE_NO_EDGE": "多周期震荡无优势",
            "EVENT_LOCKED": "事件锁定",
            "DATA_DEGRADED": "数据质量不足",
            "RISK_OFF": "风险关闭",
        }
        instructions = {
            "STRATEGIC_LONG_TACTICAL_LONG": "战略方向看多，战术方向看多，执行层等待回踩支撑或突破回踩确认。",
            "STRATEGIC_LONG_TACTICAL_SHORT": "战略方向看多，战术方向看空，长期分批关注，短中期优先执行空头计划。",
            "STRATEGIC_SHORT_TACTICAL_SHORT": "战略方向看空，战术方向看空，降低风险资产暴露，优先执行反弹压力失败空头计划。",
            "STRATEGIC_SHORT_TACTICAL_LONG": "战略方向看空，战术方向反弹，反弹只按短线处理，目标压制在高周期压力区。",
            "RANGE_NO_EDGE": "多周期方向优势不足，等待区间突破或关键结构确认。",
            "EVENT_LOCKED": "高影响事件窗口内暂停新开仓，事件落地后等待确认周期收盘。",
            "DATA_DEGRADED": "关键数据缺失或过期，策略权限下调，禁止输出强执行计划。",
            "RISK_OFF": "风险门禁触发，暂停新交易计划。",
        }
        permission = "no_trade" if code in {"EVENT_LOCKED", "DATA_DEGRADED", "RISK_OFF"} or governance.position_cap == "no_trade" else "conditional"
        if code == "RANGE_NO_EDGE":
            permission = "observe"
        risk_level = "high" if permission == "no_trade" else "medium" if governance.position_cap == "reduced" else "low"
        current_price = next((node.current_price for node in nodes if node.current_price is not None), None)
        return {
            "code": code,
            "label": labels[code],
            "instruction": instructions[code],
            "permission": permission,
            "risk_level": risk_level,
            "current_price": current_price,
            "primary_symbol": "BTC",
            "next_check_time": next_check_time or "next_4h_close",
        }

    def _view(
        self,
        key: str,
        label: str,
        horizon: str,
        nodes: Sequence[TimeframeNode],
        weights: Mapping[str, float],
    ) -> HorizonView:
        long_score = weighted(nodes, weights, "long_score")
        short_score = weighted(nodes, weights, "short_score")
        direction = direction_from_scores(long_score, short_score)
        evidence: list[str] = []
        source_modules: list[str] = []
        freshness_aggregate = "fresh"
        for node in nodes:
            evidence.extend(node.evidence)
            source_modules.extend(node.source_modules)
            if node.freshness in {"missing", "error"}:
                freshness_aggregate = "degraded"
            elif node.freshness in {"stale", "usable_stale"} and freshness_aggregate == "fresh":
                freshness_aggregate = "usable_stale"
        confidence = evidence_confidence(
            freshness=freshness_aggregate,
            consistency=1.0 if direction != "NEUTRAL" else 0.4,
            coverage=len(nodes) / max(len(weights), 1),
        )
        return HorizonView(
            key=key,
            label=label,
            horizon=horizon,
            source_timeframes=[node.timeframe for node in nodes],
            direction=direction,
            state=f"{key.upper()}_{direction}",
            instruction=self._instruction(key, direction),
            long_score=long_score,
            short_score=short_score,
            confidence=confidence,
            evidence=evidence[:6],
            source_modules=sorted(set(source_modules)) or ["MultiTimeframeStructureEngine"],
        )

    @staticmethod
    def _instruction(key: str, direction: str) -> str:
        if direction == "LONG":
            return f"{key} 层方向看多，等待下级周期确认执行条件。"
        if direction == "SHORT":
            return f"{key} 层方向看空，等待下级周期确认执行条件。"
        return f"{key} 层方向无优势，等待结构重新定价。"
