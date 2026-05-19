from __future__ import annotations

PERMISSION_LABELS = {
    "observe_only": "仅观察",
    "conditional_long": "条件多头",
    "conditional_short": "条件空头",
    "allow": "已触发",
    "blocked": "暂停执行",
}

TONE_CLASSES = {
    "warning": "warning",
    "caution": "caution",
    "neutral": "neutral",
    "positive": "positive",
    "negative": "negative",
}


def resolve_structure_text(
    *,
    local_state: str,
    local_label: str | None = None,
    latest_close: float | None = None,
    local_level: float | None = None,
    overall_bias: str | None = None,
    overall_score: float | None = None,
    overall_confidence: float | None = None,
    conflict_state: bool = False,
    conflict_type: str | None = None,
    contribution_breakdown: dict[str, float] | None = None,
    primary_drivers: list[str] | None = None,
    opposing_factors: list[str] | None = None,
) -> dict:
    if not overall_bias:
        overall_bias = "neutral"

    resolved = _build_decision(
        local_state=local_state,
        overall_bias=normalize_bias(overall_bias),
        contribution_breakdown=contribution_breakdown or {},
        primary_drivers=primary_drivers or [],
        opposing_factors=opposing_factors or [],
    )

    return {
        "local_state": local_state,
        "overall_bias": overall_bias,
        "resolved_state": resolved["resolved_state"],
        "headline": resolved["headline"],
        "message": resolved["message"],
        "permission": resolved["permission"],
        "permission_label": PERMISSION_LABELS.get(resolved["permission"], resolved["permission"]),
        "tone": resolved["tone"],
        "dominant_evidence": resolved.get("dominant_evidence", []),
        "opposing_evidence": resolved.get("opposing_evidence", []),
        "next_trigger": resolved["next_trigger"],
        "show_trade_action": resolved.get("show_trade_action", False),
    }


def normalize_bias(bias: str) -> str:
    bias = str(bias).lower().strip()
    if bias in {"bullish", "strong_bullish", "weak_bullish"}:
        return "bullish"
    if bias in {"bearish", "strong_bearish", "weak_bearish"}:
        return "bearish"
    return "neutral"


def _build_decision(
    local_state: str,
    overall_bias: str,
    contribution_breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    decisions = {
        "breakdown": _decide_breakdown,
        "breakout": _decide_breakout,
        "invalidated": _decide_invalidated,
        "inside": _decide_inside,
        "retest": _decide_retest,
    }
    handler = decisions.get(local_state, _decide_default)
    return handler(overall_bias, contribution_breakdown, primary_drivers, opposing_factors)


def _classify_contributions(breakdown: dict[str, float]) -> tuple[list[str], list[str]]:
    supporting = [k for k, v in breakdown.items() if v > 0.03]
    opposing = [k for k, v in breakdown.items() if v < -0.03]
    if not supporting:
        supporting = ["综合结构暂无明显偏向"]
    if not opposing:
        opposing = ["暂无明确对冲模块"]
    return supporting, opposing


def _support_oppose_labels(keys: list[str]) -> list[str]:
    name_map = {
        "swing": "摆动结构",
        "classic": "经典图形",
        "profile": "成交量轮廓",
    }
    return [name_map.get(k, k) for k in keys]


def _decide_breakdown(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)

    if overall_bias == "bullish":
        return {
            "resolved_state": "local_breakdown_overall_bullish_downgraded",
            "headline": "局部支撑破坏，综合多头降级为观望",
            "message": (
                "经典图形已跌破下沿，局部结构转弱。"
                "综合结构仍由其他模块支撑，但系统已将多头执行权限降级为仅观察。"
                "下一步等待重新站回下沿或形成新的次级别多头结构；反抽失败则转入空头跟踪。"
            ),
            "permission": "observe_only",
            "tone": "warning",
            "dominant_evidence": _support_oppose_labels(supporting),
            "opposing_evidence": _support_oppose_labels(opposing),
            "next_trigger": "重新站回下沿并形成次级别多头结构，才恢复多头计划；反抽失败则转入空头跟踪。",
            "show_trade_action": False,
        }

    if overall_bias == "bearish":
        return {
            "resolved_state": "breakdown_aligned_bearish",
            "headline": "跌破确认，综合结构同步偏空",
            "message": (
                "经典图形跌破下沿，且综合结构同步偏空。"
                "系统将方向状态切换为下破跟踪，不再保留原区间支撑假设。"
                "新空头计划需要等待反抽失败或下一级周期触发，不直接按已跌幅追空。"
            ),
            "permission": "conditional_short",
            "tone": "negative",
            "dominant_evidence": _support_oppose_labels(supporting),
            "opposing_evidence": _support_oppose_labels(opposing),
            "next_trigger": "等待反抽失败或下一级周期触发确认，不直接按已跌幅追空。",
            "show_trade_action": True,
        }

    return {
        "resolved_state": "breakdown_conflicted",
        "headline": "局部跌破，综合进入冲突观望",
        "message": (
            "经典图形已跌破下沿，但综合结构未形成一致空头。"
            "系统切换为冲突观望，暂停方向性入场，只保留关键位跟踪。"
        ),
        "permission": "observe_only",
        "tone": "caution",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "等待综合结构方向一致后再开放执行权限。",
        "show_trade_action": False,
    }


def _decide_breakout(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)

    if overall_bias == "bullish":
        return {
            "resolved_state": "breakout_aligned_bullish",
            "headline": "突破确认，综合结构同步偏多",
            "message": (
                "经典图形突破上沿，且综合结构同步偏多。"
                "系统将方向状态切换为突破跟踪；新多头计划需要等待回踩守住或下一级周期触发，避免在过度拉升后直接追价。"
            ),
            "permission": "conditional_long",
            "tone": "positive",
            "dominant_evidence": _support_oppose_labels(supporting),
            "opposing_evidence": _support_oppose_labels(opposing),
            "next_trigger": "等待回踩守住或下一级周期触发确认，不直接追价。",
            "show_trade_action": True,
        }

    if overall_bias == "bearish":
        return {
            "resolved_state": "local_breakout_overall_bearish_downgraded",
            "headline": "局部突破但综合空头未解除",
            "message": (
                "经典图形出现上破，但综合结构仍由空头或风险模块主导。"
                "系统不把本次突破升级为多头执行信号，先按假突破风险观察。"
            ),
            "permission": "observe_only",
            "tone": "caution",
            "dominant_evidence": _support_oppose_labels(supporting),
            "opposing_evidence": _support_oppose_labels(opposing),
            "next_trigger": "需综合结构方向回归一致才恢复执行权限。",
            "show_trade_action": False,
        }

    return {
        "resolved_state": "breakout_conflicted",
        "headline": "局部突破，综合仍需确认",
        "message": (
            "经典图形上破，但综合结构尚未达成一致。"
            "系统保留突破观察，不开放方向性执行权限。"
        ),
        "permission": "observe_only",
        "tone": "caution",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "等待综合结构方向明确后再开放执行权限。",
        "show_trade_action": False,
    }


def _decide_invalidated(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return {
        "resolved_state": "pattern_invalidated",
        "headline": "形态已失效，旧入场依据不再成立",
        "message": (
            "最新收盘已经触发形态失效位，旧形态不再作为入场依据。"
            "系统已将该形态移入历史观察，等待新的摆动结构或经典图形重新生成。"
        ),
        "permission": "observe_only",
        "tone": "warning",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "等待新的摆动结构或经典图形重新生成后才恢复方向性入场。",
        "show_trade_action": False,
    }


def _decide_inside(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return {
        "resolved_state": "inside_range",
        "headline": "价格位于区间内部，维持区间观察",
        "message": (
            "价格仍在形态区间内部，系统维持区间观察。"
            "当前不生成突破或跌破方向结论，只跟踪上下沿收盘确认。"
        ),
        "permission": "observe_only",
        "tone": "neutral",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "等待价格收盘突破区间上沿或跌破下沿后生成方向结论。",
        "show_trade_action": False,
    }


def _decide_retest(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return {
        "resolved_state": "retest_phase",
        "headline": "回踩验证中",
        "message": (
            "价格已离开主要形态区域并进入回踩验证阶段。"
            "系统将根据边界收回、成交确认和次级别结构决定是否恢复原突破方向。"
        ),
        "permission": "observe_only",
        "tone": "neutral",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "回踩守住边界并给出次级别结构确认后恢复原突破方向；跌破则转入空头跟踪。",
        "show_trade_action": False,
    }


def _decide_default(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return {
        "resolved_state": "unresolved",
        "headline": "暂无明确方向结论",
        "message": "当前价格位置未触发明确的结构状态变化，系统暂不输出方向性建议。",
        "permission": "observe_only",
        "tone": "neutral",
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": "等待价格触发关键位后重新评估。",
        "show_trade_action": False,
    }
