from __future__ import annotations

from typing import Any

from app.services.strategy_signal.risk_reward import (
    clamp,
    number,
    risk_reward_label,
    round2,
)
from app.services.strategy_signal.scoring_engine import DirectionScores
from app.services.strategy_signal.setup_lifecycle import (
    evaluate_lower_tf_trigger,
    evaluate_strong_trend_follow,
    normalize_plan_levels,
)

STATE_LABELS = {
    "NO_EDGE": "多空不明",
    "OBSERVE": "观察等待",
    "CONFLICTED_NO_TRADE": "多空冲突，暂不交易",
    "LONG_BIAS": "偏多观察",
    "SHORT_BIAS": "偏空观察",
    "SETUP_DETECTED": "策略结构已形成",
    "WAIT_LONG_CONFIRMATION": "等待多头确认",
    "WAIT_SHORT_CONFIRMATION": "等待空头确认",
    "WAIT_LOWER_TF_CONFIRMATION": "等待次级周期确认",
    "WAIT_PULLBACK_CONFIRMATION": "等待反抽/回踩确认",
    "LONG_TRIGGERED": "多头策略已触发",
    "SHORT_TRIGGERED": "空头策略已触发",
    "TREND_FOLLOW_TRIGGERED": "强趋势追随已触发",
    "BREAKDOWN_TRIGGERED": "破位跟随已触发",
    "BREAKOUT_TRIGGERED": "突破跟随已触发",
    "MOVE_MISSED": "原计划入场已错过",
    "WAIT_RETEST_AFTER_MISSED_MOVE": "错过后等待反抽/回踩",
    "TP1_HIT": "第一目标已触发",
    "TP2_HIT": "第二目标已触发",
    "STOP_HIT": "止损/失效已触发",
    "SETUP_EXPIRED": "策略计划已过期",
    "SETUP_INVALIDATED": "策略结构已失效",
    "INVALID_PLAN_LEVELS": "策略价位无效",
    "EVENT_WAIT": "事件窗口等待",
    "RISK_OFF": "风险关闭",
}

BIAS_LABELS = {
    "long": "偏多",
    "short": "偏空",
    "neutral": "中性",
    "conflicted": "冲突",
    "risk_off": "风险关闭",
}

PERMISSION_LABELS = {
    "allow": "允许执行",
    "conditional": "条件允许",
    "observe_only": "仅观察",
    "blocked": "禁止交易",
}

STRATEGY_TYPE_LABELS = {
    "trend_pullback_long": "趋势回踩做多",
    "breakout_long": "突破做多",
    "trend_retest_short": "趋势反抽做空",
    "breakdown_short": "跌破做空",
    "neutral_observe": "多空不明",
}


def _confirmation_gates(trigger_ready: bool, rr: float, min_rr: float, side_score: float, trigger_score: float) -> list[str]:
    gates = []
    if not trigger_ready:
        gates.append("入场触发尚未完成")
    if rr < min_rr:
        gates.append(f"风险收益比低于阈值 (当前 {rr:.1f} < 要求 {min_rr:.1f})")
    if side_score < trigger_score:
        gates.append(f"方向评分未达触发要求 (当前 {side_score:.2f} < 要求 {trigger_score:.2f})")
    if not gates:
        gates.append("执行条件尚不满足，等待价格确认")
    return gates


def _next_trigger_text(side: str, snapshot: dict[str, Any]) -> str:
    price = number(snapshot.get("current_price"))
    key_level = snapshot.get(f"{side}_entry") or snapshot.get("key_support" if side == "long" else "key_resistance")
    if key_level and price:
        key_fmt = f"{float(key_level):,.0f}"
        if side == "long":
            return f"4h/1h 收盘站稳 {key_fmt} 上方并给出次级别多头确认，才开放多头执行权限。"
        else:
            return f"4h/1h 收盘跌破 {key_fmt} 下方并给出次级别空头确认，才开放空头执行权限。"
    if side == "long":
        return "4h/1h 收盘给出次级别多头确认后开放执行权限。"
    return "4h/1h 收盘给出次级别空头确认后开放执行权限。"


class StrategyGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.thresholds = config["thresholds"]
        self.state_permissions = config.get("state_permissions", {})

    def build_decision(self, snapshot: dict[str, Any], scores: DirectionScores) -> dict[str, Any]:
        state_context = self._state(snapshot, scores)
        state = state_context["state"]
        bias = state_context["bias"]
        reasons = state_context["reasons"]
        lower_tf = state_context.get("lower_tf_confirmation", {})
        trend_follow = state_context.get("strong_trend_follow", {})
        entry_mode = state_context.get("entry_mode")

        long_plan = self._plan("long", snapshot, scores.long_score, state)
        short_plan = self._plan("short", snapshot, scores.short_score, state)
        primary = long_plan if bias == "long" else short_plan if bias == "short" else self._empty_plan("neutral")
        alternative = short_plan if bias == "long" else long_plan if bias == "short" else self._empty_plan("neutral")

        if bias in {"long", "short"} and not primary.get("is_valid", True):
            state = "INVALID_PLAN_LEVELS"
            reasons = [primary.get("invalid_reason") or "策略价位顺序不满足方向约束。"]
            entry_mode = "no_trade"

        permission = self._permission(state)
        trigger_diagnostics = [
            *(lower_tf.get("diagnostics") or []),
            *(trend_follow.get("diagnostics") or []),
            *self._gate_diagnostics(snapshot, scores, bias),
        ]

        return {
            "strategy_state": state,
            "strategy_state_label": STATE_LABELS.get(state, state),
            "strategy_bias": bias,
            "strategy_bias_label": BIAS_LABELS.get(bias, bias),
            "strategy_permission": permission,
            "strategy_permission_label": PERMISSION_LABELS.get(permission, permission),
            "long_score": round2(scores.long_score),
            "short_score": round2(scores.short_score),
            "neutral_score": round2(scores.neutral_score),
            "dominant_direction": bias,
            "direction_confidence": round2(scores.confidence),
            "confidence_score": round2(scores.confidence),
            "data_quality_score": round2(scores.data_quality_score),
            "conflict_score": round2(scores.conflict_score),
            "execution_score": round2(snapshot.get("execution_quality", 0)),
            "risk_score": round2(snapshot.get("late_entry_risk_score", 0)),
            "pattern_type": primary.get("pattern_type"),
            "pattern_label": primary.get("pattern_label"),
            "primary_strategy": primary,
            "alternative_strategy": alternative,
            "backup_strategy": alternative,
            "long_plan": long_plan,
            "short_plan": short_plan,
            "risk_reward": {
                "long": {"value": round(scores.rr_long, 2) if scores.rr_long is not None else None, "label": risk_reward_label(scores.rr_long)},
                "short": {"value": round(scores.rr_short, 2) if scores.rr_short is not None else None, "label": risk_reward_label(scores.rr_short)},
            },
            "entry_checklist": self._entry_checklist(snapshot, state, bias, scores),
            "gates": self._gates(snapshot, scores),
            "trigger_diagnostics": trigger_diagnostics,
            "lower_tf_confirmation": lower_tf,
            "strong_trend_follow": trend_follow,
            "entry_mode": entry_mode or primary.get("entry_mode") or "no_trade",
            "setup_lifecycle": {},
            "active_setup": None,
            "missed_move": {},
            "no_trade_reasons": reasons,
            "conflict_reasons": self._conflict_reasons(snapshot, scores),
            "evidence_matrix": self._evidence_matrix(snapshot, scores),
            "review_tags": self._review_tags(state, bias, primary),
            "explain": self._explain(snapshot, state, bias, scores, reasons),
            "components": self._components(snapshot, scores),
        }

    def _state(self, snapshot: dict[str, Any], scores: DirectionScores) -> dict[str, Any]:
        th = self.thresholds
        hard_reasons = self._hard_gate_reasons(snapshot)
        if hard_reasons:
            return {"state": "RISK_OFF", "bias": "risk_off", "reasons": hard_reasons, "entry_mode": "no_trade"}
        if clamp(snapshot.get("event_risk_score", 0)) >= th["event_wait"]:
            return {"state": "EVENT_WAIT", "bias": "neutral", "reasons": ["重大事件窗口临近，等待落地后重新评估。"], "entry_mode": "no_trade"}
        if scores.data_quality_score < th["data_quality_min_decision"]:
            return {"state": "NO_EDGE", "bias": "neutral", "reasons": ["当前数据质量低于最低决策要求，暂不生成交易策略。"], "entry_mode": "no_trade"}
        if scores.long_score < th["no_edge_score"] and scores.short_score < th["no_edge_score"]:
            return {"state": "NO_EDGE", "bias": "neutral", "reasons": ["多空双方都没有形成可交易信号。"], "entry_mode": "no_trade"}
        if (
            scores.long_score >= th["conflict_both_high"]
            and scores.short_score >= th["conflict_both_high"]
            and abs(scores.long_score - scores.short_score) < th["conflict_gap"]
        ):
            return {"state": "CONFLICTED_NO_TRADE", "bias": "conflicted", "reasons": ["多空证据同时较强，方向冲突未解除。"], "entry_mode": "no_trade"}

        side = None
        if scores.long_score - scores.short_score >= th["dominant_gap"]:
            side = "long"
        elif scores.short_score - scores.long_score >= th["dominant_gap"]:
            side = "short"
        if side is None:
            return {"state": "OBSERVE", "bias": "neutral", "reasons": ["多空分差不足，等待更清晰的结构或触发信号。"], "entry_mode": "no_trade"}

        side_score = scores.long_score if side == "long" else scores.short_score
        setup_ready = bool(snapshot.get(f"{side}_setup_ready"))
        trigger_ready = bool(snapshot.get(f"{side}_trigger_ready"))
        rr = scores.rr_long if side == "long" else scores.rr_short

        trend_follow = evaluate_strong_trend_follow(side, snapshot, self.config)
        if trend_follow.get("state") == "WAIT_RETEST_AFTER_MISSED_MOVE":
            return {
                "state": "WAIT_RETEST_AFTER_MISSED_MOVE",
                "bias": side,
                "reasons": [trend_follow.get("reason") or "强趋势已走出，但追单距离偏远。"],
                "strong_trend_follow": trend_follow,
                "entry_mode": trend_follow.get("entry_mode"),
            }
        if trend_follow.get("ready"):
            return {"state": trend_follow["state"], "bias": side, "reasons": [], "strong_trend_follow": trend_follow, "entry_mode": trend_follow.get("entry_mode")}

        if side_score >= th["trigger_score"] and setup_ready and trigger_ready and (rr or 0) >= th["min_rr_trade"]:
            return {"state": f"{side.upper()}_TRIGGERED", "bias": side, "reasons": [], "entry_mode": "pullback_confirm"}
        if side_score >= th["setup_score"] and setup_ready:
            lower_tf = evaluate_lower_tf_trigger(side, snapshot, None, self.config)
            if lower_tf.get("missing"):
                return {
                    "state": "WAIT_LOWER_TF_CONFIRMATION",
                    "bias": side,
                    "reasons": ["方向优势存在，但缺少次级周期触发确认。"],
                    "lower_tf_confirmation": lower_tf,
                    "entry_mode": "pullback_confirm",
                    "blocking_gates": ["缺少次级别周期信号"],
                    "next_trigger": "等待 4h 或 1h 周期出现明确触发信号后重新评估入场。",
                }
            gates = _confirmation_gates(trigger_ready, rr or 0, th["min_rr_trade"], side_score, th["trigger_score"])
            return {
                "state": "WAIT_LONG_CONFIRMATION" if side == "long" else "WAIT_SHORT_CONFIRMATION",
                "bias": side,
                "reasons": [f"{BIAS_LABELS[side]}方向评分占优，但执行触发未完成。"],
                "entry_mode": "pullback_confirm",
                "blocking_gates": gates,
                "next_trigger": _next_trigger_text(side, snapshot),
            }
        if side_score >= th["bias_score"]:
            return {
                "state": "LONG_BIAS" if side == "long" else "SHORT_BIAS",
                "bias": side,
                "reasons": [f"市场{BIAS_LABELS[side]}，但策略结构还不完整。"],
                "entry_mode": "no_trade",
                "blocking_gates": ["setup 结构尚未形成", "入场触发条件未满足"],
                "next_trigger": f"等待{BIAS_LABELS[side]}方向 setup 结构完整形成后进入 WAIT_CONFIRMATION 阶段。",
            }
        return {"state": "OBSERVE", "bias": "neutral", "reasons": ["方向优势不足，继续观察。"], "entry_mode": "no_trade"}

    def _permission(self, state: str) -> str:
        if state in self.state_permissions:
            return self.state_permissions[state]
        if state.endswith("TRIGGERED"):
            return "allow"
        if state.startswith("WAIT") or state == "SETUP_DETECTED":
            return "conditional"
        if state in {"RISK_OFF", "INVALID_PLAN_LEVELS"}:
            return "blocked"
        return "observe_only"

    def _plan(self, side: str, snapshot: dict[str, Any], side_score: float, state: str) -> dict[str, Any]:
        price = number(snapshot.get("current_price"))
        atr = max(number(snapshot.get("atr_14"), price * 0.025), price * 0.006) if price else 0.0
        if not price:
            return self._empty_plan(side)
        if side == "long":
            entry = number(snapshot.get("long_entry"), price * 0.995)
            stop = number(snapshot.get("long_stop"), entry - atr * 1.6)
            tp1 = number(snapshot.get("long_tp1"), entry + atr * 2.2)
            tp2 = number(snapshot.get("long_tp2"), entry + atr * 3.6)
            pattern = "breakout_long" if snapshot.get("breakout_up") else "trend_pullback_long"
            conditions = ["高周期方向不冲突", "价格回踩后重新站稳关键位", "成交量或资金流至少一项同步改善"]
            invalidation = ["收盘跌回关键支撑下方", "跌破最近结构低点", "主动买入无法延续且价格失守入场区"]
            active = state in {"LONG_TRIGGERED", "BREAKOUT_TRIGGERED", "TREND_FOLLOW_TRIGGERED"}
        else:
            entry = number(snapshot.get("short_entry"), price * 1.005)
            stop = number(snapshot.get("short_stop"), entry + atr * 1.6)
            tp1 = number(snapshot.get("short_tp1"), entry - atr * 2.2)
            tp2 = number(snapshot.get("short_tp2"), entry - atr * 3.6)
            pattern = "breakdown_short" if snapshot.get("breakout_down") else "trend_retest_short"
            conditions = ["高周期方向不冲突", "反抽关键位失败或跌破支撑", "主动卖出或空头动量继续增强"]
            invalidation = ["收盘重新站上关键阻力", "突破最近结构高点", "主动卖出衰竭且价格收回入场区"]
            active = state in {"SHORT_TRIGGERED", "BREAKDOWN_TRIGGERED", "TREND_FOLLOW_TRIGGERED"}
        levels = normalize_plan_levels(side, entry, stop, tp1, tp2, price, atr, min_rr=self.thresholds.get("min_rr_trade", 1.5))
        rr = levels["rr1"] if levels["is_valid"] else None
        return {
            "pattern_type": pattern,
            "pattern_label": STRATEGY_TYPE_LABELS[pattern],
            "direction": side,
            "entry_mode": "breakout_follow" if pattern == "breakout_long" else "breakdown_follow" if pattern == "breakdown_short" else "pullback_confirm",
            "entry_condition": "触发条件已接近满足" if active else "等待入场确认",
            "entry_zone": [round(levels["entry"] * 0.998, 2), round(levels["entry"] * 1.002, 2)] if levels["entry"] else None,
            "entry_price_range": [round(levels["entry"] * 0.998, 2), round(levels["entry"] * 1.002, 2)] if levels["entry"] else None,
            "entry_price": round(levels["entry"], 2) if levels["entry"] else None,
            "stop_loss_rule": f"结构失效或价格触发 {round(levels['stop'], 2)} 附近" if levels["stop"] else "暂无止损位",
            "take_profit_rule": f"第一目标 {round(levels['tp1'], 2)}，第二目标 {round(levels['tp2'], 2)}" if levels["tp1"] else "暂无止盈位",
            "stop_price": round(levels["stop"], 2) if levels["stop"] else None,
            "take_profit_1": round(levels["tp1"], 2) if levels["tp1"] else None,
            "take_profit_2": round(levels["tp2"], 2) if levels["tp2"] else None,
            "risk_reward_ratio": round(rr, 2) if rr is not None else None,
            "risk_reward_1": round(rr, 2) if rr is not None else None,
            "risk_reward_label": risk_reward_label(rr),
            "capital_pct": round(0 if not active else min(12, max(3, side_score / 10)), 2),
            "max_leverage": 3 if active else 0,
            "strategy_logic": "综合趋势结构、动量、资金流、衍生品确认与执行质量生成的市场策略信号。",
            "entry_conditions": conditions,
            "confirmation_criteria": conditions,
            "invalidation_rules": invalidation,
            "invalidation_criteria": invalidation,
            "levels": levels,
            "is_valid": bool(levels["is_valid"]),
            "invalid_reason": levels.get("invalid_reason"),
        }

    @staticmethod
    def _empty_plan(side: str) -> dict[str, Any]:
        return {
            "pattern_type": None,
            "pattern_label": "暂无策略",
            "direction": side,
            "entry_condition": "暂无有效入场条件",
            "entry_zone": None,
            "entry_price_range": None,
            "entry_price": None,
            "stop_loss_rule": "暂无止损位",
            "take_profit_rule": "暂无止盈位",
            "stop_price": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "risk_reward_ratio": None,
            "risk_reward_label": "暂无盈亏比",
            "capital_pct": 0,
            "max_leverage": 0,
            "strategy_logic": "当前多空不明，等待更清晰的结构或触发信号。",
            "entry_conditions": [],
            "confirmation_criteria": [],
            "invalidation_rules": [],
            "invalidation_criteria": [],
            "is_valid": True,
        }

    def _entry_checklist(self, snapshot: dict[str, Any], state: str, bias: str, scores: DirectionScores) -> list[dict[str, Any]]:
        if bias not in {"long", "short"}:
            return [
                {"condition": "方向优势", "current_value": "多空分差不足", "status": "未满足"},
                {"condition": "数据质量", "current_value": round2(scores.data_quality_score), "status": "部分满足"},
            ]
        gap = abs(scores.long_score - scores.short_score)
        return [
            {"condition": "方向分差", "current_value": round2(gap), "status": "满足" if gap >= self.thresholds["dominant_gap"] else "部分满足"},
            {"condition": "入场触发", "current_value": STATE_LABELS.get(state, state), "status": "满足" if "TRIGGERED" in state else "部分满足"},
            {"condition": "盘口执行", "current_value": round2(snapshot.get("execution_quality")), "status": "满足" if number(snapshot.get("execution_quality")) >= 60 else "未满足"},
            {"condition": "事件风险", "current_value": snapshot.get("event_window_status", "normal"), "status": "满足" if snapshot.get("event_risk_score", 0) < self.thresholds["event_wait"] else "未满足"},
        ]

    def _gates(self, snapshot: dict[str, Any], scores: DirectionScores) -> list[dict[str, Any]]:
        gates = [{"code": "HARD_GATE", "severity": "block", "message": reason} for reason in self._hard_gate_reasons(snapshot)]
        if scores.data_quality_score < 60:
            gates.append({"code": "DATA_QUALITY_LOW", "severity": "warn", "message": "数据质量偏低，建议只观察或等待缓存补齐。"})
        if number(snapshot.get("funding_crowding_score")) > 75:
            gates.append({"code": "FUNDING_CROWDING", "severity": "warn", "message": "资金费率拥挤，追单回撤风险上升。"})
        return gates

    def _gate_diagnostics(self, snapshot: dict[str, Any], scores: DirectionScores, bias: str) -> list[dict[str, Any]]:
        if bias not in {"long", "short"}:
            return []
        score = scores.long_score if bias == "long" else scores.short_score
        rr = scores.rr_long if bias == "long" else scores.rr_short
        return [
            {"code": f"{bias}_setup_score", "status": "pass" if score >= self.thresholds["setup_score"] else "fail", "message": "方向分达到 setup 阈值" if score >= self.thresholds["setup_score"] else "方向分未达到 setup 阈值", "current": round2(score), "required": self.thresholds["setup_score"], "severity": "info"},
            {"code": f"{bias}_trigger_score", "status": "pass" if score >= self.thresholds["trigger_score"] else "fail", "message": "方向分达到触发阈值" if score >= self.thresholds["trigger_score"] else "方向分未达到触发阈值", "current": round2(score), "required": self.thresholds["trigger_score"], "severity": "info"},
            {"code": f"{bias}_rr", "status": "pass" if (rr or 0) >= self.thresholds["min_rr_trade"] else "fail", "message": "盈亏比达到交易阈值" if (rr or 0) >= self.thresholds["min_rr_trade"] else "盈亏比不足或缺失", "current": round(rr or 0, 2), "required": self.thresholds["min_rr_trade"], "severity": "warning"},
        ]

    def _hard_gate_reasons(self, snapshot: dict[str, Any]) -> list[str]:
        th = self.thresholds
        reasons = []
        if clamp(snapshot.get("spread_bps", 0), 0, 10000) > th["spread_hard_limit_bps"]:
            reasons.append("当前买卖价差过宽，执行风险过高。")
        if clamp(snapshot.get("slippage_bps", 0), 0, 10000) > th["slippage_hard_limit_bps"]:
            reasons.append("当前预计滑点过高，入场价格不可控。")
        if clamp(snapshot.get("depth_score", 100)) < th["min_depth_score"]:
            reasons.append("当前盘口深度偏薄，冲击成本可能侵蚀收益。")
        return reasons

    @staticmethod
    def _conflict_reasons(snapshot: dict[str, Any], scores: DirectionScores) -> list[str]:
        reasons = []
        if scores.conflict_score >= 70:
            reasons.append("多空证据差距偏小，当前方向冲突较高。")
        if number(snapshot.get("event_risk_score")) >= 75:
            reasons.append("重大事件窗口提高了策略不确定性。")
        return reasons

    @staticmethod
    def _evidence_matrix(snapshot: dict[str, Any], scores: DirectionScores) -> list[dict[str, Any]]:
        return [
            {"name": "多周期方向", "long_score": round2(snapshot.get("mtf_trend_bullish")), "short_score": round2(snapshot.get("mtf_trend_bearish")), "detail": "来自当前与相邻周期的方向一致性。"},
            {"name": "结构与关键位", "long_score": round2(snapshot.get("bullish_structure")), "short_score": round2(snapshot.get("bearish_structure")), "detail": "参考 BOS、区间位置、支撑阻力和价值区。"},
            {"name": "动量与成交", "long_score": round2(snapshot.get("bullish_momentum")), "short_score": round2(snapshot.get("bearish_momentum")), "detail": "参考 RSI、MACD、ADX、OBV 与成交量确认。"},
            {"name": "资金流与衍生品", "long_score": round2(snapshot.get("bullish_flow")), "short_score": round2(snapshot.get("bearish_flow")), "detail": "参考 CVD、OI、Funding、Basis 与盘口深度。"},
            {"name": "综合结果", "long_score": round2(scores.long_score), "short_score": round2(scores.short_score), "detail": "应用惩罚项和风险收益比后的最终多空评分。"},
        ]

    @staticmethod
    def _review_tags(state: str, bias: str, primary: dict[str, Any]) -> list[str]:
        tags = [f"state:{state}", f"bias:{bias}"]
        if primary.get("pattern_type"):
            tags.append(f"pattern:{primary['pattern_type']}")
        return tags

    @staticmethod
    def _components(snapshot: dict[str, Any], scores: DirectionScores) -> dict[str, float]:
        keys = [
            "mtf_trend_bullish",
            "bullish_structure",
            "bullish_momentum",
            "bullish_flow",
            "derivatives_long_confirmation",
            "execution_quality",
            "mtf_trend_bearish",
            "bearish_structure",
            "bearish_momentum",
            "bearish_flow",
            "derivatives_short_confirmation",
            "range_structure",
            "low_adx",
        ]
        components = {key: round2(snapshot.get(key)) for key in keys}
        components["long_penalty"] = round2(scores.long_penalty)
        components["short_penalty"] = round2(scores.short_penalty)
        return components

    @staticmethod
    def _explain(snapshot: dict[str, Any], state: str, bias: str, scores: DirectionScores, reasons: list[str]) -> list[str]:
        output = [
            f"当前策略状态为“{STATE_LABELS.get(state, state)}”，策略倾向为“{BIAS_LABELS.get(bias, bias)}”。",
            f"多头分 {scores.long_score:.2f}，空头分 {scores.short_score:.2f}，中性分 {scores.neutral_score:.2f}。",
            f"数据质量 {scores.data_quality_score:.2f}，冲突分 {scores.conflict_score:.2f}，方向置信 {scores.confidence:.2f}。",
        ]
        if snapshot.get("lower_tf_missing"):
            output.append("当前缺少次级周期触发数据，不能把方向优势直接升级为入场触发。")
        output.extend(reasons)
        return output
