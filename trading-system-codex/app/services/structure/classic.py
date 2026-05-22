# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .common import (
    DetectionBundle,
    Pivot,
    ScoreBundle,
    StructureActiveItem,
    StructureGeometry,
    build_structure_id,
    clamp,
    to_decimal,
    to_float,
)

UTC = timezone.utc
CLASSIC_PATTERN_CONTRACT_VERSION = "classic-pattern-region-v1"
MAX_CLASSIC_PROJECTION_BARS = 6
MAX_SECONDARY_CLASSIC_PATTERNS = 3
MIN_TOTAL_TOUCHES = 4
PRIMARY_FILL_ALPHA = 0.12
CANDIDATE_FILL_ALPHA = 0.05
INVALIDATED_FILL_ALPHA = 0.03
PRIMARY_BOUNDARY_ALPHA = 0.85
CANDIDATE_BOUNDARY_ALPHA = 0.35
INVALIDATED_BOUNDARY_ALPHA = 0.18
MIN_SPAN_BARS = 20
MAX_SPAN_RATIO_OF_WINDOW = 0.72
MAX_VERTICAL_RANGE_PCT = 0.35
RECENT_TOUCH_MAX_AGE_BARS = 20
BREAKOUT_MAX_AGE_BARS = 10
MIN_RENDER_SCORE = 0.48


class ClassicScorer:
    def detect(
        self, instrument_id: str, timeframe: str, candles: list, pivots: list[Pivot]
    ) -> DetectionBundle:
        candidates = detect_classic_patterns(candles, pivots, max_candidates=4)
        if not candidates:
            return DetectionBundle(
                score=ScoreBundle(
                    system="classic",
                    direction="neutral",
                    direction_score=0.0,
                    confidence=0.30,
                    quality=0.45,
                    freshness=0.70,
                    evidence_count=0,
                    top_reasons=["经典图形模块暂未识别到高质量确认形态。"],
                    conflict_flags=[],
                    metadata={
                        "regime_hint": "transition",
                        "candidate_weight": 0.0,
                        "candidate_count": 0,
                    },
                )
            )

        best = candidates[0]
        classic_patterns_payload = build_classic_patterns_payload(
            instrument_id, timeframe, candles, candidates
        )
        score = ScoreBundle(
            system="classic",
            direction=best["bias"],
            direction_score=best["direction_score"],
            confidence=best["confidence"],
            quality=best["quality"],
            freshness=0.88,
            evidence_count=len(best.get("points", [])),
            top_reasons=best.get("reasons", []),
            conflict_flags=["candidate_only"] if best["status"] != "confirmed" else [],
            metadata={
                "regime_hint": "transition",
                "candidate_count": len(candidates),
                "candidate_types": [c["pattern_type"] for c in candidates],
                "classic_patterns": classic_patterns_payload,
            },
        )

        all_geo: list[StructureGeometry] = []
        for c in candidates:
            for g in c.get("geometry", []):
                all_geo.append(_make_structure_geometry(instrument_id, timeframe, g, c))

        items = [_make_active_item(instrument_id, timeframe, c) for c in candidates[:3]]

        return DetectionBundle(
            score=score, active_items=items, geometry=all_geo, events=[], alerts=[]
        )


def linear_fit(points: list[Pivot]) -> tuple[float, float, float]:
    n = len(points)
    if n < 2:
        return 0.0, 0.0, 0.0
    xs = [float(p.index) for p in points]
    ys = [p.price for p in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den != 0 else 0.0
    intercept = mean_y - slope * mean_x
    errors = [
        abs(y - (slope * x + intercept)) / max(abs(y), 0.0001) for x, y in zip(xs, ys, strict=True)
    ]
    mean_error = sum(errors) / n
    return slope, intercept, mean_error


def detect_classic_patterns(
    candles: list, pivots: list[Pivot], *, max_candidates: int = 4
) -> list[dict]:
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
        lambda: detect_channels(candles, highs, lows),
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
    result = all_candidates[:max_candidates]
    if result:
        result[0]["display_role"] = "primary"
        _apply_display_role(result[0], "primary")
        for c in result[1:]:
            c["display_role"] = "candidate"
            _apply_display_role(c, "candidate")
    return result


def _make_region_geometry(
    pattern_type,
    status,
    x1,
    y1,
    x2,
    y2,
    x3,
    y3,
    x4,
    y4,
    left_pivot,
    right_pivot,
    candles,
    confidence,
):
    base_ts = candles[0].ts_open if candles else datetime.now(timezone.utc)
    interval = _infer_candle_delta(candles)

    def ts_for(idx):
        if 0 <= idx < len(candles):
            return candles[idx].ts_open.isoformat()
        return (base_ts + interval * idx).isoformat()

    fill_map = {
        "rectangle_range": "patternNeutral",
        "rectangle_breakout": "patternBullish",
        "rectangle_breakdown": "patternBearish",
        "ascending_triangle": "patternBullish",
        "descending_triangle": "patternBearish",
        "symmetrical_triangle": "patternMixed",
        "rising_wedge": "patternBearish",
        "falling_wedge": "patternBullish",
    }
    fill_token = fill_map.get(pattern_type, "patternNeutral")
    points_json = [
        {"index": x1, "time": ts_for(x1), "price": round(y1, 2)},
        {"index": x2, "time": ts_for(x2), "price": round(y2, 2)},
        {"index": x3, "time": ts_for(x3), "price": round(y3, 2)},
        {"index": x4, "time": ts_for(x4), "price": round(y4, 2)},
    ]
    return {
        "system": "classic",
        "kind": "region",
        "status": status,
        "points": points_json,
        "labels": [pattern_type],
        "meta_json": {
            "pattern_type": pattern_type,
            "role": "pattern_region",
            "layer": "classic_region",
            "priority": 35,
            "confidence": round(confidence, 4),
            "visible_by_default": True,
            "fill_token": fill_token,
            "fill_alpha": 0.12,
            "boundary_alpha": 0.85,
            "style_hint": "classic_region_fill",
            "overlap_policy": "keep",
            "dedupe_group": f"classic:{pattern_type}:region",
        },
    }


def _infer_candle_delta(candles: list) -> timedelta:
    if len(candles) >= 2:
        latest = getattr(candles[-1], "ts_open", None)
        previous = getattr(candles[-2], "ts_open", None)
        if isinstance(latest, datetime) and isinstance(previous, datetime):
            delta = latest - previous
            if delta.total_seconds() > 0:
                return delta
    return timedelta(hours=1)


def _touch_counts(points: list[Pivot]) -> tuple[int, int]:
    upper = sum(1 for point in points if getattr(point, "kind", "") == "high")
    lower = sum(1 for point in points if getattr(point, "kind", "") == "low")
    return upper, lower


def _touch_score(points: list[Pivot]) -> float:
    upper, lower = _touch_counts(points)
    if upper < 2 or lower < 2:
        return 0.0
    return round(min((upper + lower) / 6.0, 1.0), 4)


def _normalized_slope(slope: float, avg_price: float) -> float:
    return slope / max(abs(avg_price), 1.0)


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

    score_breakdown = {
        "touch_score": _touch_score(list(hs) + list(ls)),
        "fit_score": round(1.0 - (high_range + low_range) / max(tol * 2, 0.0001), 4),
        "duration_score": round(
            min((hs[-1].index - hs[0].index) / max(len(candles) * 0.5, 1), 1.0), 4
        ),
        "breakout_score": 1.0 if status == "confirmed" else 0.4,
        "volume_score": 0.5,
        "mtf_score": 0.5,
        "freshness_score": 0.8,
    }

    geometry = [
        {
            "kind": "resistance_line",
            "points": _line_points(hs[0], hs[-1], resistance, "矩形上沿"),
            "labels": ["矩形上沿"],
            "meta_json": {
                "role": "resistance",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        {
            "kind": "support_line",
            "points": _line_points(ls[0], ls[-1], support, "矩形下沿"),
            "labels": ["矩形下沿"],
            "meta_json": {
                "role": "support",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        {
            "kind": "zone",
            "points": [_pt(hs[0], "zone_top", resistance), _pt(ls[0], "zone_bottom", support)],
            "labels": ["矩形区域"],
            "meta_json": {
                "role": "rectangle_zone",
                "layer": "secondary",
                "priority": 5,
                "confidence": confidence_val,
                "visible_by_default": False,
                "style_hint": "dashed",
            },
        },
    ]

    region_geom = _make_region_geometry(
        pattern_type,
        status,
        hs[0].index,
        resistance,
        hs[-1].index,
        resistance,
        hs[-1].index,
        support,
        hs[0].index,
        support,
        hs[0],
        hs[-1],
        candles,
        confidence_val,
    )
    geometry.append(region_geom)

    results.append(
        {
            "pattern_type": pattern_type,
            "display_name": display_name,
            "status": status,
            "bias": bias,
            "direction_score": direction_score,
            "confidence": confidence_val,
            "quality": quality_val,
            "points": list(hs) + list(ls),
            "levels": {"resistance": resistance, "support": support},
            "reasons": reasons,
            "geometry": geometry,
            "bar_age": max(p.index for p in hs + ls),
            "score_breakdown": score_breakdown,
        }
    )
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

    score_breakdown = {
        "touch_score": _touch_score(list(hs) + list(ls)),
        "fit_score": round(1.0 - max_err / max(tol * 2, 0.0001), 4),
        "duration_score": round(min((right_idx - left_idx) / max(len(candles) * 0.5, 1), 1.0), 4),
        "breakout_score": 1.0 if status == "confirmed" else 0.4,
        "volume_score": 0.5,
        "mtf_score": 0.5,
        "freshness_score": 0.8,
    }

    upper_line_points = [
        _pt(hs[0], "三角形上边界", upper_left_price),
        _pt(hs[-1], "三角形上边界", upper_right_price),
    ]
    lower_line_points = [
        _pt(ls[0], "三角形下边界", lower_left_price),
        _pt(ls[-1], "三角形下边界", lower_right_price),
    ]

    geometry = [
        {
            "kind": "upper_boundary",
            "points": upper_line_points,
            "labels": ["上边界"],
            "meta_json": {
                "role": "upper_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        {
            "kind": "lower_boundary",
            "points": lower_line_points,
            "labels": ["下边界"],
            "meta_json": {
                "role": "lower_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
    ]

    region_geom = _make_region_geometry(
        pattern_type,
        status,
        left_idx,
        upper_left_price,
        right_idx,
        upper_right_price,
        right_idx,
        lower_right_price,
        left_idx,
        lower_left_price,
        hs[0],
        hs[-1],
        candles,
        confidence_val,
    )
    geometry.append(region_geom)

    results.append(
        {
            "pattern_type": pattern_type,
            "display_name": display_name,
            "status": status,
            "bias": bias,
            "direction_score": direction_score,
            "confidence": confidence_val,
            "quality": quality_val,
            "points": all_points,
            "levels": {
                "resistance_slope": upper_slope,
                "support_slope": lower_slope,
                "resistance_line": resistance_line_price,
                "support_line": support_line_price,
            },
            "reasons": reasons,
            "geometry": geometry,
            "bar_age": bar_age,
            "score_breakdown": score_breakdown,
        }
    )
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

    score_breakdown = {
        "touch_score": _touch_score(list(hs) + list(ls)),
        "fit_score": round(1.0 - max_err / max(tol * 2, 0.0001), 4),
        "duration_score": round(min((right_idx - left_idx) / max(len(candles) * 0.5, 1), 1.0), 4),
        "breakout_score": 1.0 if status == "confirmed" else 0.4,
        "volume_score": 0.5,
        "mtf_score": 0.5,
        "freshness_score": 0.8,
    }

    upper_line_points = [
        _pt(hs[0], "楔形上边界", upper_left_price),
        _pt(hs[-1], "楔形上边界", upper_right_price),
    ]
    lower_line_points = [
        _pt(ls[0], "楔形下边界", lower_left_price),
        _pt(ls[-1], "楔形下边界", lower_right_price),
    ]

    geometry = [
        {
            "kind": "upper_boundary",
            "points": upper_line_points,
            "labels": ["上边界"],
            "meta_json": {
                "role": "upper_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        {
            "kind": "lower_boundary",
            "points": lower_line_points,
            "labels": ["下边界"],
            "meta_json": {
                "role": "lower_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
    ]

    region_geom = _make_region_geometry(
        pattern_type,
        status,
        left_idx,
        upper_left_price,
        right_idx,
        upper_right_price,
        right_idx,
        lower_right_price,
        left_idx,
        lower_left_price,
        hs[0],
        hs[-1],
        candles,
        confidence_val,
    )
    geometry.append(region_geom)

    results.append(
        {
            "pattern_type": pattern_type,
            "display_name": display_name,
            "status": status,
            "bias": bias,
            "direction_score": direction_score,
            "confidence": confidence_val,
            "quality": quality_val,
            "points": all_points,
            "levels": {
                "resistance_slope": upper_slope,
                "support_slope": lower_slope,
                "resistance_line": resistance_line_price,
                "support_line": support_line_price,
            },
            "reasons": reasons,
            "geometry": geometry,
            "bar_age": bar_age,
            "score_breakdown": score_breakdown,
        }
    )
    return results


def detect_channels(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    if len(highs) < 4 or len(lows) < 4:
        return results

    hs = highs[-4:]
    ls = lows[-4:]
    upper_slope, upper_intercept, upper_err = linear_fit(hs)
    lower_slope, lower_intercept, lower_err = linear_fit(ls)
    tol = _adaptive_tolerance(candles)
    max_err = max(upper_err, lower_err)
    if max_err > tol * 2.0:
        return results

    avg_price = max(sum(p.price for p in hs + ls) / len(hs + ls), 1.0)
    slope_gap = abs(upper_slope - lower_slope) / avg_price
    if slope_gap > tol * 0.45:
        return results

    left_idx = min(hs[0].index, ls[0].index)
    right_idx = max(hs[-1].index, ls[-1].index)
    if right_idx - left_idx < 12:
        return results

    upper_left_price = upper_intercept + upper_slope * left_idx
    upper_right_price = upper_intercept + upper_slope * right_idx
    lower_left_price = lower_intercept + lower_slope * left_idx
    lower_right_price = lower_intercept + lower_slope * right_idx
    channel_width = abs(
        ((upper_left_price + upper_right_price) - (lower_left_price + lower_right_price)) / 2.0
    )
    if channel_width / avg_price < 0.008:
        return results

    if upper_slope > tol * avg_price * 0.2:
        bias = "bullish"
        direction_score = 0.26
        display_name = "上升通道"
        reasons = ["高低点沿近似平行的上行边界运行，当前以趋势通道候选观察。"]
    elif upper_slope < -tol * avg_price * 0.2:
        bias = "bearish"
        direction_score = -0.26
        display_name = "下降通道"
        reasons = ["高低点沿近似平行的下行边界运行，当前以趋势通道候选观察。"]
    else:
        bias = "neutral"
        direction_score = 0.0
        display_name = "横向通道"
        reasons = ["上下边界近似平行，价格仍在通道内部运行，等待边界突破或回落确认。"]

    confidence_val = clamp(0.48 + (1.0 - max_err / max(tol * 2.0, 0.0001)) * 0.18, 0.40, 0.72)
    score_breakdown = {
        "touch_score": _touch_score(list(hs) + list(ls)),
        "fit_score": round(1.0 - max_err / max(tol * 2, 0.0001), 4),
        "duration_score": round(min((right_idx - left_idx) / max(len(candles) * 0.5, 1), 1.0), 4),
        "breakout_score": 0.35,
        "volume_score": 0.5,
        "mtf_score": 0.5,
        "freshness_score": 0.8,
    }
    upper_line_points = [
        _point_at_index(candles, left_idx, upper_left_price, "通道上沿"),
        _point_at_index(candles, right_idx, upper_right_price, "通道上沿"),
    ]
    lower_line_points = [
        _point_at_index(candles, left_idx, lower_left_price, "通道下沿"),
        _point_at_index(candles, right_idx, lower_right_price, "通道下沿"),
    ]
    geometry = [
        {
            "kind": "upper_boundary",
            "points": upper_line_points,
            "labels": ["通道上沿"],
            "meta_json": {
                "role": "upper_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        {
            "kind": "lower_boundary",
            "points": lower_line_points,
            "labels": ["通道下沿"],
            "meta_json": {
                "role": "lower_boundary",
                "layer": "primary",
                "priority": 10,
                "confidence": confidence_val,
                "visible_by_default": True,
                "style_hint": "solid",
            },
        },
        _make_region_geometry(
            "channel",
            "candidate",
            left_idx,
            upper_left_price,
            right_idx,
            upper_right_price,
            right_idx,
            lower_right_price,
            left_idx,
            lower_left_price,
            hs[0],
            hs[-1],
            candles,
            confidence_val,
        ),
    ]
    results.append(
        {
            "pattern_type": "channel",
            "display_name": display_name,
            "status": "candidate",
            "bias": bias,
            "direction_score": direction_score,
            "confidence": confidence_val,
            "quality": 0.64,
            "points": list(hs) + list(ls),
            "levels": {
                "upper_slope": upper_slope,
                "lower_slope": lower_slope,
                "resistance_line": upper_right_price,
                "support_line": lower_right_price,
            },
            "reasons": reasons,
            "geometry": geometry,
            "bar_age": right_idx,
            "score_breakdown": score_breakdown,
        }
    )
    return results


def detect_double_top_bottom(candles: list, highs: list[Pivot], lows: list[Pivot]) -> list[dict]:
    results: list[dict] = []
    last_close = to_float(candles[-1].close)

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

        score_breakdown = {
            "touch_score": 0.67,
            "fit_score": round(1.0 - delta / max(tolerance, 0.0001), 4),
            "duration_score": round(
                min((right.index - left.index) / max(len(candles) * 0.5, 1), 1.0), 4
            ),
            "breakout_score": 1.0 if confirmed else 0.4,
            "volume_score": 0.5,
            "mtf_score": 0.5,
            "freshness_score": 0.8,
        }

        neckline_points = _line_points(left, right, neckline, "颈线")

        geometry = [
            {
                "kind": "neckline",
                "points": neckline_points,
                "labels": ["双顶颈线"],
                "meta_json": {
                    "role": "neckline",
                    "layer": "primary",
                    "priority": 10,
                    "confidence": conf,
                    "visible_by_default": True,
                    "style_hint": "solid",
                },
            }
        ]
        results.append(
            {
                "pattern_type": "double_top",
                "display_name": "双顶",
                "status": "confirmed" if confirmed else "candidate",
                "bias": "bearish",
                "direction_score": direction_score,
                "confidence": conf,
                "quality": qual,
                "points": [left, neckline_pivot, right],
                "levels": {
                    "neckline": neckline,
                    "left_peak": left.price,
                    "right_peak": right.price,
                    "peak_delta_pct": delta,
                    "tolerance_pct": tolerance,
                },
                "reasons": [
                    "双顶形态路径已识别，两个高点接近且中间存在颈线低点。",
                    "收盘已跌破颈线，双顶形态得到确认。"
                    if confirmed
                    else "尚未跌破颈线，当前作为双顶候选观察。",
                ],
                "geometry": geometry,
                "bar_age": max(left.index, right.index),
                "score_breakdown": score_breakdown,
            }
        )
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

        score_breakdown = {
            "touch_score": 0.67,
            "fit_score": round(1.0 - delta / max(tolerance, 0.0001), 4),
            "duration_score": round(
                min((right.index - left.index) / max(len(candles) * 0.5, 1), 1.0), 4
            ),
            "breakout_score": 1.0 if confirmed else 0.4,
            "volume_score": 0.5,
            "mtf_score": 0.5,
            "freshness_score": 0.8,
        }

        neckline_points = _line_points(left, right, neckline, "颈线")

        geometry = [
            {
                "kind": "neckline",
                "points": neckline_points,
                "labels": ["双底颈线"],
                "meta_json": {
                    "role": "neckline",
                    "layer": "primary",
                    "priority": 10,
                    "confidence": conf,
                    "visible_by_default": True,
                    "style_hint": "solid",
                },
            }
        ]
        results.append(
            {
                "pattern_type": "double_bottom",
                "display_name": "双底",
                "status": "confirmed" if confirmed else "candidate",
                "bias": "bullish",
                "direction_score": direction_score,
                "confidence": conf,
                "quality": qual,
                "points": [left, neckline_pivot, right],
                "levels": {
                    "neckline": neckline,
                    "left_trough": left.price,
                    "right_trough": right.price,
                    "peak_delta_pct": delta,
                    "tolerance_pct": tolerance,
                },
                "reasons": [
                    "双底形态路径已识别，两个低点接近且中间存在颈线高点。",
                    "收盘已突破颈线，双底形态得到确认。"
                    if confirmed
                    else "尚未突破颈线，当前作为双底候选观察。",
                ],
                "geometry": geometry,
                "bar_age": max(left.index, right.index),
                "score_breakdown": score_breakdown,
            }
        )
        break

    return results


def build_classic_patterns_payload(
    instrument_id: str,
    timeframe: str,
    candles: list,
    candidates: list[dict],
) -> dict[str, Any]:
    region_candidates = [
        candidate for candidate in candidates if _region_geometry(candidate) is not None
    ]
    gated_candidates = [
        (candidate, _classic_quality_gate(candles, candidate)) for candidate in region_candidates
    ]
    renderable_candidates = [item for item in gated_candidates if item[1]["renderable"]]
    hidden_candidates = [item for item in gated_candidates if not item[1]["renderable"]]
    selected = (
        renderable_candidates[: 1 + MAX_SECONDARY_CLASSIC_PATTERNS]
        + hidden_candidates[
            : max(0, 1 + MAX_SECONDARY_CLASSIC_PATTERNS - len(renderable_candidates))
        ]
    )
    candidate_payloads = [
        _classic_candidate_payload(
            instrument_id,
            timeframe,
            candles,
            candidate,
            index,
            "primary" if index == 0 and gate["renderable"] else "candidate",
            gate,
        )
        for index, (candidate, gate) in enumerate(selected)
    ]
    primary = next(
        (
            item
            for item in candidate_payloads
            if item["display_role"] == "primary" and item["renderable"]
        ),
        None,
    )
    secondary = [
        item for item in candidate_payloads if primary is None or item["id"] != primary["id"]
    ][:MAX_SECONDARY_CLASSIC_PATTERNS]
    return {
        "version": CLASSIC_PATTERN_CONTRACT_VERSION,
        "primary": primary,
        "candidates": secondary,
        "source": {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "candidate_count": len(region_candidates),
            "max_projection_bars": MAX_CLASSIC_PROJECTION_BARS,
        },
    }


def _classic_quality_gate(candles: list, candidate: dict) -> dict[str, Any]:
    reasons: list[str] = []
    region = _region_geometry(candidate) or {}
    region_points = region.get("points") or []
    polygon_prices = [
        float(point.get("price")) for point in region_points if point.get("price") is not None
    ]
    candle_prices = [
        value
        for candle in candles
        for value in (_candle_value(candle, "high"), _candle_value(candle, "low"))
        if value is not None and value > 0
    ]
    latest_close = _candle_value(candles[-1], "close") if candles else None
    confidence = float(candidate.get("confidence") or 0.0)
    quality = float(candidate.get("quality") or 0.0)
    score = candidate.get("score_breakdown") or {}
    touch_score = float(score.get("touch_score") or 0.0)
    fit_score = float(score.get("fit_score") or 0.0)
    point_indices = _candidate_indices(candidate)
    unique_indices = sorted(set(point_indices))
    pattern_type = _contract_pattern_type(candidate.get("pattern_type"))
    status = _contract_status(candidate)

    if len(region_points) < 4:
        reasons.append("形态区域点不足")
    if len(unique_indices) < MIN_TOTAL_TOUCHES:
        reasons.append("触碰证据不足")
    if touch_score < 0.45 and pattern_type not in {"double_top", "double_bottom"}:
        reasons.append("上下边界触点不足")
    if confidence < 0.35:
        reasons.append("置信度过低")
    if quality < 0.25:
        reasons.append("形态质量过低")
    if fit_score and fit_score < 0.20:
        reasons.append("边界拟合质量不足")

    if unique_indices:
        span_bars = max(unique_indices) - min(unique_indices) + 1
        if span_bars < MIN_SPAN_BARS:
            reasons.append("形态跨度过短")
        if candles and span_bars / max(len(candles), 1) > MAX_SPAN_RATIO_OF_WINDOW:
            reasons.append("形态覆盖窗口过大")
        latest_index = len(candles) - 1
        recent_touch_age = latest_index - max(unique_indices)
        if recent_touch_age > RECENT_TOUCH_MAX_AGE_BARS:
            reasons.append("最近触碰距离当前过远")
        if (
            status in {"breakout_confirmed", "breakdown_confirmed"}
            and recent_touch_age > BREAKOUT_MAX_AGE_BARS
        ):
            reasons.append("突破确认已经过旧")

    if polygon_prices and candle_prices:
        pattern_span = max(polygon_prices) - min(polygon_prices)
        candle_span = max(candle_prices) - min(candle_prices)
        avg_price = sum(candle_prices) / max(len(candle_prices), 1)
        if avg_price > 0 and pattern_span / avg_price > MAX_VERTICAL_RANGE_PCT:
            reasons.append("形态垂直高度过大")
        if candle_span > 0 and pattern_span / candle_span > 1.35:
            reasons.append("形态区域过宽")
        if latest_close is not None:
            margin = max(pattern_span * 0.25, avg_price * 0.005)
            if (
                latest_close < min(polygon_prices) - margin
                or latest_close > max(polygon_prices) + margin
            ):
                reasons.append("最新价格已明显脱离形态区域")

    channel_check: dict[str, Any] | None = None
    if pattern_type == "channel":
        channel_check = _channel_containment_check(candles, candidate)
        if channel_check["latest_position"] in {"above", "below"}:
            reasons.append("最新价格已脱离通道边界")
        if channel_check["containment_ratio"] < 0.55:
            reasons.append("通道对历史走势覆盖不足")
        if channel_check["recent_containment_ratio"] < 0.45:
            reasons.append("最近价格不再沿通道运行")

    display_range = _display_range_for_candidate(candles, candidate)
    if (
        display_range["projection_end_index"] - display_range["end_index"]
        > MAX_CLASSIC_PROJECTION_BARS
    ):
        reasons.append("投影超出限制")

    composite_score = confidence * 0.45 + quality * 0.35 + touch_score * 0.20
    if composite_score < MIN_RENDER_SCORE:
        reasons.append("综合质量未达到渲染门槛")

    renderable = not reasons and status not in {"invalidated", "expired"}
    return {
        "renderable": renderable,
        "hidden_reason": "；".join(reasons) if reasons else None,
        "checks": {
            "confidence": round(confidence, 4),
            "quality": round(quality, 4),
            "touch_score": round(touch_score, 4),
            "fit_score": round(fit_score, 4),
            "composite_score": round(composite_score, 4),
            "touch_count": len(unique_indices),
            **({"channel": channel_check} if channel_check is not None else {}),
        },
    }


def _boundary_line(candidate: dict, role_name: str) -> tuple[float, float, int, int] | None:
    for geometry in candidate.get("geometry", []):
        meta = geometry.get("meta_json") or {}
        role = meta.get("role") or geometry.get("kind")
        if role != role_name:
            continue
        points = geometry.get("points", [])
        if len(points) < 2:
            return None
        left, right = points[0], points[-1]
        left_index = int(left.get("index", left.get("pivot_index", 0)))
        right_index = int(right.get("index", right.get("pivot_index", left_index)))
        if right_index == left_index:
            return None
        left_price = float(left.get("price") or left.get("value"))
        right_price = float(right.get("price") or right.get("value"))
        slope = (right_price - left_price) / (right_index - left_index)
        intercept = left_price - slope * left_index
        return slope, intercept, left_index, right_index
    return None


def _channel_containment_check(candles: list, candidate: dict) -> dict[str, Any]:
    upper = _boundary_line(candidate, "upper_boundary")
    lower = _boundary_line(candidate, "lower_boundary")
    if upper is None or lower is None or not candles:
        return {
            "containment_ratio": 0.0,
            "recent_containment_ratio": 0.0,
            "latest_position": "unknown",
        }

    upper_slope, upper_intercept, upper_left, _upper_right = upper
    lower_slope, lower_intercept, lower_left, _lower_right = lower
    start_index = max(0, min(upper_left, lower_left))
    latest_index = len(candles) - 1
    window = candles[start_index : latest_index + 1]
    if not window:
        return {
            "containment_ratio": 0.0,
            "recent_containment_ratio": 0.0,
            "latest_position": "unknown",
        }

    price_values = [
        value
        for candle in window
        for value in (_candle_value(candle, "high"), _candle_value(candle, "low"))
        if value is not None and value > 0
    ]
    span = max(price_values) - min(price_values) if price_values else 0.0
    margin = max(span * 0.035, max(price_values or [1.0]) * 0.0025)

    def position_at(index: int, close: float, margin_value: float) -> str:
        upper_price = upper_intercept + upper_slope * index
        lower_price = lower_intercept + lower_slope * index
        high = max(upper_price, lower_price)
        low = min(upper_price, lower_price)
        if close > high + margin_value:
            return "above"
        if close < low - margin_value:
            return "below"
        return "inside"

    positions: list[str] = []
    recent_positions: list[str] = []
    recent_start = max(start_index, latest_index - 19)
    for absolute_index, candle in enumerate(candles):
        if absolute_index < start_index:
            continue
        close = _candle_value(candle, "close")
        if close is None:
            continue
        pos = position_at(absolute_index, close, margin)
        positions.append(pos)
        if absolute_index >= recent_start:
            recent_positions.append(pos)

    latest_close = _candle_value(candles[-1], "close")
    latest_position = (
        position_at(latest_index, latest_close, margin) if latest_close is not None else "unknown"
    )
    inside_count = sum(1 for item in positions if item == "inside")
    recent_inside_count = sum(1 for item in recent_positions if item == "inside")
    return {
        "containment_ratio": round(inside_count / max(len(positions), 1), 4),
        "recent_containment_ratio": round(recent_inside_count / max(len(recent_positions), 1), 4),
        "latest_position": latest_position,
        "margin": round(margin, 4),
    }


def _classic_candidate_payload(
    instrument_id: str,
    timeframe: str,
    candles: list,
    candidate: dict,
    index: int,
    role: str,
    quality_gate: dict[str, Any],
) -> dict[str, Any]:
    region = _region_geometry(candidate) or {}
    status = _contract_status(candidate)
    pattern_type = _contract_pattern_type(candidate.get("pattern_type"))
    bias = _contract_bias(candidate.get("bias"))
    display_range = _display_range_for_candidate(candles, candidate)
    region_payload = _region_payload(candidate, region, status, role)
    lines = _line_payloads(candidate, candles, display_range)
    levels = _contract_levels(candidate)
    confidence = round(float(candidate.get("confidence") or 0.0), 4)
    return {
        "id": build_structure_id(
            "classic-pattern", timeframe, pattern_type, display_range["start_index"], index
        ),
        "symbol": instrument_id,
        "timeframe": timeframe,
        "pattern_type": pattern_type,
        "source_pattern_type": candidate.get("pattern_type"),
        "display_name": _contract_display_name(candidate),
        "status": status,
        "direction_bias": bias,
        "confidence": confidence,
        "display_role": role,
        "renderable": bool(quality_gate.get("renderable")),
        "hidden_reason": quality_gate.get("hidden_reason"),
        "quality_gate": quality_gate,
        "display_range": display_range,
        "region": region_payload,
        "lines": lines,
        "levels": levels,
        "score_breakdown": candidate.get("score_breakdown") or {},
        "explanation": _contract_explanation(candidate, status, bias, levels),
    }


def _apply_display_role(candidate: dict, role: str) -> None:
    status = _contract_status(candidate)
    fill_alpha, boundary_alpha = _alphas_for(role, status)
    for geometry in candidate.get("geometry", []):
        meta = geometry.setdefault("meta_json", {})
        meta["display_role"] = role
        meta["fill_alpha"] = (
            fill_alpha
            if meta.get("role") == "pattern_region"
            else meta.get("fill_alpha", fill_alpha)
        )
        meta["boundary_alpha"] = boundary_alpha
        meta["visible_by_default"] = role == "primary"


def _region_geometry(candidate: dict) -> dict | None:
    for geometry in candidate.get("geometry", []):
        meta = geometry.get("meta_json") or {}
        if geometry.get("kind") == "region" or meta.get("role") == "pattern_region":
            return geometry
    return None


def _contract_pattern_type(pattern_type: Any) -> str:
    value = str(pattern_type or "unknown")
    if value.startswith("rectangle_"):
        return "rectangle"
    return value


def _contract_status(candidate: dict) -> str:
    raw_status = str(candidate.get("status") or "candidate")
    bias = str(candidate.get("bias") or "neutral")
    if raw_status == "confirmed":
        return (
            "breakout_confirmed"
            if bias == "bullish"
            else "breakdown_confirmed"
            if bias == "bearish"
            else "near_breakout"
        )
    if raw_status in {"invalidated", "expired"}:
        return raw_status
    return "forming"


def _contract_bias(value: Any) -> str:
    text = str(value or "neutral")
    return text if text in {"bullish", "bearish", "neutral", "mixed"} else "neutral"


def _display_range_for_candidate(candles: list, candidate: dict) -> dict[str, Any]:
    point_indices = _candidate_indices(candidate)
    start_index = max(0, min(point_indices) if point_indices else 0)
    end_index = max(point_indices) if point_indices else max(len(candles) - 1, 0)
    projection_end_index = min(
        max(len(candles) - 1, end_index), end_index + MAX_CLASSIC_PROJECTION_BARS
    )
    return {
        "start_index": start_index,
        "end_index": end_index,
        "projection_end_index": projection_end_index,
        "start_time": _candle_time(candles, start_index),
        "end_time": _candle_time(candles, end_index),
        "projection_end_time": _candle_time(candles, projection_end_index),
        "extend_policy": "right_limited",
        "max_projection_bars": MAX_CLASSIC_PROJECTION_BARS,
    }


def _candidate_indices(candidate: dict) -> list[int]:
    indices: list[int] = []
    for pivot in candidate.get("points", []):
        index = getattr(pivot, "index", None)
        if isinstance(index, int):
            indices.append(index)
    for geometry in candidate.get("geometry", []):
        for point in geometry.get("points", []):
            index = point.get("index", point.get("pivot_index"))
            if isinstance(index, int):
                indices.append(index)
    return indices


def _region_payload(candidate: dict, region: dict, status: str, role: str) -> dict[str, Any]:
    fill_alpha, boundary_alpha = _alphas_for(role, status)
    meta = region.get("meta_json") or {}
    return {
        "polygon_points": [_contract_point(point) for point in region.get("points", [])],
        "fill_token": meta.get("fill_token") or _fill_token_for(candidate.get("bias")),
        "fill_alpha": fill_alpha,
        "boundary_alpha": boundary_alpha,
        "closure_score": round(float(candidate.get("quality") or 0.0), 4),
    }


def _line_payloads(
    candidate: dict, candles: list, display_range: dict[str, Any]
) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for geometry in candidate.get("geometry", []):
        meta = geometry.get("meta_json") or {}
        role = meta.get("role") or geometry.get("kind")
        if role == "pattern_region" or geometry.get("kind") == "region":
            continue
        points = [_contract_point(point) for point in geometry.get("points", [])]
        if len(points) < 2:
            continue
        projected_points = _project_line_points(points, candles, display_range)
        lines.append(
            {
                "role": _contract_line_role(role),
                "label": _line_label(role),
                "points": projected_points,
                "style": "solid" if candidate.get("display_role") == "primary" else "dashed",
                "extend_policy": "right_limited",
                "confidence": round(float(candidate.get("confidence") or 0.0), 4),
            }
        )
    return lines


def _project_line_points(
    points: list[dict[str, Any]], candles: list, display_range: dict[str, Any]
) -> list[dict[str, Any]]:
    if len(points) < 2:
        return points
    first, last = points[0], points[-1]
    target_index = display_range["projection_end_index"]
    if target_index <= int(last.get("index") or 0):
        return points
    first_index = int(first.get("index") or 0)
    last_index = int(last.get("index") or first_index)
    if last_index == first_index:
        return points
    slope = (float(last["price"]) - float(first["price"])) / (last_index - first_index)
    projected_price = float(last["price"]) + slope * (target_index - last_index)
    return [
        points[0],
        {
            "index": target_index,
            "time": _candle_time(candles, target_index),
            "price": round(projected_price, 2),
        },
    ]


def _contract_levels(candidate: dict) -> dict[str, Any]:
    levels = dict(candidate.get("levels") or {})
    if "resistance" in levels:
        levels.setdefault("breakout_confirm", levels["resistance"])
    if "support" in levels:
        levels.setdefault("breakdown_confirm", levels["support"])
    if "resistance_line" in levels:
        levels.setdefault("breakout_confirm", levels["resistance_line"])
    if "support_line" in levels:
        levels.setdefault("breakdown_confirm", levels["support_line"])
    if "neckline" in levels:
        if candidate.get("bias") == "bullish":
            levels.setdefault("breakout_confirm", levels["neckline"])
        else:
            levels.setdefault("breakdown_confirm", levels["neckline"])
    if "breakout_confirm" in levels and "breakdown_confirm" in levels:
        height = abs(float(levels["breakout_confirm"]) - float(levels["breakdown_confirm"]))
        if candidate.get("bias") == "bullish":
            levels.setdefault("invalidation", levels["breakdown_confirm"])
            levels.setdefault("stop_loss", levels["breakdown_confirm"])
            levels.setdefault("take_profit_1", float(levels["breakout_confirm"]) + height)
            levels.setdefault("take_profit_2", float(levels["breakout_confirm"]) + height * 1.618)
        elif candidate.get("bias") == "bearish":
            levels.setdefault("invalidation", levels["breakout_confirm"])
            levels.setdefault("stop_loss", levels["breakout_confirm"])
            levels.setdefault("take_profit_1", float(levels["breakdown_confirm"]) - height)
            levels.setdefault("take_profit_2", float(levels["breakdown_confirm"]) - height * 1.618)
    return {
        key: round(value, 4) if isinstance(value, float) else value for key, value in levels.items()
    }


def _contract_explanation(
    candidate: dict, status: str, bias: str, levels: dict[str, Any]
) -> dict[str, Any]:
    reasons = [str(item) for item in candidate.get("reasons", []) if item]
    status_text = {
        "forming": "\u5f62\u6001\u5f62\u6210\u4e2d",
        "near_breakout": "\u63a5\u8fd1\u7a81\u7834",
        "breakout_confirmed": "\u5411\u4e0a\u7a81\u7834\u5df2\u786e\u8ba4",
        "breakdown_confirmed": "\u5411\u4e0b\u8dcc\u7834\u5df2\u786e\u8ba4",
        "invalidated": "\u5f62\u6001\u5df2\u5931\u6548",
        "expired": "\u5f62\u6001\u5df2\u8fc7\u671f",
    }.get(status, "\u5f62\u6001\u89c2\u5bdf\u4e2d")
    bias_text = {
        "bullish": "\u504f\u591a",
        "bearish": "\u504f\u7a7a",
        "neutral": "\u4e2d\u6027",
        "mixed": "\u6df7\u5408",
    }.get(bias, "\u4e2d\u6027")
    summary = f"{_contract_display_name(candidate)}\uff1a{status_text}\uff0c\u65b9\u5411\u503e\u5411\u4e3a{bias_text}\u3002"
    key_levels = []
    for key, label in [
        ("breakout_confirm", "\u7a81\u7834\u786e\u8ba4\u4f4d"),
        ("breakdown_confirm", "\u8dcc\u7834\u786e\u8ba4\u4f4d"),
        ("invalidation", "\u5931\u6548\u4f4d"),
        ("stop_loss", "\u6b62\u635f\u4f4d"),
        ("take_profit_1", "\u7b2c\u4e00\u6b62\u76c8\u4f4d"),
        ("take_profit_2", "\u7b2c\u4e8c\u6b62\u76c8\u4f4d"),
    ]:
        if key in levels:
            key_levels.append({"key": key, "label": label, "value": levels[key]})
    return {
        "summary": summary,
        "status_text": status_text,
        "direction_text": bias_text,
        "evidence": reasons[:3],
        "key_levels": key_levels,
        "tooltip": _tooltip_text(candidate, status_text, bias_text, key_levels),
    }


def _tooltip_text(
    candidate: dict, status_text: str, bias_text: str, key_levels: list[dict[str, Any]]
) -> str:
    levels_text = "\uff1b".join(f"{item['label']} {item['value']}" for item in key_levels[:4])
    score = candidate.get("score_breakdown") or {}
    touch = score.get("touch_score", "-")
    fit = score.get("fit_score", "-")
    return (
        f"{_contract_display_name(candidate)}\uff5c{status_text}\uff5c{bias_text}\uff5c"
        f"\u7f6e\u4fe1\u5ea6 {round(float(candidate.get('confidence') or 0.0), 2)}\uff5c"
        f"\u89e6\u78b0 {touch}\uff5c\u62df\u5408 {fit}"
        + (f"\uff5c{levels_text}" if levels_text else "")
    )


def _contract_display_name(candidate: dict) -> str:
    pattern_type = _contract_pattern_type(candidate.get("pattern_type"))
    mapping = {
        "rectangle": "\u77e9\u5f62\u6574\u7406",
        "ascending_triangle": "\u4e0a\u5347\u4e09\u89d2\u5f62",
        "descending_triangle": "\u4e0b\u964d\u4e09\u89d2\u5f62",
        "symmetrical_triangle": "\u5bf9\u79f0\u4e09\u89d2\u5f62",
        "rising_wedge": "\u4e0a\u5347\u6954\u5f62",
        "falling_wedge": "\u4e0b\u964d\u6954\u5f62",
        "channel": "\u4ef7\u683c\u901a\u9053",
        "double_top": "\u53cc\u9876",
        "double_bottom": "\u53cc\u5e95",
    }
    return mapping.get(pattern_type, str(candidate.get("display_name") or pattern_type))


def _contract_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": int(point.get("index", point.get("pivot_index", 0)) or 0),
        "time": point.get("time")
        or point.get("ts")
        or point.get("timestamp")
        or point.get("ts_open"),
        "price": round(float(point.get("price") or point.get("value") or 0.0), 2),
    }


def _alphas_for(role: str, status: str) -> tuple[float, float]:
    if status in {"invalidated", "expired"}:
        return INVALIDATED_FILL_ALPHA, INVALIDATED_BOUNDARY_ALPHA
    if role == "primary":
        return PRIMARY_FILL_ALPHA, PRIMARY_BOUNDARY_ALPHA
    return CANDIDATE_FILL_ALPHA, CANDIDATE_BOUNDARY_ALPHA


def _fill_token_for(bias: Any) -> str:
    return {
        "bullish": "patternBullish",
        "bearish": "patternBearish",
        "neutral": "patternNeutral",
        "mixed": "patternMixed",
    }.get(str(bias or "neutral"), "patternNeutral")


def _contract_line_role(role: Any) -> str:
    mapping = {
        "resistance": "upper_boundary",
        "support": "lower_boundary",
        "upper_boundary": "upper_boundary",
        "lower_boundary": "lower_boundary",
        "neckline": "neckline",
    }
    return mapping.get(str(role), str(role or "boundary"))


def _line_label(role: Any) -> str:
    return {
        "resistance": "上边界",
        "support": "下边界",
        "upper_boundary": "上边界",
        "lower_boundary": "下边界",
        "neckline": "颈线",
    }.get(str(role), "边界")


def _candle_value(candle: Any, key: str) -> float | None:
    raw = candle.get(key) if isinstance(candle, dict) else getattr(candle, key, None)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _candle_time(candles: list, index: int) -> str | None:
    if not candles:
        return None
    safe_index = max(0, min(index, len(candles) - 1))
    candle = candles[safe_index]
    value = candle.get("ts_open") if isinstance(candle, dict) else getattr(candle, "ts_open", None)
    return (
        value.isoformat()
        if hasattr(value, "isoformat")
        else str(value)
        if value is not None
        else None
    )


def _point_at_index(candles: list, index: int, price: float, label: str) -> dict[str, Any]:
    return {
        "index": index,
        "pivot_index": index,
        "ts": _candle_time(candles, index),
        "time": _candle_time(candles, index),
        "price": price,
        "label": label,
    }


def _make_structure_geometry(
    instrument_id: str, timeframe: str, geo_dict: dict, pattern_dict: dict
) -> StructureGeometry:
    pattern_type = pattern_dict["pattern_type"]
    status = pattern_dict["status"]
    confidence_val = pattern_dict["confidence"]

    meta_json = dict(geo_dict.get("meta_json", {}))
    meta_json.update(
        {
            "pattern_type": pattern_type,
            "confidence": confidence_val,
        }
    )

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
    return {
        "ts": p.ts.isoformat(),
        "price": p.price if price is None else price,
        "label": label or p.kind,
        "pivot_index": p.index,
    }


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
