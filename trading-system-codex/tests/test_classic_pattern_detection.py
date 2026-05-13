from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone
from statistics import mean

from app.services.structure.classic import detect_classic_patterns, linear_fit
from app.services.structure.common import Pivot, to_float

UTC = timezone.utc


class FakeCandle:
    def __init__(self, idx, o, h, l, c):
        self.ts_open = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=idx)
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = 1000


def make_candles(pivot_points: list[tuple[int, float]], length=96):
    pivot_points = sorted(pivot_points)
    if pivot_points[0][0] != 0:
        pivot_points = [(0, pivot_points[0][1])] + pivot_points
    if pivot_points[-1][0] != length - 1:
        pivot_points = pivot_points + [(length - 1, pivot_points[-1][1])]
    prices = [0.0] * length
    for (i0, p0), (i1, p1) in zip(pivot_points, pivot_points[1:]):
        span = max(i1 - i0, 1)
        for i in range(i0, i1 + 1):
            t = (i - i0) / span
            prices[i] = p0 + (p1 - p0) * t
    candles = []
    for i, close in enumerate(prices):
        w = 0.2 + 0.03 * math.sin(i)
        candles.append(FakeCandle(i, prices[i - 1] if i else close, close + w, close - w, close))
    return candles


def make_pivots(candles, positions: list[tuple[int, float, str]]):
    return [Pivot(ts=candles[i].ts_open, price=p, kind=k, index=i) for i, p, k in positions]


def test_ascending_triangle_detected():
    candles = make_candles([(0, 95), (8, 99), (16, 99.5), (24, 100), (32, 110), (40, 100), (48, 109.8), (56, 101), (64, 110.1), (72, 102), (80, 109.9), (88, 103), (95, 109)])
    pivots = make_pivots(candles, [(8, 99, "low"), (16, 99.5, "low"), (24, 100, "low"), (32, 110, "high"), (40, 100, "low"), (48, 109.8, "high"), (56, 101, "low"), (64, 110.1, "high"), (72, 102, "low"), (80, 109.9, "high"), (88, 103, "low")])
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "ascending_triangle" in found, f"Expected ascending_triangle, got {found}"
    for c in candidates:
        if c["pattern_type"] == "ascending_triangle":
            geo = c["geometry"]
            roles = {g.get("meta_json", {}).get("role") for g in geo}
            assert "upper_boundary" in roles
            assert "lower_boundary" in roles


def test_descending_triangle_detected():
    candles = make_candles([(0, 115), (8, 114), (16, 99), (24, 112), (32, 100), (40, 110), (48, 99.8), (56, 108), (64, 100.2), (72, 106), (80, 99.9), (88, 104), (95, 101)])
    pivots = make_pivots(candles, [(0, 115, "high"), (8, 114, "high"), (16, 99, "low"), (24, 112, "high"), (32, 100, "low"), (40, 110, "high"), (48, 99.8, "low"), (56, 108, "high"), (64, 100.2, "low"), (72, 106, "high"), (80, 99.9, "low"), (88, 104, "high")])
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "descending_triangle" in found, f"Expected descending_triangle, got {found}"


def test_rectangle_range_detected():
    candles = make_candles([(0, 100), (8, 101), (16, 109.8), (24, 100.5), (32, 110), (40, 100.8), (48, 109.7), (56, 100.3), (64, 110.1), (72, 100.1), (80, 109.9), (88, 100.4), (95, 105)])
    pivots = make_pivots(candles, [(0, 100, "low"), (8, 101, "low"), (16, 109.8, "high"), (24, 100.5, "low"), (32, 110, "high"), (40, 100.8, "low"), (48, 109.7, "high"), (56, 100.3, "low"), (64, 110.1, "high"), (72, 100.1, "low"), (80, 109.9, "high"), (88, 100.4, "low")])
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "rectangle_range" in found, f"Expected rectangle_range, got {found}"


def test_double_top_still_detected():
    candles = make_candles([(0, 130), (8, 92), (16, 104), (24, 95), (32, 106), (40, 92), (48, 92), (56, 90), (64, 88), (72, 128), (80, 84), (88, 82), (95, 80)])
    pivots = make_pivots(candles, [(0, 130, "high"), (8, 92, "low"), (16, 104, "high"), (24, 95, "low"), (32, 106, "high"), (40, 92, "low"), (48, 92, "low"), (56, 90, "low"), (64, 88, "low"), (72, 128, "high"), (80, 84, "low"), (88, 82, "low")])
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "double_top" in found, f"Expected double_top, got {found}"
    for c in candidates:
        if c["pattern_type"] == "double_top":
            geo = c["geometry"]
            roles = {g.get("meta_json", {}).get("role") for g in geo}
            assert "neckline" in roles


def test_no_pattern_path_in_geometry():
    candles = make_candles([(0, 95), (8, 99), (16, 99.5), (24, 100), (32, 110), (40, 100), (48, 109.8), (56, 101), (64, 110.1), (72, 102), (80, 109.9), (88, 103), (95, 109)])
    pivots = make_pivots(candles, [(8, 99, "low"), (16, 99.5, "low"), (24, 100, "low"), (32, 110, "high"), (40, 100, "low"), (48, 109.8, "high"), (56, 101, "low"), (64, 110.1, "high"), (72, 102, "low"), (80, 109.9, "high"), (88, 103, "low")])
    candidates = detect_classic_patterns(candles, pivots)
    for c in candidates:
        for g in c.get("geometry", []):
            role = g.get("meta_json", {}).get("role", "")
            kind = g.get("kind", "")
            assert "pattern_path" not in role, f"Found pattern_path role in {c['pattern_type']}"
            assert kind != "pattern_path", f"Found pattern_path kind in {c['pattern_type']}"
