from __future__ import annotations

PERMISSION_LABELS = {
    "observe_only": "仅观察",
    "conditional_long": "条件做多",
    "conditional_short": "条件做空",
    "allow": "已触发",
    "blocked": "暂停执行",
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
    """Translate local pattern state and fused bias into user-facing guidance.

    The output intentionally avoids internal event keys and placeholder question marks. If the
    next actionable trigger is unknown, it is omitted rather than shown as a fake value.
    """

    resolved = _build_decision(
        local_state=local_state,
        overall_bias=normalize_bias(overall_bias or "neutral"),
        contribution_breakdown=contribution_breakdown or {},
        primary_drivers=primary_drivers or [],
        opposing_factors=opposing_factors or [],
    )
    permission = resolved["permission"]
    next_trigger = resolved.get("next_trigger") or ""

    return {
        "local_state": local_state,
        "overall_bias": overall_bias or "neutral",
        "resolved_state": resolved["resolved_state"],
        "headline": resolved["headline"],
        "message": resolved["message"],
        "permission": permission,
        "permission_label": PERMISSION_LABELS.get(permission, permission),
        "tone": resolved["tone"],
        "dominant_evidence": resolved.get("dominant_evidence", []),
        "opposing_evidence": resolved.get("opposing_evidence", []),
        "next_trigger": next_trigger,
        "show_trade_action": resolved.get("show_trade_action", False),
    }


def normalize_bias(bias: str) -> str:
    value = str(bias).lower().strip()
    if value in {"bullish", "strong_bullish", "weak_bullish"}:
        return "bullish"
    if value in {"bearish", "strong_bearish", "weak_bearish"}:
        return "bearish"
    return "neutral"


def _build_decision(
    local_state: str,
    overall_bias: str,
    contribution_breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    handler = {
        "breakdown": _decide_breakdown,
        "breakout": _decide_breakout,
        "invalidated": _decide_invalidated,
        "inside": _decide_inside,
        "retest": _decide_retest,
    }.get(local_state, _decide_default)
    return handler(overall_bias, contribution_breakdown, primary_drivers, opposing_factors)


def _classify_contributions(breakdown: dict[str, float]) -> tuple[list[str], list[str]]:
    supporting = [key for key, value in breakdown.items() if value > 0.03]
    opposing = [key for key, value in breakdown.items() if value < -0.03]
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
        "fused": "综合判断",
    }
    return [name_map.get(key, key) for key in keys]


def _base_payload(
    *,
    resolved_state: str,
    headline: str,
    message: str,
    permission: str,
    tone: str,
    supporting: list[str],
    opposing: list[str],
    next_trigger: str = "",
    show_trade_action: bool = False,
) -> dict:
    return {
        "resolved_state": resolved_state,
        "headline": headline,
        "message": message,
        "permission": permission,
        "tone": tone,
        "dominant_evidence": _support_oppose_labels(supporting),
        "opposing_evidence": _support_oppose_labels(opposing),
        "next_trigger": next_trigger,
        "show_trade_action": show_trade_action,
    }


def _decide_breakdown(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    if overall_bias == "bullish":
        return _base_payload(
            resolved_state="local_breakdown_overall_bullish_downgraded",
            headline="局部支撑破坏，综合多头降级为观察",
            message=(
                "局部形态已经跌破下沿，但综合结构仍有其他模块支撑。系统不会继续把旧区间当作有效支撑，"
                "需要等待价格重新站回下沿，或形成新的次级别多头结构后再恢复多头执行权限。"
            ),
            permission="observe_only",
            tone="warning",
            supporting=supporting,
            opposing=opposing,
            next_trigger="重新站回下沿并获得收盘确认，或次级别出现新的多头结构。",
        )
    if overall_bias == "bearish":
        return _base_payload(
            resolved_state="breakdown_aligned_bearish",
            headline="跌破确认，综合结构同步偏空",
            message=(
                "局部形态跌破下沿，且综合结构同步偏空。后续应重点观察反抽是否失败，"
                "不建议在已经跌开后直接追空。"
            ),
            permission="conditional_short",
            tone="negative",
            supporting=supporting,
            opposing=opposing,
            next_trigger="等待反抽失败或下一周期触发确认。",
            show_trade_action=True,
        )
    return _base_payload(
        resolved_state="breakdown_conflicted",
        headline="局部跌破，综合进入冲突观察",
        message="局部形态已经跌破，但综合结构尚未形成一致空头。当前只保留关键位跟踪，不开放方向性执行。",
        permission="observe_only",
        tone="caution",
        supporting=supporting,
        opposing=opposing,
        next_trigger="等待综合结构方向重新统一。",
    )


def _decide_breakout(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    if overall_bias == "bullish":
        return _base_payload(
            resolved_state="breakout_aligned_bullish",
            headline="突破确认，综合结构同步偏多",
            message=(
                "局部形态突破上沿，且综合结构同步偏多。后续重点观察回踩是否守住突破位，"
                "避免在短线过度拉升后追价。"
            ),
            permission="conditional_long",
            tone="positive",
            supporting=supporting,
            opposing=opposing,
            next_trigger="等待回踩守住或下一周期触发确认。",
            show_trade_action=True,
        )
    if overall_bias == "bearish":
        return _base_payload(
            resolved_state="local_breakout_overall_bearish_downgraded",
            headline="局部突破，但综合空头尚未解除",
            message="局部形态出现上破，但综合结构仍偏空。当前按假突破风险观察，暂不升级为多头执行信号。",
            permission="observe_only",
            tone="caution",
            supporting=supporting,
            opposing=opposing,
            next_trigger="需要综合结构方向回归一致后再恢复执行权限。",
        )
    return _base_payload(
        resolved_state="breakout_conflicted",
        headline="局部突破，综合仍需确认",
        message="局部形态上破，但综合结构尚未达成一致。当前保留突破观察，不开放方向性执行权限。",
        permission="observe_only",
        tone="caution",
        supporting=supporting,
        opposing=opposing,
        next_trigger="等待综合结构方向明确。",
    )


def _decide_invalidated(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return _base_payload(
        resolved_state="pattern_invalidated",
        headline="旧形态已经失效",
        message="最新价格已经触发旧形态失效位，系统不再把该形态作为入场依据，只保留价格位置和摆动结构观察。",
        permission="observe_only",
        tone="warning",
        supporting=supporting,
        opposing=opposing,
        next_trigger="等待新的结构区间或摆动序列形成。",
    )


def _decide_inside(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    if overall_bias == "bullish":
        headline = "价格位于区间内部，综合结构略偏多"
        message = "价格仍在形态内部运行，偏多结论需要向上收盘突破或回踩确认后才能增强。"
        tone = "positive"
    elif overall_bias == "bearish":
        headline = "价格位于区间内部，综合结构略偏空"
        message = "价格仍在形态内部运行，偏空结论需要向下收盘跌破或反抽失败后才能增强。"
        tone = "caution"
    else:
        headline = "价格位于区间内部，维持区间观察"
        message = "价格仍在形态区间内部，当前不生成突破或跌破方向结论，只跟踪上下沿收盘确认。"
        tone = "neutral"
    return _base_payload(
        resolved_state="inside_range",
        headline=headline,
        message=message,
        permission="observe_only",
        tone=tone,
        supporting=supporting,
        opposing=opposing,
    )


def _decide_retest(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return _base_payload(
        resolved_state="retest_phase",
        headline="价格接近边界，等待回踩或反抽确认",
        message="价格已经接近形态边界，方向判断需要收盘确认和成交量配合，当前不把边界触碰直接当成突破。",
        permission="observe_only",
        tone="neutral",
        supporting=supporting,
        opposing=opposing,
        next_trigger="等待边界外收盘确认，或回到区间内部后重新评估。",
    )


def _decide_default(
    overall_bias: str,
    breakdown: dict[str, float],
    primary_drivers: list[str],
    opposing_factors: list[str],
) -> dict:
    supporting, opposing = _classify_contributions(breakdown)
    return _base_payload(
        resolved_state="no_actionable_pattern",
        headline="暂无明确形态触发",
        message="当前形态没有形成可执行的突破、跌破或失效信号，先保留结构观察。",
        permission="observe_only",
        tone="neutral",
        supporting=supporting,
        opposing=opposing,
    )
