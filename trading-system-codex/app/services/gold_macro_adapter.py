from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

LAYER_SCORE_KEYS = {
    "rates_policy": "rates_policy_score",
    "inflation": "inflation_score",
    "growth_labor": "growth_labor_score",
    "liquidity_credit": "liquidity_credit_score",
    "cross_asset_confirmation": "cross_asset_score",
    "event_window": "event_window_score",
}


def _as_mapping(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload or {})


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _indicator_value(item: Mapping[str, Any]) -> str:
    value = _number(item.get("value_num"))
    if value is None:
        text = item.get("value_text")
        return str(text) if text not in (None, "") else "-"
    unit = str(item.get("unit") or "").strip()
    if unit == "%":
        return f"{value:.2f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f}{unit}"
    return f"{value:.2f}{unit}"


def _indicator_label(item: Mapping[str, Any]) -> str:
    return str(
        item.get("display_label") or item.get("label") or item.get("indicator_key") or "宏观指标"
    )


def _layer_fact(layer: Mapping[str, Any]) -> str:
    label = str(layer.get("label_cn") or layer.get("layer_key") or "宏观层级")
    score = _number(layer.get("score"))
    bias = str(layer.get("bias") or "").strip()
    effective = int(_number(layer.get("effective_count")) or 0)
    total = int(_number(layer.get("total_count")) or 0)
    score_text = f"{score:.0f}" if score is not None else "-"
    count_text = f"，有效指标 {effective}/{total}" if total else ""
    bias_text = f"，{bias}" if bias else ""
    return f"{label}评分 {score_text}{bias_text}{count_text}。"


def _top_indicator_facts(layer: Mapping[str, Any], limit: int = 2) -> list[str]:
    facts: list[str] = []
    indicators = layer.get("indicators") if isinstance(layer.get("indicators"), list) else []
    for item in indicators:
        if not isinstance(item, Mapping):
            continue
        if not item.get("is_scored") and item.get("value_num") in (None, ""):
            continue
        facts.append(f"{_indicator_label(item)}：{_indicator_value(item)}。")
        if len(facts) >= limit:
            break
    return facts


def _find_indicator(
    layers: list[Mapping[str, Any]], indicator_key: str
) -> Mapping[str, Any] | None:
    for layer in layers:
        indicators = layer.get("indicators") if isinstance(layer.get("indicators"), list) else []
        for item in indicators:
            if isinstance(item, Mapping) and item.get("indicator_key") == indicator_key:
                return item
    return None


def _real_yield_5y_fact(layers: list[Mapping[str, Any]]) -> str | None:
    item = _find_indicator(layers, "real_yield_5y")
    if not item:
        return None
    value = _number(item.get("value_num"))
    if value is None:
        return None
    source = str(item.get("source_provider") or "").strip()
    source_text = f"，来源 {source}" if source else ""
    return (
        f"美国5年期通胀保值国债收益率为 {value:.2f}%{source_text}，"
        "直接影响黄金短中期持有机会成本。"
    )


def macro_overview_to_gold_macro(payload: Any) -> dict[str, Any]:
    data = _as_mapping(payload)
    layers = [item for item in data.get("layers") or [] if isinstance(item, Mapping)]
    layer_map = {str(item.get("layer_key") or ""): dict(item) for item in layers}
    layer_contributions = dict(data.get("layer_contributions") or {})
    completeness = dict(data.get("data_completeness") or {})

    result: dict[str, Any] = {
        "total_score": _number(data.get("total_score") or data.get("score")) or 50.0,
        "score_band": data.get("score_band"),
        "confidence": data.get("confidence"),
        "data_completeness": completeness,
        "layer_contributions": layer_contributions,
        "layers": layers,
        "layer_map": layer_map,
        "warnings": list(data.get("warnings") or []),
        "event_window_status": data.get("event_window_status"),
        "event_window_summary": data.get("event_window_summary"),
    }

    for layer_key, score_key in LAYER_SCORE_KEYS.items():
        layer = layer_map.get(layer_key)
        score = _number((layer or {}).get("score"))
        result[score_key] = score if score is not None else 50.0

    result["macro_layer_facts"] = [
        _layer_fact(layer)
        for layer_key in (
            "rates_policy",
            "inflation",
            "growth_labor",
            "liquidity_credit",
            "cross_asset_confirmation",
            "event_window",
        )
        if (layer := layer_map.get(layer_key))
    ]
    result["macro_indicator_facts"] = [
        fact
        for layer_key in (
            "rates_policy",
            "inflation",
            "cross_asset_confirmation",
            "liquidity_credit",
        )
        for fact in _top_indicator_facts(layer_map.get(layer_key, {}), 2)
    ]
    if real_yield_fact := _real_yield_5y_fact(layers):
        result["macro_indicator_facts"].insert(0, real_yield_fact)
    result["liquidity_facts"] = (
        [
            _layer_fact(layer_map["liquidity_credit"]),
            *_top_indicator_facts(layer_map["liquidity_credit"], 4),
        ]
        if "liquidity_credit" in layer_map
        else []
    )
    result["cross_asset_facts"] = (
        [
            _layer_fact(layer_map["cross_asset_confirmation"]),
            *_top_indicator_facts(layer_map["cross_asset_confirmation"], 3),
        ]
        if "cross_asset_confirmation" in layer_map
        else []
    )

    return result


def _gold_macro_snapshot(macro: dict) -> dict:
    """从 macro layer_map 提取 4 个核心宏观指标 + 计算黄金视角的多空 bias。

    重要：以下 bias 计算**仅针对黄金视角**，不复用 registry 的 risk-assets bias。

    阈值来源: app/monitoring/configs/macro_scoring_registry.v1.json
    方向重写: 见 V2 spec §4.6.2-4.6.6
    """
    layer_map = (macro or {}).get("layer_map") or {}
    indicators_by_layer = {
        layer["layer_key"]: layer.get("indicators", [])
        for layer in (macro or {}).get("layers", [])
        if isinstance(layer, dict)
    }
    flat_indicators = [
        ind for ind_list in indicators_by_layer.values() for ind in ind_list
    ]

    def find(indicator_key: str) -> dict | None:
        for ind in flat_indicators:
            if ind.get("indicator_key") == indicator_key:
                return ind
        return None

    def value_of(ind: dict | None) -> float | None:
        if not ind:
            return None
        raw = ind.get("value_num")
        if raw is None:
            return None
        # Defensive casting: value_num may come as str from MacroOverviewService when
        # numeric transform failed; try float, fall back to None.
        if isinstance(raw, (int, float)):
            return float(raw)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    real_yield = find("real_yield_5y") or find("real_yield_10y")
    dxy = find("dxy") or find("dollar_index")
    cpi = find("cpi_yoy")
    vix = find("vix")

    ry_val = value_of(real_yield)
    dxy_val = value_of(dxy)
    cpi_val = value_of(cpi)
    vix_val = value_of(vix)

    # 流动性冲击检测
    liquidity_shock = (
        vix_val is not None and vix_val >= 25
        and dxy_val is not None and dxy_val >= 105
        and ry_val is not None and ry_val >= 2.0
    )

    def bias_for_real_yield(value):
        if value is None:
            return ("missing", "数据不足")
        if value <= 0.5:
            return ("strong_bullish", "实际利率低于 0.5%，持有黄金机会成本极低，强烈支持黄金")
        if value <= 1.5:
            return ("bullish", "实际利率处于低位，债券吸引力弱，利好黄金")
        if value >= 2.8:
            return ("strong_bearish", "实际利率高于 2.8%，持有黄金机会成本高，强烈压制黄金")
        if value >= 2.0:
            return ("bearish", "实际利率偏高，债券吸引力上升，压制黄金")
        return ("neutral", "实际利率处于中性区间")

    def bias_for_dxy(value):
        if value is None:
            return ("missing", "数据不足")
        if liquidity_shock:
            return ("bearish", "DXY 走强叠加 VIX 急升，流动性冲击模式：黄金短期先被卖补保证金")
        if value <= 98:
            return ("strong_bullish", "美元指数极弱，黄金 USD 计价上涨空间打开")
        if value <= 102:
            return ("bullish", "美元偏弱，支撑黄金")
        if value >= 108:
            return ("strong_bearish", "美元极强，强势压制黄金")
        if value >= 105:
            return ("bearish", "美元走强，压制黄金")
        return ("neutral", "美元处于中性区间")

    def bias_for_cpi(value):
        if value is None:
            return ("missing", "数据不足")
        # CPI 上行 + RealYield 下行 + DXY 不强 → 看多
        if value >= 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 偏高但实际利率下行 / 美元不强 → 抗通胀需求支撑黄金")
        # CPI 上行 + RealYield 上行 + DXY 上行 → 看空
        if value >= 3.0 and ry_val is not None and ry_val >= 2.0:
            if dxy_val is not None and dxy_val >= 105:
                return ("bearish", "CPI 高位 + 实际利率上行 + 美元走强，紧缩周期压制黄金")
        # CPI 温和回落 + RealYield 下行 + DXY 走弱 → 看多（降息预期）
        if 1.5 <= value < 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 温和回落 + 实际利率下行 + 美元不强，降息预期支撑黄金")
        # CPI 快速下行 → 等待确认
        if value < 1.0:
            return ("neutral", "CPI 快速下行，衰退风险升温，需结合 VIX/DXY/ETF 流向确认（不输出单方向）")
        return ("neutral", "CPI 处于中性区间，需结合其他宏观信号综合判断")

    def bias_for_vix(value):
        if value is None:
            return ("missing", "数据不足")
        if liquidity_shock:
            return ("bearish", "VIX 急升叠加 DXY 走强 + 实际利率上行 → 流动性冲击模式，黄金先被卖补保证金，待压力缓和后回到避险逻辑")
        if value >= 28:
            return ("strong_bullish", "VIX 急升，市场风险厌恶强烈，黄金避险属性显著")
        if value >= 22:
            return ("bullish", "VIX 上升，避险需求支撑黄金")
        if value <= 12:
            return ("strong_bearish", "VIX 极低，市场过度乐观，避险需求缺失")
        if value <= 15:
            return ("bearish", "VIX 偏低，避险需求不足")
        return ("neutral", "VIX 处于中性区间")

    def build(ind, bias_fn, fallback_label):
        if not ind:
            return {
                "value": None,
                "unit": "",
                "display_label": fallback_label,
                "source": "",
                "observation_ts": "",
                "bias": "missing",
                "bias_reason": "数据不足",
                "threshold_low": None,
                "threshold_high": None,
                "status": "missing",
            }
        # Use value_of() to coerce string → float defensively (MacroOverviewService may pass str)
        raw_value = value_of(ind)
        bias, reason = bias_fn(raw_value)
        return {
            "value": raw_value,
            "unit": ind.get("unit", ""),
            "display_label": ind.get("display_label", fallback_label),
            "source": ind.get("source_provider", ""),
            "observation_ts": ind.get("observation_ts", ""),
            "bias": bias,
            "bias_reason": reason,
            "threshold_low": 0.5 if "yield" in ind.get("indicator_key", "") else None,
            "threshold_high": 2.8 if "yield" in ind.get("indicator_key", "") else None,
            "status": ind.get("status", "unknown"),
        }

    return {
        "real_yield_10y": build(real_yield, bias_for_real_yield, "美国10年期实际利率 (TIPS yield)"),
        "dxy": build(dxy, bias_for_dxy, "美元指数 DXY"),
        "cpi_yoy": build(cpi, bias_for_cpi, "美国 CPI 同比"),
        "vix": build(vix, bias_for_vix, "VIX 波动率"),
        "_diagnostics": {
            "liquidity_shock_detected": liquidity_shock,
            "liquidity_shock_definition": "VIX>=25 AND DXY>=105 AND RealYield>=2.0",
        },
    }
