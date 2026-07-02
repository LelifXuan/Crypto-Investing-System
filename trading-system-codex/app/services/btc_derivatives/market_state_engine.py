from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

VALID_DATA_STATES = {"ok", "live", "stale", "partial"}
HIGH_QUALITY_STATES = {"ok", "live", "stale"}

SIGNAL_TRANSLATIONS: dict[str, dict[str, str]] = {
    "price_up_oi_up": {
        "label": "价格上涨且持仓增加",
        "tone": "supports_long",
        "explanation": "杠杆资金顺势进入，趋势延续证据增强。",
    },
    "price_down_oi_up": {
        "label": "价格下跌且持仓增加",
        "tone": "supports_short",
        "explanation": "新增仓位压低价格，下行压力上升。",
    },
    "price_down_oi_down": {
        "label": "价格与持仓同步下降",
        "tone": "deleveraging",
        "explanation": "市场处于去杠杆释放阶段，追空性价比下降。",
    },
    "flat_oi_up": {
        "label": "横盘期间持仓增加",
        "tone": "compression",
        "explanation": "杠杆仓位在区间内累积，后续波动可能放大，但方向尚未确认。",
    },
    "flat": {
        "label": "价格与持仓变化有限",
        "tone": "neutral",
        "explanation": "期货层暂未形成清晰方向增量。",
    },
    "positive_hot": {
        "label": "资金费率偏热",
        "tone": "crowding_warning",
        "explanation": "多头支付成本抬升，继续追多的风险回报下降。",
    },
    "negative_hot": {
        "label": "负资金费率偏热",
        "tone": "crowding_warning",
        "explanation": "空头支付成本抬升，价格企稳时需警惕反抽或逼空。",
    },
    "neutral": {
        "label": "资金费率中性",
        "tone": "neutral",
        "explanation": "资金成本暂未形成明显拥挤信号。",
    },
    "basis_rising": {
        "label": "期货溢价偏高",
        "tone": "supports_long",
        "explanation": "远期合约相对现货溢价抬升，市场仍在为上方空间或资金成本定价。",
    },
    "basis_falling": {
        "label": "期货溢价收窄",
        "tone": "weakens_long",
        "explanation": "远期溢价回落，杠杆多头或基差交易热度下降。",
    },
    "call_skew_high": {
        "label": "Call 追涨需求偏高",
        "tone": "upside_squeeze_watch",
        "explanation": "市场正在为上涨或逼空情形支付更高期权价格。",
    },
    "put_skew_high": {
        "label": "Put 保护需求偏高",
        "tone": "downside_protection",
        "explanation": "市场愿意为下跌保护支付更高价格，单纯追多的置信度应下调。",
    },
    "skew_neutral": {
        "label": "Skew 中性",
        "tone": "neutral",
        "explanation": "Call 与 Put 的相对保护需求未形成明显倾斜。",
    },
    "iv_high": {
        "label": "隐含波动率偏高",
        "tone": "expensive_options",
        "explanation": "直接买入保护的成本偏高，应比较有限风险价差或降低敞口。",
    },
    "iv_neutral": {
        "label": "隐含波动率中性",
        "tone": "neutral",
        "explanation": "波动率定价未明显偏高或偏低，需要结合期限结构和保护成本判断。",
    },
    "rising": {
        "label": "持仓集中区上移",
        "tone": "key_level_rising",
        "explanation": "期权持仓分布重心正在抬高。",
    },
    "falling": {
        "label": "持仓集中区下移",
        "tone": "key_level_falling",
        "explanation": "期权持仓分布重心正在下移。",
    },
    "stable": {
        "label": "持仓集中区稳定",
        "tone": "neutral",
        "explanation": "关键持仓价位近期没有明显迁移。",
    },
    "cheap": {
        "label": "保护成本偏低",
        "tone": "hedge_cost_supportive",
        "explanation": "保护成本相对可接受，可优先比较有限风险保护方案。",
    },
    "expensive": {
        "label": "保护成本偏高",
        "tone": "hedge_cost_warning",
        "explanation": "直接买入保护成本不低，应优先比较借记价差或降低网格敞口。",
    },
    "data_insufficient": {
        "label": "数据不足",
        "tone": "neutral",
        "explanation": "当前数据不足以形成可靠推定。",
    },
}


def _display_item(code: str) -> dict[str, str]:
    translated = SIGNAL_TRANSLATIONS.get(code)
    if translated:
        return {
            "label": translated["label"],
            "tone": translated["tone"],
            "explanation": translated["explanation"],
        }
    return {
        "label": "解释暂不可用",
        "tone": "neutral",
        "explanation": "该内部信号尚未配置用户可见解释，当前不参与页面结论。",
    }


def _signal_is_valid(code: str | None) -> bool:
    return bool(code) and code != "data_insufficient" and code in SIGNAL_TRANSLATIONS


def _confidence_for_signals(
    data_quality_status: str,
    signals: list[str],
    *,
    decisive: bool = False,
) -> str:
    valid_count = sum(1 for signal in signals if _signal_is_valid(signal))
    if decisive and data_quality_status in VALID_DATA_STATES and valid_count >= 1:
        return "high" if data_quality_status in HIGH_QUALITY_STATES else "medium"
    if data_quality_status in HIGH_QUALITY_STATES and valid_count >= 2:
        return "high"
    if data_quality_status in VALID_DATA_STATES and valid_count >= 1:
        return "medium"
    return "low"


def _group(
    signals: list[str],
    *,
    conclusion: str,
    implication: str,
    tone: str,
    confidence: str,
) -> dict[str, Any]:
    items = [_display_item(code) for code in signals]
    basis = [
        item["label"]
        for item in items
        if item["label"] not in {"数据不足", "解释暂不可用"}
    ]
    return {
        "signals": signals,
        "display_items": items,
        "conclusion": conclusion,
        "basis": basis,
        "implication": implication,
        "tone": tone,
        "confidence": confidence,
    }


def _key_level_group(
    wall_movement: Mapping[str, str],
    max_pain_movement: str,
    *,
    conclusion: str,
    implication: str,
    tone: str,
    confidence: str,
) -> dict[str, Any]:
    signals = [
        wall_movement.get("call_wall", "data_insufficient"),
        wall_movement.get("put_wall", "data_insufficient"),
        max_pain_movement,
    ]
    names = ["Call Wall", "Put Wall", "Max Pain"]
    movement_labels = {
        "rising": "上移",
        "falling": "下移",
        "stable": "稳定",
        "mixed": "震荡",
        "data_insufficient": "历史不足",
    }
    items = [
        {
            "label": f"{name} {movement_labels.get(code, '历史不足')}",
            "tone": _display_item(code)["tone"],
            "explanation": _display_item(code)["explanation"],
        }
        for name, code in zip(names, signals, strict=True)
    ]
    return {
        "signals": signals,
        "display_items": items,
        "conclusion": conclusion,
        "basis": [item["label"] for item in items],
        "implication": implication,
        "tone": tone,
        "confidence": confidence,
    }


def _axis_tone(axis: Mapping[str, Any]) -> str:
    bias = str(axis.get("bias") or "neutral")
    if bias == "bullish":
        return "bullish"
    if bias == "bearish":
        return "bearish"
    if bias == "mixed":
        return "mixed"
    return "neutral"


def _key_level_axis_group(axis: Mapping[str, Any]) -> dict[str, Any]:
    evidence = [
        item for item in axis.get("evidence", [])
        if isinstance(item, Mapping) and item.get("code") in {"call_wall", "put_wall", "max_pain"}
    ]
    items = [
        {
            "label": str(item.get("label") or "关键价位"),
            "tone": str(item.get("bias") or "neutral"),
            "explanation": str(item.get("explanation") or "解释暂不可用"),
        }
        for item in evidence
    ]
    if not items:
        items = [
            {
                "label": "关键价位样本不足",
                "tone": "neutral",
                "explanation": "当前关键价位数据不足，暂不形成方向判断。",
            }
        ]
    basis = [
        f"{item['label']}：{item['explanation']}"
        for item in items
    ]
    return {
        "signals": [str(axis.get("overall_signal") or "data_insufficient")],
        "display_items": items,
        "conclusion": str(
            axis.get("status_label")
            or axis.get("summary")
            or "关键价位解释暂不可用"
        ),
        "basis": basis,
        "implication": str(
            axis.get("summary")
            or "等待 Call Wall、Put Wall 与 Max Pain 的有效迁移证据。"
        ),
        "tone": _axis_tone(axis),
        "confidence": str(axis.get("confidence") or "low"),
    }


def _inference_blocks(groups: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    titles = {
        "futures": "期货与永续",
        "options": "期权情绪",
        "key_levels": "关键价位",
        "hedge_cost": "保护成本",
    }
    return [
        {
            "id": key,
            "title": titles[key],
            "conclusion": str(groups[key]["conclusion"]),
            "basis": list(groups[key]["basis"]),
            "implication": str(groups[key]["implication"]),
            "tone": str(groups[key]["tone"]),
            "confidence": str(groups[key].get("confidence", "low")),
        }
        for key in ("futures", "options", "key_levels", "hedge_cost")
    ]


def _overall_confidence(groups: Mapping[str, Mapping[str, Any]]) -> str:
    values = [str(group.get("confidence", "low")) for group in groups.values()]
    if values.count("high") >= 2 and "low" not in values:
        return "high"
    if "high" in values or values.count("medium") >= 2:
        return "medium"
    return "low"


def build_market_state(
    *,
    price_oi_state: str,
    funding_state: str,
    iv_state: str,
    skew_state: str,
    wall_movement: Mapping[str, str],
    max_pain_movement: str,
    data_quality_status: str,
    basis_state: str = "data_insufficient",
    hedge_cost_state: str = "data_insufficient",
    technical_bias: str | None = None,
    options_wall_signal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    helps_long: list[str] = []
    hurts_long: list[str] = []
    helps_short: list[str] = []
    hurts_short: list[str] = []
    conflicts: list[str] = []
    warnings = [
        "最大痛点用于观察持仓分布迁移，不作为价格预测。",
        "期权墙用于观察持仓集中与对冲敏感区，不作为确定支撑或阻力。",
    ]
    state = "balanced"
    score = 50

    if price_oi_state == "price_up_oi_up":
        helps_long.append("price_up_oi_up")
        hurts_short.append("price_up_oi_up")
        score += 8
    elif price_oi_state == "price_down_oi_up":
        hurts_long.append("price_down_oi_up")
        helps_short.append("price_down_oi_up")
        score -= 8
    elif price_oi_state == "price_down_oi_down":
        helps_long.append("deleveraging_flush")
        hurts_short.append("late_short_risk")
        state = "deleveraging"
        score = 44

    if skew_state == "call_skew_high":
        helps_long.append("call_skew_high")
        hurts_short.append("call_skew_high")
    elif skew_state == "put_skew_high":
        hurts_long.append("put_skew_high")
        helps_short.append("put_skew_high")

    if funding_state == "positive_hot":
        hurts_long.append("funding_overheated")
        helps_short.append("long_crowding")
    elif funding_state == "negative_hot":
        helps_long.append("short_crowding")
        hurts_short.append("funding_negative_extreme")

    key_levels_axis = dict(options_wall_signal or {})
    has_key_levels_axis = key_levels_axis.get("status") == "ok"
    if has_key_levels_axis:
        axis_bias = str(key_levels_axis.get("bias") or "neutral")
        axis_confirmation = str(key_levels_axis.get("confirmation") or "unconfirmed")
        axis_signal = str(key_levels_axis.get("overall_signal") or "data_insufficient")
        if axis_bias == "bullish":
            helps_long.append(f"key_levels_{axis_signal}")
            hurts_short.append(f"key_levels_{axis_signal}")
            if axis_confirmation != "confirmed":
                conflicts.append("关键价位结构偏多但现价确认不足。")
        elif axis_bias == "bearish":
            hurts_long.append(f"key_levels_{axis_signal}")
            helps_short.append(f"key_levels_{axis_signal}")
            if axis_confirmation != "confirmed":
                conflicts.append("关键价位结构偏空但现价确认不足。")
        elif axis_bias == "mixed":
            conflicts.extend(
                str(item) for item in key_levels_axis.get("conflicts", []) if item
            )
    else:
        if wall_movement.get("call_wall") == "rising":
            helps_long.append("call_wall_rising")
            hurts_short.append("call_wall_rising")
        if wall_movement.get("put_wall") == "falling":
            hurts_long.append("put_wall_falling")
            helps_short.append("put_wall_falling")

    if state != "deleveraging":
        if price_oi_state == "price_up_oi_up" and skew_state == "call_skew_high":
            state = "upside_squeeze_risk"
            score = 68
        elif price_oi_state == "price_down_oi_up" and skew_state == "put_skew_high":
            state = "downside_stress"
            score = 32
        elif price_oi_state in {"flat_oi_up", "flat"}:
            state = "compression"

    if basis_state == "basis_rising":
        helps_long.append("basis_rising")
        hurts_short.append("basis_rising")
    elif basis_state == "basis_falling":
        hurts_long.append("basis_falling")
        helps_short.append("basis_falling")

    if technical_bias == "bearish" and (
        price_oi_state == "price_up_oi_up" or skew_state == "call_skew_high"
    ):
        conflicts.append("技术面偏空，但上涨增仓或 Call 偏贵提高追空与逼空风险。")
    if technical_bias == "bullish" and (
        price_oi_state == "price_down_oi_up" or skew_state == "put_skew_high"
    ):
        conflicts.append("技术面偏多，但下跌增仓或 Put 保护需求削弱多头置信度。")

    futures_conclusion = "杠杆资金暂未形成清晰方向"
    futures_implication = "价格、持仓、资金费率与基差尚未形成同向共振，方向敞口不宜上调。"
    futures_tone = "neutral"
    if price_oi_state == "price_up_oi_up":
        futures_conclusion = "杠杆资金偏多，但多头已有拥挤"
        futures_implication = "趋势延续证据存在；若资金费率继续偏热，追多性价比下降。"
        futures_tone = "mixed"
    elif price_oi_state == "price_down_oi_up":
        futures_conclusion = "新增仓位偏空，下行压力上升"
        futures_implication = "现货和多网格应优先比较保护成本或降低杠杆。"
        futures_tone = "bearish"
    elif price_oi_state == "price_down_oi_down":
        futures_conclusion = "市场处于去杠杆释放阶段"
        futures_implication = "风险释放不等于趋势反转，但晚追空的赔率下降。"
        futures_tone = "deleveraging"

    options_conclusion = "期权市场未形成明显方向偏好"
    options_implication = "IV 与 Skew 均未明显倾斜，期权层当前不给出额外方向增量。"
    options_tone = "neutral"
    if skew_state == "put_skew_high":
        options_conclusion = "下行保护需求偏高"
        options_implication = "单纯追多的置信度下降；现货或多网格可比较 Put Spread 保护成本。"
        options_tone = "bearish"
    elif skew_state == "call_skew_high":
        options_conclusion = "上行追涨或逼空保护需求升高"
        options_implication = "空网格或空头仓位应关注 Call / Call Spread 保护成本。"
        options_tone = "bullish"

    key_conclusion = "关键持仓价位迁移不明显"
    key_implication = "当前仓位结构暂未提供额外方向增量。"
    key_tone = "neutral"
    if has_key_levels_axis:
        key_conclusion = str(
            key_levels_axis.get("status_label")
            or key_levels_axis.get("summary")
            or "关键价位解释暂不可用"
        )
        key_implication = str(
            key_levels_axis.get("summary")
            or "等待 Call Wall、Put Wall 与 Max Pain 的有效迁移证据。"
        )
        key_tone = _axis_tone(key_levels_axis)
    elif wall_movement.get("call_wall") == "rising":
        key_conclusion = "上方持仓集中区正在抬高"
        key_implication = "价格接近 Call Wall 时，空网格需重新评估上破保护成本。"
        key_tone = "bullish"
    elif wall_movement.get("put_wall") == "falling":
        key_conclusion = "下方保护集中区继续下移"
        key_implication = "市场开始为更低价格配置保护，多头仓位需关注下破风险。"
        key_tone = "bearish"

    hedge_conclusion = "保护成本处于可观察区间"
    hedge_implication = "继续比较单买期权、借记价差与降低网格敞口。"
    hedge_tone = "neutral"
    if hedge_cost_state == "expensive" or iv_state == "iv_high":
        hedge_conclusion = "保护成本偏高"
        hedge_implication = "单腿买权成本不低，优先比较借记价差或直接降低网格敞口。"
        hedge_tone = "warning"
    elif hedge_cost_state == "cheap":
        hedge_conclusion = "保护成本偏低"
        hedge_implication = "可优先比较有限风险保护，但仍需检查流动性与价差。"
        hedge_tone = "supportive"

    futures_signals = [price_oi_state, funding_state, basis_state]
    options_signals = [iv_state, skew_state]
    key_signals = (
        [str(key_levels_axis.get("overall_signal") or "data_insufficient")]
        if has_key_levels_axis
        else [
            wall_movement.get("call_wall", "data_insufficient"),
            wall_movement.get("put_wall", "data_insufficient"),
            max_pain_movement,
        ]
    )
    hedge_signals = [hedge_cost_state if hedge_cost_state != "neutral" else iv_state]
    evidence_groups = {
        "futures": _group(
            futures_signals,
            conclusion=futures_conclusion,
            implication=futures_implication,
            tone=futures_tone,
            confidence=_confidence_for_signals(data_quality_status, futures_signals),
        ),
        "options": _group(
            options_signals,
            conclusion=options_conclusion,
            implication=options_implication,
            tone=options_tone,
            confidence=_confidence_for_signals(data_quality_status, options_signals),
        ),
        "key_levels": (
            _key_level_axis_group(key_levels_axis)
            if has_key_levels_axis
            else _key_level_group(
                wall_movement,
                max_pain_movement,
                conclusion=key_conclusion,
                implication=key_implication,
                tone=key_tone,
                confidence=_confidence_for_signals(data_quality_status, key_signals),
            )
        ),
        "hedge_cost": _group(
            hedge_signals,
            conclusion=hedge_conclusion,
            implication=hedge_implication,
            tone=hedge_tone,
            confidence=_confidence_for_signals(
                data_quality_status,
                hedge_signals,
                decisive=hedge_cost_state in {"expensive", "cheap"} or iv_state == "iv_high",
            ),
        ),
    }
    inference_blocks = _inference_blocks(evidence_groups)
    display_items = [
        item
        for group in evidence_groups.values()
        for item in group["display_items"]
    ]
    return {
        "market_state": state,
        "confidence": _overall_confidence(evidence_groups),
        "score": score,
        "helps_long": helps_long,
        "hurts_long": hurts_long,
        "helps_short": helps_short,
        "hurts_short": hurts_short,
        "supports_long": helps_long,
        "weakens_long": hurts_long,
        "supports_short": helps_short,
        "weakens_short": hurts_short,
        "conflicts": conflicts,
        "display_items": display_items,
        "inference_blocks": inference_blocks,
        "evidence_groups": evidence_groups,
        "bias_effect": {
            "long": "supports_but_crowded"
            if helps_long and hurts_long
            else "supports"
            if helps_long
            else "weakens"
            if hurts_long
            else "neutral",
            "short": "raises_squeeze_risk"
            if state == "upside_squeeze_risk"
            else "supports"
            if helps_short
            else "weakens"
            if hurts_short
            else "neutral",
        },
        "wall_movement": dict(wall_movement),
        "max_pain_movement": max_pain_movement,
        "key_levels_axis": key_levels_axis,
        "derivatives_axes": {
            "key_levels_axis": key_levels_axis,
        },
        "direct_command": "none; evidence layer only",
        "warnings": warnings,
    }


def decision_cards(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    blocks = {
        str(block.get("id")): block
        for block in analysis.get("inference_blocks", [])
        if isinstance(block, Mapping)
    }
    futures = blocks.get("futures", {})
    options = blocks.get("options", {})
    levels = blocks.get("key_levels", {})
    hedge = blocks.get("hedge_cost", {})
    return [
        {
            "id": "market_state",
            "label": "当前衍生品状态",
            "state": str(futures.get("tone", "neutral")),
            "confidence": str(futures.get("confidence", "low")),
            "summary": str(futures.get("conclusion", "当前数据不足以形成清晰判断")),
            "conclusion": str(futures.get("conclusion", "当前数据不足以形成清晰判断")),
            "basis": list(futures.get("basis", [])),
            "implication": str(futures.get("implication", "等待更多有效数据。")),
        },
        {
            "id": "primary_risk",
            "label": "主要风险",
            "state": str(options.get("tone", "neutral")),
            "confidence": str(options.get("confidence", "low")),
            "summary": str(options.get("conclusion", "当前风险方向尚不清晰")),
            "conclusion": str(options.get("conclusion", "当前风险方向尚不清晰")),
            "basis": [*list(options.get("basis", [])), *list(levels.get("basis", []))],
            "implication": " ".join(
                value
                for value in (
                    str(options.get("implication", "")),
                    str(levels.get("implication", "")),
                )
                if value
            ),
        },
        {
            "id": "strategy_implication",
            "label": "策略含义",
            "state": str(hedge.get("tone", "neutral")),
            "confidence": str(hedge.get("confidence", "low")),
            "summary": str(hedge.get("conclusion", "保护成本尚待观察")),
            "conclusion": str(hedge.get("conclusion", "保护成本尚待观察")),
            "basis": list(hedge.get("basis", [])),
            "implication": str(hedge.get("implication", "等待更多有效数据。")),
        },
    ]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _distance_pct(value: Any, spot: Any) -> float | None:
    level = _finite(value)
    current = _finite(spot)
    if level is None or current in {None, 0}:
        return None
    return (level - current) / current


def _movement_label(value: str | None) -> str:
    return {
        "rising": "上移",
        "falling": "下移",
        "stable": "稳定",
        "mixed": "震荡",
        "data_insufficient": "历史不足",
    }.get(str(value or ""), "历史不足")


def build_key_level_cards(
    *,
    spot_price: float | None,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
    maturity_bucket: str,
    source_expiry: str | None,
    source_dte: int | None,
    wall_movement: Mapping[str, str],
    max_pain_movement: str,
) -> list[dict[str, Any]]:
    call_move = _movement_label(wall_movement.get("call_wall"))
    put_move = _movement_label(wall_movement.get("put_wall"))
    pain_move = _movement_label(max_pain_movement)
    call_meaning = (
        "当前链数据不足，暂时无法判断上方 Call 持仓集中区。"
        if _finite(call_wall) is None
        else "上方 Call 持仓集中区正在抬高，空网格接近该区域时应检查上破保护。"
        if call_move == "上移"
        else "观察现价与上方持仓集中区的距离，接近时重新评估上破保护成本。"
    )
    put_meaning = (
        "当前链数据不足，暂时无法判断下方 Put 持仓集中区。"
        if _finite(put_wall) is None
        else "下方 Put 持仓集中区继续下移，市场对更低价格的保护需求增加。"
        if put_move == "下移"
        else "观察现价与下方保护集中区的距离，接近时关注下行波动和保护需求。"
    )
    pain_meaning = (
        "当前链数据不足，暂时无法计算持仓分布重心。"
        if _finite(max_pain) is None
        else f"当前持仓分布重心{pain_move}，用于观察期权仓位结构迁移。"
    )
    maturity_meaning = (
        f"当前追踪 {maturity_bucket} 期限桶，实际到期日 "
        f"{source_expiry or '数据不足'}，剩余 DTE "
        f"{source_dte if source_dte is not None else '未知'}；换月点会在历史中明确标记。"
    )
    return [
        {
            "id": "call_wall",
            "label": "Call Wall",
            "subtitle": "上方 Call 持仓集中区",
            "value": call_wall,
            "distance_pct": _distance_pct(call_wall, spot_price),
            "movement": call_move,
            "current_meaning": call_meaning,
            "knowledge_term": "Call Wall",
        },
        {
            "id": "put_wall",
            "label": "Put Wall",
            "subtitle": "下方 Put 持仓集中区",
            "value": put_wall,
            "distance_pct": _distance_pct(put_wall, spot_price),
            "movement": put_move,
            "current_meaning": put_meaning,
            "knowledge_term": "Put Wall",
        },
        {
            "id": "max_pain",
            "label": "Max Pain",
            "subtitle": "期权 OI 理论最小赔付价",
            "value": max_pain,
            "distance_pct": _distance_pct(max_pain, spot_price),
            "movement": pain_move,
            "current_meaning": pain_meaning,
            "knowledge_term": "Max Pain",
        },
        {
            "id": "constant_maturity",
            "label": "Constant Maturity",
            "subtitle": "固定剩余期限追踪",
            "value": maturity_bucket,
            "distance_pct": None,
            "movement": "当前追踪",
            "current_meaning": maturity_meaning,
            "knowledge_term": "Constant Maturity",
        },
    ]
