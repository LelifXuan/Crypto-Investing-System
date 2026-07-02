from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Literal, Mapping

Bias = Literal["bullish", "bearish", "neutral", "mixed"]


DEFAULT_THRESHOLDS: dict[str, float] = {
    "spot_move_threshold_pct": 0.005,
    "wall_shift_threshold_pct": 0.02,
    "large_wall_shift_threshold_pct": 0.05,
    "near_wall_threshold_pct": 0.03,
    "far_wall_threshold_pct": 0.08,
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _pct_change(current: Any, previous: Any) -> float | None:
    current_number = _finite(current)
    previous_number = _finite(previous)
    if current_number is None or previous_number in {None, 0}:
        return None
    return (current_number - previous_number) / abs(previous_number)


def _distance_pct(level: Any, spot: Any) -> float | None:
    level_number = _finite(level)
    spot_number = _finite(spot)
    if level_number is None or spot_number in {None, 0}:
        return None
    return (level_number - spot_number) / spot_number


def _movement(change_pct: float | None, threshold: float) -> str:
    if change_pct is None:
        return "data_insufficient"
    if change_pct >= threshold:
        return "rising"
    if change_pct <= -threshold:
        return "falling"
    return "stable"


def _spot_direction(change_pct: float | None, threshold: float) -> str:
    if change_pct is None:
        return "unknown"
    if change_pct >= threshold:
        return "up"
    if change_pct <= -threshold:
        return "down"
    return "flat"


def _level_label(level_id: str) -> str:
    return {
        "call_wall": "Call Wall",
        "put_wall": "Put Wall",
        "max_pain": "Max Pain",
    }[level_id]


def _parse_expiry(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _is_friday(day: datetime) -> bool:
    return day.weekday() == 4


def _third_friday(year: int, month: int) -> datetime:
    day = datetime(year, month, 1)
    while not _is_friday(day):
        day += timedelta(days=1)
    return day + timedelta(days=14)


def _last_friday(year: int, month: int) -> datetime:
    if month == 12:
        day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        day = datetime(year, month + 1, 1) - timedelta(days=1)
    while not _is_friday(day):
        day -= timedelta(days=1)
    return day


def _expiry_calendar_context(
    selected_expiry: str | None,
    source_dte: int | None,
) -> dict[str, Any]:
    expiry = _parse_expiry(selected_expiry)
    if expiry is None:
        return {
            "selected_expiry": selected_expiry,
            "source_dte": source_dte,
            "cycle": "unknown",
            "labels": ["到期日待确认"],
            "note": "缺少可解析到期日，暂不使用交割周期提高期权墙结论权重。",
        }

    is_quarter_month = expiry.month in {3, 6, 9, 12}
    last_friday = _last_friday(expiry.year, expiry.month)
    third_friday = _third_friday(expiry.year, expiry.month)
    labels = ["月度交割"] if expiry.date() == last_friday.date() else ["非标准到期日"]
    cycle = "monthly" if "月度交割" in labels else "weekly_or_custom"
    if is_quarter_month and expiry.date() == last_friday.date():
        cycle = "quarterly"
        labels.insert(0, "季度交割")
        if abs((expiry - third_friday).days) <= 7:
            labels.append("四巫日窗口")
        labels.append("ETF调仓窗口")

    note = (
        "该到期日处于重要交割/调仓窗口，期权墙与 Max Pain 的迁移需要结合现价同步性和 OI 变化解读。"
        if cycle == "quarterly"
        else "月度到期日前后仓位滚动可能放大，期权墙与 Max Pain 不应脱离现价变化单独解读。"
        if cycle == "monthly"
        else "非标准到期日的墙位迁移需要降低与月季交割周期的可比性。"
    )
    return {
        "selected_expiry": expiry.date().isoformat(),
        "source_dte": source_dte,
        "cycle": cycle,
        "labels": labels,
        "note": note,
        "monthly_expiry": last_friday.date().isoformat(),
        "quad_witching_reference": third_friday.date().isoformat()
        if is_quarter_month
        else None,
    }


def _signal_for_level(
    level_id: str,
    movement: str,
    spot_direction: str,
) -> tuple[str, Bias, str, str]:
    if movement == "data_insufficient":
        return ("data_insufficient", "neutral", "unavailable", "关键价位历史样本不足")
    if movement == "stable":
        return (
            "wall_stable",
            "neutral",
            "unconfirmed",
            f"{_level_label(level_id)} 暂未出现有效迁移",
        )

    if level_id == "call_wall":
        if movement == "rising" and spot_direction == "up":
            return (
                "bullish_confirmed",
                "bullish",
                "confirmed",
                "上方 Call 持仓重心上移，并获得现价同步确认",
            )
        if movement == "rising" and spot_direction == "down":
            return (
                "divergence_watch",
                "mixed",
                "divergent",
                "上方 Call 持仓重心上移，但现价没有跟随，属于结构分歧",
            )
        if movement == "rising":
            return (
                "bullish_expectation_unconfirmed",
                "bullish",
                "unconfirmed",
                "上方 Call 持仓重心上移，但现价尚未确认",
            )
        if movement == "falling" and spot_direction == "down":
            return (
                "bearish_confirmed",
                "bearish",
                "confirmed",
                "上方 Call 持仓重心回落，并与现价走弱一致",
            )
        if movement == "falling" and spot_direction == "up":
            return (
                "spot_up_options_not_confirmed",
                "mixed",
                "divergent",
                "现价上行，但上方 Call 持仓重心回落，期权结构未跟随",
            )
        return (
            "bearish_expectation_unconfirmed",
            "bearish",
            "unconfirmed",
            "上方 Call 持仓重心回落，但现价尚未确认",
        )

    if level_id == "put_wall":
        if movement == "rising" and spot_direction == "up":
            return (
                "bullish_confirmed",
                "bullish",
                "confirmed",
                "下方 Put 保护集中区上移，并与现价走强一致",
            )
        if movement == "rising" and spot_direction == "down":
            return (
                "defensive_demand_unconfirmed",
                "mixed",
                "divergent",
                "下方 Put 保护集中区上移，但现价走弱，防御需求与趋势方向分歧",
            )
        if movement == "rising":
            return (
                "defensive_demand_watch",
                "neutral",
                "unconfirmed",
                "下方 Put 保护集中区上移，需等待现价确认",
            )
        if movement == "falling" and spot_direction == "down":
            return (
                "bearish_confirmed",
                "bearish",
                "confirmed",
                "下方 Put 保护集中区下移，并与现价走弱一致",
            )
        if movement == "falling" and spot_direction == "up":
            return (
                "spot_up_options_not_confirmed",
                "mixed",
                "divergent",
                "现价上行，但下方 Put 保护集中区下移，期权保护未跟随",
            )
        return (
            "bearish_expectation_unconfirmed",
            "bearish",
            "unconfirmed",
            "下方 Put 保护集中区下移，但现价尚未确认",
        )

    if movement == "rising" and spot_direction == "up":
        return (
            "bullish_confirmed",
            "bullish",
            "confirmed",
            "Max Pain 持仓重心上移，并获得现价同步确认",
        )
    if movement == "rising" and spot_direction in {"down", "flat"}:
        return (
            "position_center_up_unconfirmed",
            "mixed",
            "divergent",
            "Max Pain 持仓重心上移，但现价尚未同步确认",
        )
    if movement == "falling" and spot_direction == "down":
        return (
            "bearish_confirmed",
            "bearish",
            "confirmed",
            "Max Pain 持仓重心下移，并获得现价同步确认",
        )
    if movement == "falling":
        return (
            "position_center_down_unconfirmed",
            "mixed",
            "divergent",
            "Max Pain 持仓重心下移，但现价尚未同步确认",
        )
    return ("wall_stable", "neutral", "unconfirmed", "Max Pain 暂未出现有效迁移")


def _build_level(
    *,
    level_id: str,
    current: Any,
    previous: Any,
    spot_price: Any,
    spot_direction: str,
    threshold: float,
) -> dict[str, Any]:
    change_pct = _pct_change(current, previous)
    movement = _movement(change_pct, threshold)
    signal, bias, confirmation, explanation = _signal_for_level(level_id, movement, spot_direction)
    return {
        "id": level_id,
        "label": _level_label(level_id),
        "value": _finite(current),
        "previous_value": _finite(previous),
        "shift_pct": change_pct,
        "movement": movement,
        "distance_pct": _distance_pct(current, spot_price),
        "signal": signal,
        "bias": bias,
        "confirmation": confirmation,
        "explanation": explanation,
    }


def _confidence(
    *,
    status: str,
    confirmed_count: int,
    divergent_count: int,
    data_quality_status: str,
    degraded: bool,
) -> str:
    if status != "ok" or data_quality_status in {"data_insufficient", "missing"}:
        return "low"
    if data_quality_status in {"stale", "degraded"} or degraded:
        return "medium" if confirmed_count >= 2 else "low"
    if confirmed_count >= 3 and divergent_count == 0:
        return "high"
    if confirmed_count >= 2:
        return "medium"
    return "low"


def _aggregate(levels: Mapping[str, Mapping[str, Any]]) -> tuple[str, Bias, str, list[str]]:
    bullish_confirmed = [
        level["label"] for level in levels.values()
        if level.get("bias") == "bullish" and level.get("confirmation") == "confirmed"
    ]
    bearish_confirmed = [
        level["label"] for level in levels.values()
        if level.get("bias") == "bearish" and level.get("confirmation") == "confirmed"
    ]
    divergent = [
        level["label"] for level in levels.values()
        if level.get("confirmation") == "divergent"
    ]
    conflicts: list[str] = []
    if bullish_confirmed and bearish_confirmed:
        conflicts.append("关键价位出现多空确认分歧，需要降低方向结论权重")
        return ("mixed", "mixed", "divergent", conflicts)
    if divergent:
        conflicts.append("部分关键价位迁移与现价方向不一致")
    if len(bullish_confirmed) >= 2:
        return ("bullish_confirmed", "bullish", "confirmed", conflicts)
    if len(bearish_confirmed) >= 2:
        return ("bearish_confirmed", "bearish", "confirmed", conflicts)
    if divergent:
        return ("divergence_watch", "mixed", "divergent", conflicts)
    if any(level.get("bias") == "bullish" for level in levels.values()):
        return ("bullish_expectation_unconfirmed", "bullish", "unconfirmed", conflicts)
    if any(level.get("bias") == "bearish" for level in levels.values()):
        return ("bearish_expectation_unconfirmed", "bearish", "unconfirmed", conflicts)
    return ("wall_stable", "neutral", "unconfirmed", conflicts)


def _status_label(overall_signal: str) -> str:
    return {
        "bullish_confirmed": "关键价位结构偏多并获得现价确认",
        "bearish_confirmed": "关键价位结构偏空并获得现价确认",
        "bullish_expectation_unconfirmed": "关键价位结构偏多但等待现价确认",
        "bearish_expectation_unconfirmed": "关键价位结构偏空但等待现价确认",
        "divergence_watch": "关键价位迁移与现价存在分歧",
        "mixed": "关键价位结构多空分歧",
        "wall_stable": "关键价位结构暂未明显迁移",
        "data_insufficient": "关键价位样本不足",
    }.get(overall_signal, "关键价位解释暂不可用")


def evaluate_key_levels_axis(
    *,
    spot_price: float | None,
    previous_spot_price: float | None,
    call_wall: float | None,
    previous_call_wall: float | None,
    put_wall: float | None,
    previous_put_wall: float | None,
    max_pain: float | None,
    previous_max_pain: float | None,
    data_quality_status: str,
    provider: str | None = None,
    quality: str | None = None,
    stale: bool = False,
    rollover: bool = False,
    provider_changed: bool = False,
    thresholds: Mapping[str, float] | None = None,
    oi_context: Mapping[str, Any] | None = None,
    iv_context: Mapping[str, Any] | None = None,
    comparison_basis: str | None = None,
    comparison_timestamp: str | None = None,
    comparison_is_same_day: bool | None = None,
    selected_expiry: str | None = None,
    source_dte: int | None = None,
) -> dict[str, Any]:
    """Evaluate option key-level migration as an evidence axis.

    This function is deliberately pure and dict-based so it can be reused by
    dashboard, market context, tests, and future monitoring jobs without
    importing API or persistence layers.
    """

    config = {**DEFAULT_THRESHOLDS, **dict(thresholds or {})}
    spot_change_pct = _pct_change(spot_price, previous_spot_price)
    spot_direction = _spot_direction(spot_change_pct, config["spot_move_threshold_pct"])
    levels = {
        "call_wall": _build_level(
            level_id="call_wall",
            current=call_wall,
            previous=previous_call_wall,
            spot_price=spot_price,
            spot_direction=spot_direction,
            threshold=config["wall_shift_threshold_pct"],
        ),
        "put_wall": _build_level(
            level_id="put_wall",
            current=put_wall,
            previous=previous_put_wall,
            spot_price=spot_price,
            spot_direction=spot_direction,
            threshold=config["wall_shift_threshold_pct"],
        ),
        "max_pain": _build_level(
            level_id="max_pain",
            current=max_pain,
            previous=previous_max_pain,
            spot_price=spot_price,
            spot_direction=spot_direction,
            threshold=config["wall_shift_threshold_pct"],
        ),
    }
    usable_levels = [
        level for level in levels.values()
        if level["value"] is not None and level["previous_value"] is not None
    ]
    status = "ok" if _finite(spot_price) is not None and usable_levels else "data_insufficient"
    if status == "ok":
        overall_signal, bias, confirmation, conflicts = _aggregate(levels)
    else:
        overall_signal, bias, confirmation, conflicts = (
            "data_insufficient",
            "neutral",
            "unavailable",
            ["关键价位或现价样本不足"],
        )

    evidence = [
        {
            "code": level["id"],
            "label": level["label"],
            "signal": level["signal"],
            "bias": level["bias"],
            "confirmation": level["confirmation"],
            "explanation": level["explanation"],
        }
        for level in levels.values()
    ]
    expiry_context = _expiry_calendar_context(selected_expiry, source_dte)
    evidence.append(
        {
            "code": "expiry_calendar",
            "label": "交割日上下文",
            "signal": expiry_context["cycle"],
            "bias": "neutral",
            "confirmation": "metadata",
            "explanation": (
                f"{'、'.join(expiry_context['labels'])}：{expiry_context['note']}"
            ),
        }
    )
    if rollover:
        evidence.append(
            {
                "code": "expiry_rollover",
                "label": "到期日切换",
                "signal": "confidence_degraded",
                "bias": "neutral",
                "confirmation": "metadata",
                "explanation": "历史序列发生到期日切换，迁移幅度需要降低权重解读",
            }
        )
    if provider_changed:
        evidence.append(
            {
                "code": "provider_changed",
                "label": "主链来源切换",
                "signal": "confidence_degraded",
                "bias": "neutral",
                "confirmation": "metadata",
                "explanation": "期权主链来源发生切换，历史迁移需要降低权重解读",
            }
        )

    if not oi_context:
        evidence.append(
            {
                "code": "oi_context_missing",
                "label": "OI 上下文",
                "signal": "quality_note",
                "bias": "neutral",
                "confirmation": "metadata",
                "explanation": "OI 上下文不足，关键价位结论仅按已计算墙位迁移处理",
            }
        )
    if not iv_context:
        evidence.append(
            {
                "code": "iv_context_missing",
                "label": "IV 上下文",
                "signal": "quality_note",
                "bias": "neutral",
                "confirmation": "metadata",
                "explanation": "IV 上下文不足，暂不提高方向置信度",
            }
        )

    confirmed_count = sum(1 for level in levels.values() if level["confirmation"] == "confirmed")
    divergent_count = sum(1 for level in levels.values() if level["confirmation"] == "divergent")
    confidence = _confidence(
        status=status,
        confirmed_count=confirmed_count,
        divergent_count=divergent_count,
        data_quality_status=data_quality_status,
        degraded=stale or rollover or provider_changed or quality in {"stale", "degraded"},
    )
    summary = _status_label(overall_signal)
    if status == "ok":
        level_bits = [
            f"{level['label']}：{level['explanation']}"
            for level in levels.values()
            if level["signal"] != "data_insufficient"
        ]
        if level_bits:
            summary = f"{summary}；" + "；".join(level_bits[:3])

    return {
        "schema_version": "options_wall_signal.v1",
        "status": status,
        "overall_signal": overall_signal,
        "bias": bias,
        "confirmation": confirmation,
        "confidence": confidence,
        "status_label": _status_label(overall_signal),
        "spot_price": _finite(spot_price),
        "previous_spot_price": _finite(previous_spot_price),
        "spot_change_pct": spot_change_pct,
        "spot_direction": spot_direction,
        "expiry_context": expiry_context,
        "provider": provider,
        "quality": quality or data_quality_status,
        "comparison_basis": comparison_basis or "previous_available_point",
        "comparison_timestamp": comparison_timestamp,
        "comparison_is_same_day": bool(comparison_is_same_day),
        "levels": levels,
        "call_wall_today": levels["call_wall"]["value"],
        "call_wall_previous": levels["call_wall"]["previous_value"],
        "call_wall_shift_pct": levels["call_wall"]["shift_pct"],
        "put_wall_today": levels["put_wall"]["value"],
        "put_wall_previous": levels["put_wall"]["previous_value"],
        "put_wall_shift_pct": levels["put_wall"]["shift_pct"],
        "max_pain_today": levels["max_pain"]["value"],
        "max_pain_previous": levels["max_pain"]["previous_value"],
        "max_pain_shift_pct": levels["max_pain"]["shift_pct"],
        "spot_vs_call_wall_pct": levels["call_wall"]["distance_pct"],
        "spot_vs_put_wall_pct": levels["put_wall"]["distance_pct"],
        "spot_vs_max_pain_pct": levels["max_pain"]["distance_pct"],
        "evidence": evidence,
        "conflicts": conflicts,
        "summary": summary,
        "risk_note": "",
        "direct_command": False,
    }
