# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import HorizonView, RiskAlert, TradePlan


def _cn_direction(direction: str) -> str:
    mapping = {
        "LONG": "看多",
        "SHORT": "看空",
        "NEUTRAL": "中性",
        "WAIT": "等待",
        "WAIT_LONG_TRIGGER": "等待多头触发",
        "WAIT_SHORT_TRIGGER": "等待空头触发",
        "NO_TRADE": "不交易",
    }
    return mapping.get(direction, direction or "-")


def _direction_action(direction: str) -> str:
    if direction == "LONG":
        return "看多"
    if direction == "SHORT":
        return "看空"
    if direction == "WAIT_SHORT_TRIGGER":
        return "等待空头触发"
    if direction == "WAIT_LONG_TRIGGER":
        return "等待多头触发"
    if direction == "WAIT":
        return "等待触发"
    return "观察"


def _state_label(state: Mapping[str, object]) -> str:
    code = str(state.get("code") or "")
    mapping = {
        "STRATEGIC_LONG_TACTICAL_LONG": "顺周期多头",
        "STRATEGIC_LONG_TACTICAL_SHORT": "短空长多",
        "STRATEGIC_SHORT_TACTICAL_SHORT": "顺周期空头",
        "STRATEGIC_SHORT_TACTICAL_LONG": "空头趋势中的战术反弹",
        "RANGE_NO_EDGE": "多周期震荡无优势",
        "EVENT_LOCKED": "事件锁定",
        "DATA_DEGRADED": "数据质量不足",
        "RISK_OFF": "风险关闭",
    }
    return mapping.get(code) or str(state.get("label") or code or "统一策略")


def _fmt_score(view: HorizonView) -> str:
    return f"多 {view.long_score:.0f} / 空 {view.short_score:.0f}，置信度 {view.confidence:.0f}"


def _clean_evidence(items: Sequence[str], *, fallback: str) -> str:
    cleaned: list[str] = []
    for item in items:
        text = _humanize_evidence(str(item or "").strip())
        if not text or text in cleaned:
            continue
        cleaned.append(text)
    return "；".join(cleaned[:2]) if cleaned else fallback


def _humanize_evidence(text: str) -> str:
    if not text:
        return ""
    if text == "Market context fallback supplied usable structure scores.":
        return "市场上下文提供了可用的结构分数。"
    if "context state=CONTEXT_LONG" in text:
        return text.split(" context state=", 1)[0].upper() + " 市场上下文偏多。"
    if "context state=CONTEXT_SHORT" in text:
        return text.split(" context state=", 1)[0].upper() + " 市场上下文偏空。"
    if "context state=CONTEXT_NEUTRAL" in text:
        return text.split(" context state=", 1)[0].upper() + " 市场上下文中性。"
    if any(token in text for token in ("CONTEXT_", "fallback", "raw_status", "cache_state")):
        return ""
    return text


def _plan_by_type(plans: Sequence[TradePlan], plan_type: str) -> TradePlan | None:
    for plan in plans:
        if plan.type == plan_type or plan.plan_type == plan_type:
            return plan
    return None


class NarrativeRenderer:
    def render(
        self,
        state: Mapping[str, object],
        horizon_views: Mapping[str, HorizonView],
        trade_plans: Sequence[TradePlan],
        risk_alerts: Sequence[RiskAlert],
        market_operation: Mapping[str, object],
    ) -> dict[str, Any]:
        strategic = horizon_views["strategic"]
        tactical = horizon_views["tactical"]
        execution = horizon_views["execution"]
        tactical_plan = _plan_by_type(trade_plans, f"TACTICAL_{tactical.direction}")
        execution_plan = _plan_by_type(trade_plans, "EXECUTION_TRIGGER")

        headline = (
            f"{_state_label(state)}: "
            f"1M/1w {_direction_action(strategic.direction)}，"
            f"1d/4h {_direction_action(tactical.direction)}，"
            f"执行层{_direction_action(execution.direction)}。"
        )

        layers = [
            {
                "key": "strategic",
                "label": "战略层",
                "timeframes": strategic.source_timeframes or ["1M", "1w"],
                "direction": strategic.direction,
                "direction_label": _cn_direction(strategic.direction),
                "basis": f"1M/1w 综合分数 {_fmt_score(strategic)}；{_clean_evidence(strategic.evidence, fallback='缺少高周期证据明细，暂以综合分数和结构状态为准。')}",
                "required_signal": "只定义长期边界和仓位上限，不直接触发短线入场。",
            },
            {
                "key": "tactical",
                "label": "战术层",
                "timeframes": tactical.source_timeframes or ["1d", "4h"],
                "direction": tactical.direction,
                "direction_label": _cn_direction(tactical.direction),
                "basis": f"1d/4h 综合分数 {_fmt_score(tactical)}；{_clean_evidence(tactical.evidence, fallback='缺少日线/4H 结构证据明细，不能把战术方向升级为强执行。')}",
                "required_signal": tactical_plan.entry_logic if tactical_plan else "等待 4H 收盘确认战术结构延续。",
            },
            {
                "key": "execution",
                "label": "执行层",
                "timeframes": execution.source_timeframes or ["4h", "1h", "15m"],
                "direction": execution.direction,
                "direction_label": _cn_direction(execution.direction),
                "basis": f"4H/1H/15M 综合分数 {_fmt_score(execution)}；{_clean_evidence(execution.evidence, fallback='缺少 1H/15M 触发证据，当前只能等待确认。')}",
                "required_signal": self._execution_required_signal(execution, execution_plan),
            },
        ]

        watchlist = self._watchlist(tactical, execution, tactical_plan, execution_plan, risk_alerts)
        action = self._action(state, tactical, execution, watchlist)
        return {
            "headline": headline,
            "layers": layers,
            "watchlist": watchlist,
            "action": action,
            "summary": "",
            "market_operation": str(market_operation.get("summary") or ""),
            "trade_plan": tactical_plan.entry_logic if tactical_plan else "",
            "risk": self._risk_summary(risk_alerts),
        }

    @staticmethod
    def _execution_required_signal(execution: HorizonView, execution_plan: TradePlan | None) -> str:
        if execution.direction == "WAIT_SHORT_TRIGGER":
            return "等待 1H 反抽失败或跌破确认，15M 只用于回抽不过和追空过滤。"
        if execution.direction == "WAIT_LONG_TRIGGER":
            return "等待 1H 突破回踩确认或支撑反转，15M 只用于入场质量过滤。"
        if execution_plan and execution_plan.entry_logic:
            return execution_plan.entry_logic
        return "缺少 1H/15M 方向触发，等待 4H 或 1H 收盘重新确认。"

    @staticmethod
    def _watchlist(
        tactical: HorizonView,
        execution: HorizonView,
        tactical_plan: TradePlan | None,
        execution_plan: TradePlan | None,
        risk_alerts: Sequence[RiskAlert],
    ) -> list[dict[str, str]]:
        side = "空头" if tactical.direction == "SHORT" else "多头" if tactical.direction == "LONG" else "方向"
        items = [
            {
                "timeframe": "4H",
                "indicator": "收盘结构",
                "condition": tactical_plan.invalidation if tactical_plan else f"确认 {side} 结构是否延续。",
            },
            {
                "timeframe": "1H",
                "indicator": "触发信号",
                "condition": "反抽失败 / 跌破确认" if execution.direction == "WAIT_SHORT_TRIGGER" else "突破回踩 / 支撑反转" if execution.direction == "WAIT_LONG_TRIGGER" else "等待方向触发。",
            },
            {
                "timeframe": "15M",
                "indicator": "执行过滤",
                "condition": "确认回抽不过、追价质量和触发位收回风险。",
            },
        ]
        if execution_plan and execution_plan.invalidation:
            items.append({
                "timeframe": "1H/15M",
                "indicator": "执行失效",
                "condition": execution_plan.invalidation,
            })
        for risk in risk_alerts:
            if risk.severity in {"blocker", "warning"}:
                items.append({
                    "timeframe": "/".join(risk.affected_horizons) or "全局",
                    "indicator": risk.label,
                    "condition": risk.action,
                })
                break
        return items[:5]

    @staticmethod
    def _action(state: Mapping[str, object], tactical: HorizonView, execution: HorizonView, watchlist: Sequence[Mapping[str, str]]) -> str:
        permission = str(state.get("permission") or "")
        if permission == "no_trade":
            return "当前权限为不交易，先处理风险门禁和数据缺口。"
        if tactical.direction == "SHORT":
            return "短中期优先执行空头计划，但必须等待 1H/15M 触发确认。"
        if tactical.direction == "LONG":
            return "短中期优先执行多头计划，但必须等待 1H/15M 触发确认。"
        first = watchlist[0]["condition"] if watchlist else "等待 4H/1H 结构重新定价。"
        return f"当前以观察为主，下一步检查：{first}"

    @staticmethod
    def _risk_summary(risk_alerts: Sequence[RiskAlert]) -> str:
        if not risk_alerts:
            return "未触发硬风险门禁。"
        return "；".join(f"{risk.label}: {risk.action}" for risk in risk_alerts[:3])
