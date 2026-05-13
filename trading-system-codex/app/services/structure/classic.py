from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .common import (
    DetectionBundle,
    Pivot,
    ScoreBundle,
    StructureActiveItem,
    StructureAlert,
    StructureEvent,
    StructureGeometry,
    build_structure_dedupe_key,
    build_structure_id,
    clamp,
    event_name,
    isoformat,
    to_decimal,
    to_float,
)

UTC = timezone.utc


class ClassicScorer:
    def detect(self, instrument_id: str, timeframe: str, candles: list, pivots: list[Pivot]) -> DetectionBundle:
        candidates = detect_classic_patterns(candles, pivots, max_candidates=4)
        if not candidates:
            return DetectionBundle(score=ScoreBundle(
                system="classic", direction="neutral", direction_score=0.0,
                confidence=0.30, quality=0.45, freshness=0.70, evidence_count=0,
                top_reasons=["经典图形模块暂未识别到高质量确认形态。"],
                conflict_flags=[], metadata={"regime_hint": "transition", "candidate_weight": 0.0, "candidate_count": 0},
            ))

        best = candidates[0]
        score = ScoreBundle(
            system="classic", direction=best["bias"], direction_score=best["direction_score"],
            confidence=best["confidence"], quality=best["quality"], freshness=0.88,
            evidence_count=len(best.get("points", [])), top_reasons=best.get("reasons", []),
            conflict_flags=["candidate_only"] if best["status"] != "confirmed" else [],
            metadata={
                "regime_hint": "transition",
                "candidate_count": len(candidates),
                "candidate_types": [c["pattern_type"] for c in candidates],
            },
        )

        all_geo: list[StructureGeometry] = []
        for c in candidates:
            for g in c.get("geometry", []):
                all_geo.append(_make_structure_geometry(instrument_id, timeframe, g, c))

        items = [_make_active_item(instrument_id, timeframe, c) for c in candidates[:3]]

        return DetectionBundle(score=score, active_items=items, geometry=all_geo, events=[], alerts=[])


def linear_fit(points: list[Pivot]) -> tuple[float, float, float]:
    n = len(points)
    if n < 2:
        return 0.0, 0.0, 0.0
    xs = [float(p.index) for p in points]
    ys = [p.price for p in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den != 0 else 0.0
    intercept = mean_y - slope * mean_x
    errors = [abs(y - (slope * x + intercept)) / max(abs(y), 0.0001) for x, y in zip(xs, ys)]
    mean_error = sum(errors) / n
    return slope, intercept, mean_error


def detect_classic_patterns(candles: list, pivots: list[Pivot], *, max_candidates: int = 4) -> list[dict]:
    if len(candles) < 40 or len(pivots) < 4:
        return []
    highs = [p for p in pivots if p.kind == "high"]
    lows = [p for p in pivots if p.kind == "low"]
    if len(highs) < 4 or len(lows) < 4:
        return []

    detectors = [
        lambda: detect_rectangles(candles, highs, lows),
        lambda: detect_triangles(candles, highs, lows),
        lambda: detect_wedges(candles, highs, lows),
        lambda: detect_double_top_bottom(candles, highs, lows),
    ]
    all_candidates: list[dict] = []
    for fn in detectors:
        all_candidates.extend(fn())

    all_candidates.sort(
        key=lambda x: (
            x["status"] == "confirmed",
            x["confidence"] * 0.6 + x["quality"] * 0.4,
        ),
        reverse=True,
    )
    return all_candidates[:max_candidates]


def detect_rectangles(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    if len(highs) < 5 or len(lows) < 5:
        return results
    hs = highs[-5:]
    ls = lows[-5:]
    last_close = to_float(candles[-1].close)
    tol = _adaptive_tolerance(candles)

    resistance = sum(p.price for p in hs) / len(hs)
    support = sum(p.price for p in ls) / len(ls)
    avg_price = max((resistance + support) / 2, 1.0)

    high_range = (max(p.price for p in hs) - min(p.price for p in hs)) / avg_price
    low_range = (max(p.price for p in ls) - min(p.price for p in ls)) / avg_price

    if high_range > tol * 1.5 or low_range > tol * 1.5:
        return results

    width = (resistance - support) / avg_price
    if width > 0.18 or width < 0.005:
        return results

    if last_close > resistance:
        pattern_type = "rectangle_breakout"
        display_name = "矩形突破"
        status = "confirmed"
        bias = "bullish"
        direction_score = 0.58
        confidence_val = 0.66
        quality_val = 0.68
        reasons = ["价格向上突破矩形整理区间上沿。"]
    elif last_close < support:
        pattern_type = "rectangle_breakdown"
        display_name = "矩形跌破"
        status = "confirmed"
        bias = "bearish"
        direction_score = -0.58
        confidence_val = 0.66
        quality_val = 0.68
        reasons = ["价格向下跌破矩形整理区间下沿。"]
    else:
        pattern_type = "rectangle_range"
        display_name = "矩形整理"
        status = "candidate"
        bias = "neutral"
        direction_score = 0.0
        confidence_val = 0.48
        quality_val = 0.55
        reasons = ["价格在矩形箱体内运行，关注突破方向。"]

    geometry = [
        {
            "kind": "resistance_line",
            "points": _line_points(hs[0], hs[-1], resistance, "矩形上沿"),
            "labels": ["矩形上沿"],
            "meta_json": {
                "role": "resistance", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
        {
            "kind": "support_line",
            "points": _line_points(ls[0], ls[-1], support, "矩形下沿"),
            "labels": ["矩形下沿"],
            "meta_json": {
                "role": "support", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
        {
            "kind": "zone",
            "points": [_pt(hs[0], "zone_top", resistance), _pt(ls[0], "zone_bottom", support)],
            "labels": ["矩形区域"],
            "meta_json": {
                "role": "rectangle_zone", "layer": "secondary", "priority": 5,
                "confidence": confidence_val, "visible_by_default": False, "style_hint": "dashed",
            },
        },
    ]

    results.append({
        "pattern_type": pattern_type, "display_name": display_name,
        "status": status, "bias": bias, "direction_score": direction_score,
        "confidence": confidence_val, "quality": quality_val,
        "points": list(hs) + list(ls), "levels": {"resistance": resistance, "support": support},
        "reasons": reasons, "geometry": geometry,
        "bar_age": max(p.index for p in hs + ls),
    })
    return results


def detect_triangles(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    if len(highs) < 4 or len(lows) < 4:
        return results
    hs = highs[-4:]
    ls = lows[-4:]
    last_close = to_float(candles[-1].close)
    tol = _adaptive_tolerance(candles)

    upper_slope, upper_intercept, upper_err = linear_fit(hs)
    lower_slope, lower_intercept, lower_err = linear_fit(ls)

    max_err = max(upper_err, lower_err)
    if max_err > tol * 2.0:
        return results

    upper_flat = abs(upper_slope) < tol * 0.3
    lower_flat = abs(lower_slope) < tol * 0.3
    upper_falling = upper_slope < -tol * 0.2
    lower_rising = lower_slope > tol * 0.2

    if upper_flat and lower_rising:
        pattern_type = "ascending_triangle"
        display_name = "上升三角形"
        bias = "bullish"
    elif lower_flat and upper_falling:
        pattern_type = "descending_triangle"
        display_name = "下降三角形"
        bias = "bearish"
    elif upper_falling and lower_rising:
        pattern_type = "symmetrical_triangle"
        display_name = "对称三角形"
        bias = "neutral"
    else:
        return results

    left_idx = hs[0].index
    right_idx = hs[-1].index
    upper_left_price = upper_intercept + upper_slope * left_idx
    upper_right_price = upper_intercept + upper_slope * right_idx
    lower_left_price = lower_intercept + lower_slope * left_idx
    lower_right_price = lower_intercept + lower_slope * right_idx

    resistance_line_price = upper_intercept + upper_slope * hs[-1].index
    support_line_price = lower_intercept + lower_slope * ls[-1].index

    all_points = list(hs) + list(ls)

    if bias == "bullish":
        confirmed = last_close > resistance_line_price
        direction_score = 0.64 if confirmed else 0.32
        reasons = [
            "上升三角形：上方压力基本持平，低点逐步抬高。",
            "收盘突破压力线，形态确认。" if confirmed else "尚未突破压力线，等待放量确认。",
        ]
    elif bias == "bearish":
        confirmed = last_close < support_line_price
        direction_score = -0.64 if confirmed else -0.32
        reasons = [
            "下降三角形：下方支撑基本持平，高点逐步降低。",
            "收盘跌破支撑线，形态确认。" if confirmed else "尚未跌破支撑线，等待放量确认。",
        ]
    else:
        confirmed = False
        direction_score = 0.0
        reasons = [
            "对称三角形：高点和低点同时收敛，等待方向选择。",
            "尚未突破任何边界，当前作为候选观察。",
        ]

    status = "confirmed" if confirmed else "candidate"
    confidence_val = 0.72 if confirmed else 0.54
    quality_val = 0.72
    bar_age = max(p.index for p in all_points)

    upper_line_points = [_pt(hs[0], "三角形上边界", upper_left_price), _pt(hs[-1], "三角形上边界", upper_right_price)]
    lower_line_points = [_pt(ls[0], "三角形下边界", lower_left_price), _pt(ls[-1], "三角形下边界", lower_right_price)]

    geometry = [
        {
            "kind": "upper_boundary",
            "points": upper_line_points,
            "labels": ["上边界"],
            "meta_json": {
                "role": "upper_boundary", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
        {
            "kind": "lower_boundary",
            "points": lower_line_points,
            "labels": ["下边界"],
            "meta_json": {
                "role": "lower_boundary", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
    ]

    results.append({
        "pattern_type": pattern_type, "display_name": display_name,
        "status": status, "bias": bias, "direction_score": direction_score,
        "confidence": confidence_val, "quality": quality_val,
        "points": all_points,
        "levels": {
            "resistance_slope": upper_slope, "support_slope": lower_slope,
            "resistance_line": resistance_line_price, "support_line": support_line_price,
        },
        "reasons": reasons, "geometry": geometry, "bar_age": bar_age,
    })
    return results


def detect_wedges(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    if len(highs) < 4 or len(lows) < 4:
        return results
    hs = highs[-4:]
    ls = lows[-4:]
    last_close = to_float(candles[-1].close)
    tol = _adaptive_tolerance(candles)

    upper_slope, upper_intercept, upper_err = linear_fit(hs)
    lower_slope, lower_intercept, lower_err = linear_fit(ls)

    max_err = max(upper_err, lower_err)
    if max_err > tol * 2.0:
        return results

    both_rising = upper_slope > tol * 0.2 and lower_slope > tol * 0.2
    both_falling = upper_slope < -tol * 0.2 and lower_slope < -tol * 0.2

    if both_rising and lower_slope > upper_slope * 1.2:
        pattern_type = "rising_wedge"
        display_name = "上升楔形"
        bias = "bearish"
    elif both_falling and upper_slope < lower_slope * 1.2:
        pattern_type = "falling_wedge"
        display_name = "下降楔形"
        bias = "bullish"
    else:
        return results

    left_idx = hs[0].index
    right_idx = hs[-1].index
    upper_left_price = upper_intercept + upper_slope * left_idx
    upper_right_price = upper_intercept + upper_slope * right_idx
    lower_left_price = lower_intercept + lower_slope * left_idx
    lower_right_price = lower_intercept + lower_slope * right_idx

    all_points = list(hs) + list(ls)
    bar_age = max(p.index for p in all_points)

    resistance_line_price = upper_intercept + upper_slope * hs[-1].index
    support_line_price = lower_intercept + lower_slope * ls[-1].index

    if bias == "bearish":
        confirmed = last_close < support_line_price
        direction_score = -0.68 if confirmed else -0.34
        reasons = [
            "上升楔形：两线同时上升但下轨更陡，看跌形态。",
            "收盘跌破楔形下轨，形态确认。" if confirmed else "尚未跌破下轨，作为楔形候选观察。",
        ]
    else:
        confirmed = last_close > resistance_line_price
        direction_score = 0.68 if confirmed else 0.34
        reasons = [
            "下降楔形：两线同时下降但上轨更陡，看涨形态。",
            "收盘突破楔形上轨，形态确认。" if confirmed else "尚未突破上轨，作为楔形候选观察。",
        ]

    status = "confirmed" if confirmed else "candidate"
    confidence_val = 0.70 if confirmed else 0.52
    quality_val = 0.68

    upper_line_points = [_pt(hs[0], "楔形上边界", upper_left_price), _pt(hs[-1], "楔形上边界", upper_right_price)]
    lower_line_points = [_pt(ls[0], "楔形下边界", lower_left_price), _pt(ls[-1], "楔形下边界", lower_right_price)]

    geometry = [
        {
            "kind": "upper_boundary",
            "points": upper_line_points,
            "labels": ["上边界"],
            "meta_json": {
                "role": "upper_boundary", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
        {
            "kind": "lower_boundary",
            "points": lower_line_points,
            "labels": ["下边界"],
            "meta_json": {
                "role": "lower_boundary", "layer": "primary", "priority": 10,
                "confidence": confidence_val, "visible_by_default": True, "style_hint": "solid",
            },
        },
    ]

    results.append({
        "pattern_type": pattern_type, "display_name": display_name,
        "status": status, "bias": bias, "direction_score": direction_score,
        "confidence": confidence_val, "quality": quality_val,
        "points": all_points,
        "levels": {
            "resistance_slope": upper_slope, "support_slope": lower_slope,
            "resistance_line": resistance_line_price, "support_line": support_line_price,
        },
        "reasons": reasons, "geometry": geometry, "bar_age": bar_age,
    })
    return results


def detect_double_top_bottom(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    last_close = to_float(candles[-1].close)
    tol = _adaptive_tolerance(candles)

    for left, right in _recent_pairs(highs):
        mids = [p for p in lows if left.index < p.index < right.index]
        if not mids:
            continue
        neckline_pivot = min(mids, key=lambda p: p.price)
        neckline = neckline_pivot.price
        delta = abs(left.price - right.price) / max((left.price + right.price) / 2.0, 1.0)
        tolerance = _local_tolerance(left.price, right.price, neckline)
        if delta > tolerance:
            continue
        confirmed = last_close < neckline
        direction_score = -0.72 if confirmed else -0.38
        conf = 0.80 if confirmed else 0.58
        qual = _pattern_quality(delta, tolerance, confirmed)

        line_left = neckline_pivot
        line_right = neckline_pivot
        if right.index > left.index:
            line_right = left
            line_left = left
        neckline_points = [_pt(neckline_pivot, "颈线", neckline)]
        neckline_points = _line_points(left, right, neckline, "颈线")

        geometry = [{
            "kind": "neckline",
            "points": neckline_points,
            "labels": ["双顶颈线"],
            "meta_json": {
                "role": "neckline", "layer": "primary", "priority": 10,
                "confidence": conf, "visible_by_default": True, "style_hint": "solid",
            },
        }]
        results.append({
            "pattern_type": "double_top", "display_name": "双顶",
            "status": "confirmed" if confirmed else "candidate",
            "bias": "bearish", "direction_score": direction_score,
            "confidence": conf, "quality": qual,
            "points": [left, neckline_pivot, right],
            "levels": {
                "neckline": neckline, "left_peak": left.price, "right_peak": right.price,
                "peak_delta_pct": delta, "tolerance_pct": tolerance,
            },
            "reasons": [
                "双顶形态路径已识别，两个高点接近且中间存在颈线低点。",
                "收盘已跌破颈线，双顶形态得到确认。" if confirmed else "尚未跌破颈线，当前作为双顶候选观察。",
            ],
            "geometry": geometry,
            "bar_age": max(left.index, right.index),
        })
        break

    for left, right in _recent_pairs(lows):
        mids = [p for p in highs if left.index < p.index < right.index]
        if not mids:
            continue
        neckline_pivot = max(mids, key=lambda p: p.price)
        neckline = neckline_pivot.price
        delta = abs(left.price - right.price) / max((left.price + right.price) / 2.0, 1.0)
        tolerance = _local_tolerance(left.price, right.price, neckline)
        if delta > tolerance:
            continue
        confirmed = last_close > neckline
        direction_score = 0.72 if confirmed else 0.38
        conf = 0.80 if confirmed else 0.58
        qual = _pattern_quality(delta, tolerance, confirmed)

        neckline_points = _line_points(left, right, neckline, "颈线")

        geometry = [{
            "kind": "neckline",
            "points": neckline_points,
            "labels": ["双底颈线"],
            "meta_json": {
                "role": "neckline", "layer": "primary", "priority": 10,
                "confidence": conf, "visible_by_default": True, "style_hint": "solid",
            },
        }]
        results.append({
            "pattern_type": "double_bottom", "display_name": "双底",
            "status": "confirmed" if confirmed else "candidate",
            "bias": "bullish", "direction_score": direction_score,
            "confidence": conf, "quality": qual,
            "points": [left, neckline_pivot, right],
            "levels": {
                "neckline": neckline, "left_trough": left.price, "right_trough": right.price,
                "peak_delta_pct": delta, "tolerance_pct": tolerance,
            },
            "reasons": [
                "双底形态路径已识别，两个低点接近且中间存在颈线高点。",
                "收盘已突破颈线，双底形态得到确认。" if confirmed else "尚未突破颈线，当前作为双底候选观察。",
            ],
            "geometry": geometry,
            "bar_age": max(left.index, right.index),
        })
        break

    return results


def _make_structure_geometry(
    instrument_id: str, timeframe: str, geo_dict: dict, pattern_dict: dict
) -> StructureGeometry:
    pattern_type = pattern_dict["pattern_type"]
    status = pattern_dict["status"]
    confidence_val = pattern_dict["confidence"]

    meta_json = dict(geo_dict.get("meta_json", {}))
    meta_json.update({
        "pattern_type": pattern_type,
        "confidence": confidence_val,
    })

    geometry_id = build_structure_id(
        "classic", timeframe, pattern_type, geo_dict.get("kind"), uuid4().hex[:8]
    )

    return StructureGeometry(
        geometry_id=geometry_id,
        instrument_id=instrument_id,
        timeframe=timeframe,
        snapshot_version="pending",
        system="classic",
        kind=geo_dict.get("kind", pattern_type),
        status=status,
        visible=True,
        points_json=geo_dict.get("points", []),
        labels_json=geo_dict.get("labels", [pattern_dict.get("display_name", "")]),
        meta_json=meta_json,
        created_at=datetime.now(timezone.utc),
    )


def _make_active_item(
    instrument_id: str, timeframe: str, pattern_dict: dict
) -> StructureActiveItem:
    pattern_type = pattern_dict["pattern_type"]
    status = pattern_dict["status"]
    generated_at = datetime.now(timezone.utc)

    structure_id = build_structure_id("classic", timeframe, pattern_type, uuid4().hex[:8])

    return StructureActiveItem(
        structure_id=structure_id,
        instrument_id=instrument_id,
        timeframe=timeframe,
        snapshot_version="pending",
        system="classic",
        structure_type=pattern_type,
        display_name=pattern_dict["display_name"],
        lifecycle_status=status,
        directional_bias=pattern_dict["bias"],
        confidence=to_decimal(pattern_dict["confidence"]),
        event_ts=generated_at,
        confirmation_ts=generated_at if status == "confirmed" else None,
        invalidation_ts=None,
        summary=pattern_dict["reasons"][0] if pattern_dict["reasons"] else "",
        reasoning_json=pattern_dict["reasons"],
        key_levels_json=pattern_dict["levels"],
        payload_json={"pattern": pattern_type},
        is_active=True,
    )


def _pt(p: Pivot, label: str | None = None, price: float | None = None) -> dict:
    return {"ts": p.ts.isoformat(), "price": p.price if price is None else price, "label": label or p.kind, "pivot_index": p.index}


def _line_points(left: Pivot, right: Pivot, price: float, label: str) -> list[dict]:
    return [_pt(left, label, price), _pt(right, label, price)]


def _adaptive_tolerance(candles: list) -> float:
    recent = candles[-60:]
    closes = [to_float(c.close) for c in recent if to_float(c.close) > 0]
    if len(closes) < 5:
        return 0.018
    near_range = (
        (max(closes[-20:]) - min(closes[-20:])) / max(sum(closes[-20:]) / 20, 1.0)
        if len(closes) >= 20
        else 0.0
    )
    ranges = [(to_float(c.high) - to_float(c.low)) / max(to_float(c.close), 1.0) for c in recent]
    avg_range = sum(ranges) / max(len(ranges), 1)
    window_range = (max(closes) - min(closes)) / max(sum(closes) / len(closes), 1.0)
    base = max(0.012, avg_range * 0.8, window_range * 0.12)
    relaxed = clamp(base * 1.20 if near_range > 0.04 else base, 0.012, 0.040)
    return relaxed


def _local_tolerance(price_a: float, price_b: float, neckline: float) -> float:
    avg_price = max((abs(price_a) + abs(price_b) + abs(neckline)) / 3.0, 1.0)
    pattern_height = abs(((price_a + price_b) / 2.0) - neckline) / avg_price
    return clamp(max(0.006, min(0.035, pattern_height * 0.35)), 0.006, 0.035)


def _pattern_quality(delta: float, tolerance: float, confirmed: bool) -> float:
    tolerance = max(tolerance, 0.0001)
    base = 0.82 - (delta / tolerance) * 0.28
    if confirmed:
        base += 0.08
    return clamp(base, 0.35, 0.95)


def _recent_pairs(pivots: list[Pivot]) -> list[tuple[Pivot, Pivot]]:
    pairs = []
    window = max(7, len(pivots) // 3)
    recent = pivots[-window:]
    for i in range(len(recent) - 1):
        for j in range(i + 1, len(recent)):
            if 3 <= recent[j].index - recent[i].index <= 120:
                pairs.append((recent[i], recent[j]))
    return list(reversed(pairs))
