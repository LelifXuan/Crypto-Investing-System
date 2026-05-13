from __future__ import annotations

from typing import Any

from app.services.strategy_signal.risk_reward import (
    clamp,
    number,
    risk_reward_label,
    round2,
)
from app.services.strategy_signal.scoring_engine import DirectionScores

STATE_LABELS = {
    "NO_EDGE": "多空不明，暂无交易信号",
    "OBSERVE": "观察等待",
    "CONFLICTED_NO_TRADE": "多空冲突，不交易",
    "LONG_BIAS": "偏多观察",
    "SHORT_BIAS": "偏空观察",
    "WAIT_LONG_CONFIRMATION": "等待做多确认",
    "WAIT_SHORT_CONFIRMATION": "等待做空确认",
    "LONG_TRIGGERED": "做多策略已触发",
    "SHORT_TRIGGERED": "做空策略已触发",
    "EVENT_WAIT": "事件窗口等待",
    "RISK_OFF": "风险关闭",
}

RISK_OFF_SUBTYPE_LABELS = {
    "LIQUIDITY": "流动性风险",
    "DATA_QUALITY": "数据质量不足",
    "EVENT": "极端事件风险",
    "LIQUIDITY_DATA": "流动性与数据质量",
    "MULTIPLE": "多重风险",
}

RISK_OFF_REASON_CONFIG = {
    "LIQUIDITY": {"keywords": ["价差", "滑点", "深度", "盘口"], "action": "等待市场流动性改善后再评估。"},
    "DATA_QUALITY": {"keywords": ["数据质量"], "action": "等待数据源更新完整后再生成策略。"},
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
    "false_breakdown_reclaim_long": "假跌破收回做多",
    "range_low_long": "区间下沿做多",
    "squeeze_breakout_long": "波动压缩向上突破",
    "liquidity_sweep_reversal_long": "扫下方流动性后反转做多",
    "trend_retest_short": "趋势反抽做空",
    "breakdown_short": "跌破做空",
    "false_breakout_reversal_short": "假突破回落做空",
    "range_high_short": "区间上沿做空",
    "squeeze_breakdown_short": "波动压缩向下跌破",
    "liquidity_sweep_reversal_short": "扫上方流动性后反转做空",
}


class StrategyGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.thresholds = config["thresholds"]

    def build_decision(self, snapshot: dict[str, Any], scores: DirectionScores) -> dict[str, Any]:
        state, bias, permission, reasons = self._state(snapshot, scores)
        long_plan = self._plan("long", snapshot, scores.long_score, state)
        short_plan = self._plan("short", snapshot, scores.short_score, state)
        primary = long_plan if bias == "long" else short_plan if bias == "short" else self._empty_plan("neutral")
        alternative = short_plan if bias == "long" else long_plan if bias == "short" else self._empty_plan("neutral")
        risk_subtype = self._classify_risk_subtype(reasons) if state == "RISK_OFF" and reasons else None

        return {
            "strategy_state": state,
            "strategy_state_label": STATE_LABELS[state],
            "strategy_bias": bias,
            "strategy_bias_label": BIAS_LABELS[bias],
            "strategy_permission": permission,
            "strategy_permission_label": PERMISSION_LABELS[permission],
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
                "long": {
                    "value": round(scores.rr_long, 2) if scores.rr_long is not None else None,
                    "label": risk_reward_label(scores.rr_long),
                },
                "short": {
                    "value": round(scores.rr_short, 2) if scores.rr_short is not None else None,
                    "label": risk_reward_label(scores.rr_short),
                },
            },
            "entry_checklist": self._entry_checklist(snapshot, state, bias, scores),
            "gates": self._gates(snapshot, scores),
            "no_trade_reasons": reasons,
            "conflict_reasons": self._conflict_reasons(snapshot, scores),
            "evidence_matrix": self._evidence_matrix(snapshot, scores),
            "review_tags": self._review_tags(state, bias, primary),
            "explain": self._explain(snapshot, state, bias, scores, reasons),
            "components": self._components(snapshot, scores),
            "risk_subtype": risk_subtype,
            "risk_subtype_label": RISK_OFF_SUBTYPE_LABELS.get(risk_subtype, "") if risk_subtype else None,
            "risk_reasons_detail": self._enrich_risk_reasons(reasons) if state == "RISK_OFF" else [],
        }

    def _state(self, snapshot: dict[str, Any], scores: DirectionScores) -> tuple[str, str, str, list[str]]:
        th = self.thresholds
        hard_reasons = self._hard_gate_reasons(snapshot, scores)
        if hard_reasons:
            return "RISK_OFF", "risk_off", "blocked", hard_reasons
        if clamp(snapshot.get("event_risk_score", 0)) >= th["event_wait"]:
            return "EVENT_WAIT", "neutral", "observe_only", ["事件窗口临近，等待落地后重新评估。"]
        if scores.data_quality_score < th["data_quality_min_decision"]:
            return "NO_EDGE", "neutral", "observe_only", ["当前数据质量低于最低决策要求，暂不生成交易策略。"]
        if scores.long_score < th["no_edge_score"] and scores.short_score < th["no_edge_score"]:
            return "NO_EDGE", "neutral", "observe_only", ["多空双方都没有形成可交易信号，不生成策略。"]
        if (
            scores.long_score >= th["conflict_both_high"]
            and scores.short_score >= th["conflict_both_high"]
            and abs(scores.long_score - scores.short_score) < th["conflict_gap"]
        ):
            return "CONFLICTED_NO_TRADE", "conflicted", "observe_only", ["多空证据同时较强，方向冲突未解除。"]

        if scores.long_score - scores.short_score >= th["dominant_gap"]:
            if (
                scores.long_score >= th["trigger_score"]
                and snapshot.get("long_setup_ready")
                and snapshot.get("long_trigger_ready")
                and (scores.rr_long or 0) >= th["min_rr_trade"]
            ):
                return "LONG_TRIGGERED", "long", "allow", []
            if scores.long_score >= th["setup_score"] and snapshot.get("long_setup_ready"):
                return "WAIT_LONG_CONFIRMATION", "long", "conditional", ["做多方向具备优势，但入场触发尚未完全确认。"]
            if scores.long_score >= th["bias_score"]:
                return "LONG_BIAS", "long", "observe_only", ["市场偏多，但策略结构还不完整。"]

        if scores.short_score - scores.long_score >= th["dominant_gap"]:
            if (
                scores.short_score >= th["trigger_score"]
                and snapshot.get("short_setup_ready")
                and snapshot.get("short_trigger_ready")
                and (scores.rr_short or 0) >= th["min_rr_trade"]
            ):
                return "SHORT_TRIGGERED", "short", "allow", []
            if scores.short_score >= th["setup_score"] and snapshot.get("short_setup_ready"):
                return "WAIT_SHORT_CONFIRMATION", "short", "conditional", ["做空方向具备优势，但入场触发尚未完全确认。"]
            if scores.short_score >= th["bias_score"]:
                return "SHORT_BIAS", "short", "observe_only", ["市场偏空，但策略结构还不完整。"]

        return "OBSERVE", "neutral", "observe_only", ["多空分差不足，等待更清晰的结构或触发信号。"]

    def _classify_risk_subtype(self, reasons: list[str]) -> str:
        has_liquidity = any(
            kw in reason for reason in reasons
            for kw in ["价差", "滑点", "深度", "盘口"]
        )
        has_data = any("数据质量" in reason for reason in reasons)
        if has_liquidity and has_data:
            return "LIQUIDITY_DATA"
        if has_liquidity:
            return "LIQUIDITY"
        if has_data:
            return "DATA_QUALITY"
        return "MULTIPLE"

    def _enrich_risk_reasons(self, reasons: list[str]) -> list[dict[str, Any]]:
        enriched = []
        for reason in reasons:
            entry: dict[str, Any] = {"message": reason, "severity": "block", "type": "MULTIPLE"}
            if any(kw in reason for kw in ["价差", "滑点", "深度", "盘口"]):
                entry["type"] = "LIQUIDITY"
                entry["suggestion"] = "等待市场流动性改善后再评估。"
            elif "数据质量" in reason:
                entry["type"] = "DATA_QUALITY"
                entry["suggestion"] = "等待数据源更新完整后再生成策略。"
            elif "事件" in reason:
                entry["type"] = "EVENT"
                entry["suggestion"] = "等待事件落地、波动率回归正常后再评估。"
            enriched.append(entry)
        return enriched

    def _hard_gate_reasons(self, snapshot: dict[str, Any], scores: DirectionScores) -> list[str]:
        th = self.thresholds
        reasons = []
        if clamp(snapshot.get("spread_bps", 0), 0, 10000) > th["spread_hard_limit_bps"]:
            reasons.append("当前买卖价差过宽，执行风险过高。")
        if clamp(snapshot.get("slippage_bps", 0), 0, 10000) > th["slippage_hard_limit_bps"]:
            reasons.append("当前预估滑点过高，入场价格不可控。")
        if clamp(snapshot.get("depth_score", 100)) < th["min_depth_score"]:
            reasons.append("当前盘口深度偏薄，市价单冲击成本可能显著侵蚀利润。")
        if clamp(snapshot.get("event_risk_score", 0)) >= th.get("event_risk_hard_block", 95):
            reasons.append("事件风险极高，暂时锁定策略。")
        return reasons

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
            conditions = ["高周期方向不冲突", "价格回踩后重新站稳关键位", "CVD、OBV 或 OI 至少一项同步改善"]
            invalidation = ["收盘跌回关键支撑下方", "跌破最近结构低点", "主动买入无法延续且价格失守入场区"]
            active = state == "LONG_TRIGGERED"
        else:
            entry = number(snapshot.get("short_entry"), price * 1.005)
            stop = number(snapshot.get("short_stop"), entry + atr * 1.6)
            tp1 = number(snapshot.get("short_tp1"), entry - atr * 2.2)
            tp2 = number(snapshot.get("short_tp2"), entry - atr * 3.6)
            pattern = "breakdown_short" if snapshot.get("breakout_down") else "trend_retest_short"
            conditions = ["高周期方向不冲突", "反抽关键位失败或跌破支撑", "主动卖出或空头动量继续增强"]
            invalidation = ["收盘重新站上关键阻力", "突破最近结构高点", "主动卖出衰竭且价格收回入场区"]
            active = state == "SHORT_TRIGGERED"
        rr = abs(tp1 - entry) / max(abs(entry - stop), 1e-9)
        return {
            "pattern_type": pattern,
            "pattern_label": STRATEGY_TYPE_LABELS[pattern],
            "direction": side,
            "entry_condition": "触发条件已接近满足" if active else "等待入场确认",
            "entry_zone": [round(entry * 0.998, 2), round(entry * 1.002, 2)],
            "entry_price_range": [round(entry * 0.998, 2), round(entry * 1.002, 2)],
            "entry_price": round(entry, 2),
            "stop_loss_rule": f"结构失效或价格触及 {round(stop, 2)} 附近",
            "take_profit_rule": f"第一目标 {round(tp1, 2)}，第二目标 {round(tp2, 2)}",
            "stop_price": round(stop, 2),
            "take_profit_1": round(tp1, 2),
            "take_profit_2": round(tp2, 2),
            "risk_reward_ratio": round(rr, 2),
            "risk_reward_1": round(rr, 2),
            "risk_reward_label": risk_reward_label(rr),
            "capital_pct": round(0 if not active else min(12, max(3, side_score / 10)), 2),
            "max_leverage": 3 if active else 0,
            "strategy_logic": "综合趋势结构、动量、资金流、衍生品确认与执行质量生成的市场策略信号。",
            "entry_conditions": conditions,
            "confirmation_criteria": conditions,
            "invalidation_rules": invalidation,
            "invalidation_criteria": invalidation,
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
            "stop_loss_rule": "暂无",
            "take_profit_rule": "暂无",
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
        }

    def _entry_checklist(
        self, snapshot: dict[str, Any], state: str, bias: str, scores: DirectionScores
    ) -> list[dict[str, Any]]:
        if bias not in {"long", "short"}:
            return [
                {"condition": "方向优势", "current_value": "多空分差不足", "status": "未满足"},
                {"condition": "数据质量", "current_value": round2(scores.data_quality_score), "status": "部分满足"},
            ]
        gap = abs(scores.long_score - scores.short_score)
        return [
            {"condition": "方向分差", "current_value": round2(gap), "status": "满足" if gap >= self.thresholds["dominant_gap"] else "部分满足"},
            {"condition": "入场触发", "current_value": STATE_LABELS[state], "status": "满足" if "TRIGGERED" in state else "部分满足"},
            {"condition": "盘口执行", "current_value": round2(snapshot.get("execution_quality")), "status": "满足" if number(snapshot.get("execution_quality")) >= 60 else "未满足"},
            {"condition": "事件风险", "current_value": snapshot.get("event_window_status", "normal"), "status": "满足" if snapshot.get("event_risk_score", 0) < self.thresholds["event_wait"] else "未满足"},
        ]

    def _gates(self, snapshot: dict[str, Any], scores: DirectionScores) -> list[dict[str, Any]]:
        gates = []
        for reason in self._hard_gate_reasons(snapshot, scores):
            gates.append({"code": "HARD_GATE", "severity": "block", "message": reason})
        if scores.data_quality_score < 60:
            gates.append({"code": "DATA_QUALITY_LOW", "severity": "warn", "message": "数据质量偏低，已计入置信度扣分，建议仅观察。"})
        if number(snapshot.get("funding_crowding_score")) > 75:
            gates.append({"code": "FUNDING_CROWDING", "severity": "warn", "message": "资金费率拥挤，追单回撤风险上升。"})
        return gates

    @staticmethod
    def _conflict_reasons(snapshot: dict[str, Any], scores: DirectionScores) -> list[str]:
        reasons = []
        if scores.conflict_score >= 70:
            reasons.append("多空证据差距偏小，当前方向冲突较高。")
        if number(snapshot.get("event_risk_score")) >= 75:
            reasons.append("重大事件窗口提高了策略不确定性。")
        if number(snapshot.get("funding_crowding_score")) > 75:
            reasons.append("资金费率拥挤，可能导致追单回撤。")
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
    def _explain(
        snapshot: dict[str, Any],
        state: str,
        bias: str,
        scores: DirectionScores,
        reasons: list[str],
    ) -> list[str]:
        output = [
            f"当前策略状态为“{STATE_LABELS[state]}”，策略倾向为“{BIAS_LABELS[bias]}”。",
            f"多头分 {scores.long_score:.2f}，空头分 {scores.short_score:.2f}，中性分 {scores.neutral_score:.2f}。",
            f"数据质量 {scores.data_quality_score:.2f}，冲突分 {scores.conflict_score:.2f}，方向置信 {scores.confidence:.2f}。",
        ]
        if snapshot.get("event_risk_score", 0) >= 75:
            output.append("重大事件风险较高，策略需要等待事件落地。")
        output.extend(reasons)
        return output
