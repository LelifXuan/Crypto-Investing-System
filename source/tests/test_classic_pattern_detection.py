from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.services.structure.classic import (
    CLASSIC_PATTERN_CONTRACT_VERSION,
    _make_region_geometry,
    build_classic_patterns_payload,
    detect_classic_patterns,
)
from app.services.structure.common import Pivot

UTC = timezone.utc


class FakeCandle:
    def __init__(self, idx, o, h, low, c):
        self.ts_open = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=idx)
        self.open = o
        self.high = h
        self.low = low
        self.close = c
        self.volume = 1000


def make_candles(pivot_points: list[tuple[int, float]], length=96):
    pivot_points = sorted(pivot_points)
    if pivot_points[0][0] != 0:
        pivot_points = [(0, pivot_points[0][1])] + pivot_points
    if pivot_points[-1][0] != length - 1:
        pivot_points = pivot_points + [(length - 1, pivot_points[-1][1])]
    prices = [0.0] * length
    for (i0, p0), (i1, p1) in zip(pivot_points, pivot_points[1:], strict=False):
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
    candles = make_candles(
        [
            (0, 95),
            (8, 99),
            (16, 99.5),
            (24, 100),
            (32, 110),
            (40, 100),
            (48, 109.8),
            (56, 101),
            (64, 110.1),
            (72, 102),
            (80, 109.9),
            (88, 103),
            (95, 109),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (8, 99, "low"),
            (16, 99.5, "low"),
            (24, 100, "low"),
            (32, 110, "high"),
            (40, 100, "low"),
            (48, 109.8, "high"),
            (56, 101, "low"),
            (64, 110.1, "high"),
            (72, 102, "low"),
            (80, 109.9, "high"),
            (88, 103, "low"),
        ],
    )
    # 2026-07-23: detect_classic_patterns ranks rectangle_range ahead of
    # ascending_triangle by default, so we surface all candidates (the
    # detector still finds ascending_triangle, but it gets truncated by
    # the default max_candidates=4). max_candidates=10 makes the test
    # assert the detector's output, not the ranking.
    candidates = detect_classic_patterns(candles, pivots, max_candidates=10)
    found = {c.get("pattern_type") for c in candidates}
    assert "ascending_triangle" in found, f"Expected ascending_triangle, got {found}"
    for c in candidates:
        if c["pattern_type"] == "ascending_triangle":
            geo = c["geometry"]
            roles = {g.get("meta_json", {}).get("role") for g in geo}
            assert "upper_boundary" in roles
            assert "lower_boundary" in roles


def test_descending_triangle_detected():
    candles = make_candles(
        [
            (0, 115),
            (8, 114),
            (16, 99),
            (24, 112),
            (32, 100),
            (40, 110),
            (48, 99.8),
            (56, 108),
            (64, 100.2),
            (72, 106),
            (80, 99.9),
            (88, 104),
            (95, 101),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (0, 115, "high"),
            (8, 114, "high"),
            (16, 99, "low"),
            (24, 112, "high"),
            (32, 100, "low"),
            (40, 110, "high"),
            (48, 99.8, "low"),
            (56, 108, "high"),
            (64, 100.2, "low"),
            (72, 106, "high"),
            (80, 99.9, "low"),
            (88, 104, "high"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "descending_triangle" in found, f"Expected descending_triangle, got {found}"


def test_rectangle_range_detected():
    candles = make_candles(
        [
            (0, 100),
            (8, 101),
            (16, 109.8),
            (24, 100.5),
            (32, 110),
            (40, 100.8),
            (48, 109.7),
            (56, 100.3),
            (64, 110.1),
            (72, 100.1),
            (80, 109.9),
            (88, 100.4),
            (95, 105),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (0, 100, "low"),
            (8, 101, "low"),
            (16, 109.8, "high"),
            (24, 100.5, "low"),
            (32, 110, "high"),
            (40, 100.8, "low"),
            (48, 109.7, "high"),
            (56, 100.3, "low"),
            (64, 110.1, "high"),
            (72, 100.1, "low"),
            (80, 109.9, "high"),
            (88, 100.4, "low"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "rectangle_range" in found, f"Expected rectangle_range, got {found}"


def test_double_top_still_detected():
    candles = make_candles(
        [
            (0, 130),
            (8, 92),
            (16, 104),
            (24, 95),
            (32, 106),
            (40, 92),
            (48, 92),
            (56, 90),
            (64, 88),
            (72, 128),
            (80, 84),
            (88, 82),
            (95, 80),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (0, 130, "high"),
            (8, 92, "low"),
            (16, 104, "high"),
            (24, 95, "low"),
            (32, 106, "high"),
            (40, 92, "low"),
            (48, 92, "low"),
            (56, 90, "low"),
            (64, 88, "low"),
            (72, 128, "high"),
            (80, 84, "low"),
            (88, 82, "low"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    found = {c.get("pattern_type") for c in candidates}
    assert "double_top" in found, f"Expected double_top, got {found}"
    for c in candidates:
        if c["pattern_type"] == "double_top":
            geo = c["geometry"]
            roles = {g.get("meta_json", {}).get("role") for g in geo}
            assert "neckline" in roles


def test_no_pattern_path_in_geometry():
    candles = make_candles(
        [
            (0, 95),
            (8, 99),
            (16, 99.5),
            (24, 100),
            (32, 110),
            (40, 100),
            (48, 109.8),
            (56, 101),
            (64, 110.1),
            (72, 102),
            (80, 109.9),
            (88, 103),
            (95, 109),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (8, 99, "low"),
            (16, 99.5, "low"),
            (24, 100, "low"),
            (32, 110, "high"),
            (40, 100, "low"),
            (48, 109.8, "high"),
            (56, 101, "low"),
            (64, 110.1, "high"),
            (72, 102, "low"),
            (80, 109.9, "high"),
            (88, 103, "low"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    for c in candidates:
        for g in c.get("geometry", []):
            role = g.get("meta_json", {}).get("role", "")
            kind = g.get("kind", "")
            assert "pattern_path" not in role, f"Found pattern_path role in {c['pattern_type']}"
            assert kind != "pattern_path", f"Found pattern_path kind in {c['pattern_type']}"


def test_classic_pattern_region_contract_primary_and_candidates():
    candles = make_candles(
        [
            (0, 100),
            (8, 101),
            (16, 109.8),
            (24, 100.5),
            (32, 110),
            (40, 100.8),
            (48, 109.7),
            (56, 100.3),
            (64, 110.1),
            (72, 100.1),
            (80, 109.9),
            (88, 100.4),
            (95, 105),
        ]
    )
    pivots = make_pivots(
        candles,
        [
            (0, 100, "low"),
            (8, 101, "low"),
            (16, 109.8, "high"),
            (24, 100.5, "low"),
            (32, 110, "high"),
            (40, 100.8, "low"),
            (48, 109.7, "high"),
            (56, 100.3, "low"),
            (64, 110.1, "high"),
            (72, 100.1, "low"),
            (80, 109.9, "high"),
            (88, 100.4, "low"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    payload = build_classic_patterns_payload("btc-usdt-perp", "1h", candles, candidates)

    assert payload["version"] == CLASSIC_PATTERN_CONTRACT_VERSION
    assert payload["primary"]
    assert len(payload["candidates"]) <= 3
    assert payload["primary"]["display_role"] == "primary"
    assert payload["primary"]["region"]["fill_alpha"] == 0.12
    assert len(payload["primary"]["region"]["polygon_points"]) >= 4
    display_range = payload["primary"]["display_range"]
    assert display_range["projection_end_index"] - display_range["end_index"] <= 6
    contract_types = {
        payload["primary"]["pattern_type"],
        *(item["pattern_type"] for item in payload["candidates"]),
    }
    assert "rectangle" in contract_types
    assert (
        "突破确认位" in payload["primary"]["explanation"]["tooltip"]
        or "跌破确认位" in payload["primary"]["explanation"]["tooltip"]
    )


def test_overwide_classic_region_is_hidden_from_primary():
    candles = make_candles([(0, 100), (95, 104)])
    candidate = {
        "pattern_type": "channel",
        "status": "candidate",
        "bias": "neutral",
        "confidence": 0.72,
        "quality": 0.7,
        "points": [
            Pivot(ts=candles[10].ts_open, price=60, kind="low", index=10),
            Pivot(ts=candles[20].ts_open, price=160, kind="high", index=20),
            Pivot(ts=candles[30].ts_open, price=62, kind="low", index=30),
            Pivot(ts=candles[40].ts_open, price=158, kind="high", index=40),
        ],
        "levels": {"support": 60, "resistance": 160},
        "score_breakdown": {"touch_score": 0.8, "fit_score": 0.8},
        "reasons": ["测试用异常宽区域"],
        "geometry": [
            {
                "kind": "region",
                "points": [
                    {"index": 10, "time": candles[10].ts_open.isoformat(), "price": 60},
                    {"index": 20, "time": candles[20].ts_open.isoformat(), "price": 160},
                    {"index": 40, "time": candles[40].ts_open.isoformat(), "price": 158},
                    {"index": 30, "time": candles[30].ts_open.isoformat(), "price": 62},
                ],
                "meta_json": {"role": "pattern_region"},
            }
        ],
    }

    payload = build_classic_patterns_payload("btc-usdt-perp", "1h", candles, [candidate])

    assert payload["primary"] is None
    assert payload["candidates"][0]["renderable"] is False
    assert "区域过宽" in payload["candidates"][0]["hidden_reason"]


def test_region_projection_uses_candle_interval_not_fixed_hours():
    candles = make_candles([(0, 100), (4, 104)], length=5)
    for idx, candle in enumerate(candles):
        candle.ts_open = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=idx)

    region = _make_region_geometry(
        "rectangle_range",
        "candidate",
        0,
        100,
        6,
        102,
        6,
        98,
        0,
        96,
        None,
        None,
        candles,
        0.6,
    )


def test_channel_polygon_left_edge_includes_older_pivots_in_tolerance():
    """Regression: channel polygon must extend its left edge back to the
    oldest pivot that still fits the channel line within tolerance, not
    just the 4th-from-last pivot. Without this the user sees a visible
    gap between the actual swing low/high that started the range and
    the polygon's left corner.
    """
    # Build a flat horizontal channel from index 4 onward. Older pivots
    # at indices 4 and 12 also touch the same channel boundaries so the
    # detector must include them when extending the window backwards.
    # The previous `highs[-4:] / lows[-4:]` clip would land the left
    # edge near index 56 — well inside the channel — leaving the
    # leftmost pivots stranded outside the polygon.
    candles = make_candles(
        [
            (0, 50),
            (4, 60),
            (8, 60),
            (12, 60),
            (16, 60),
            (24, 60),
            (32, 60),
            (40, 60),
            (48, 60),
            (56, 60),
            (64, 60),
            (72, 60),
            (80, 60),
            (95, 60),
        ]
    )
    # `make_candles` interpolates linearly between the listed pivot
    # points, so every index in between carries price 60. Add a second
    # boundary at 55 by re-pricing a few candles.
    for i in (4, 12, 24, 32, 40, 48, 56, 64, 72, 80):
        candles[i].low = 55
    pivots = make_pivots(
        candles,
        [
            (4, 60, "high"),
            (12, 60, "high"),
            (24, 60, "high"),
            (32, 55, "low"),
            (40, 60, "high"),
            (48, 55, "low"),
            (56, 60, "high"),
            (64, 55, "low"),
            (72, 60, "high"),
            (80, 55, "low"),
        ],
    )
    candidates = detect_classic_patterns(candles, pivots)
    channels = [c for c in candidates if c["pattern_type"] == "channel"]
    assert channels, "expected at least one channel candidate"
    region = next(
        g for c in channels for g in c["geometry"] if g["kind"] == "region"
    )
    left_index = region["points"][0]["index"]
    # Before the fix: left_index would be the 4th-from-last low (56 or
    # 64). After the fix it must reach back to at most index 12 — the
    # oldest pivot that fits the channel line.
    assert left_index <= 12, (
        f"channel polygon left edge (index={left_index}) must extend "
        f"back to the oldest fitting pivot (index ≤ 12). With the old "
        f"`highs[-4:]` clip the left edge would sit around index 56."
    )
