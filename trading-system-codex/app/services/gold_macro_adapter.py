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
