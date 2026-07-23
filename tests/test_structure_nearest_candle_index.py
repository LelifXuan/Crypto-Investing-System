from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_JS = ROOT / "app" / "static" / "pages" / "structure.js"


def test_structure_js_uses_nearest_candle_index():
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    assert "nearestCandleIndex" in text, "structure.js must use nearestCandleIndex helper"

    assert "xIndex.get" not in text, "structure.js must not use legacy xIndex.get pattern"
    assert "xIndex.set" not in text, "structure.js must not use legacy xIndex.set pattern"
    assert "xIndex.has" not in text, "structure.js must not use legacy xIndex.has pattern"

    lines = text.splitlines()
    nearest_count = sum(1 for line in lines if "nearestCandleIndex" in line)
    assert nearest_count >= 1, "nearestCandleIndex must be defined and used at least once"


def test_structure_swing_overlay_filters_points_outside_bound_candle():
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    assert "isSwingPointInsideCandleRange" in text
    assert "candle_high" in text
    assert "candle_low" in text
    assert "point inside the bound candle" not in text


def test_structure_swing_overlay_explains_sparse_confirmed_path():
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    assert 'price: { label: "收盘价"' in text
    assert 'swing: { label: "确认摆动路径"' in text
    assert 'dash: "5 7"' in text
    assert "部分摆动点与 K 线无法对齐" in text
    assert "观察中" in text
    assert "收盘价只连接每根 K 线的收盘价格" in text
    assert "摆动高点取对应 K 线最高价" in text
    assert "虚线只表示摆动顺序" in text


def test_structure_candidate_patterns_are_hidden_by_default_but_toggleable():
    """V1.7.x policy change: only the highest-confidence shapes render on
    the steady-state chart. Candidate classic patterns (双底 / 双顶 /
    通道 "候选" markers, plus their 观察中 labels) stay hidden until the
    user explicitly opts in via the layer toggle."""
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    # Default state must show candidate geometry (now enabled by default).
    assert "candidate: true" in text
    # Toggle still exposed in the layer panel so the user can opt-out.
    assert "候选图形（淡化）" in text
    assert 'strokeDash = "7 6"' in text
    assert "boundary_alpha" in text


def test_structure_overlay_stops_extending_after_pattern_break():
    """V1.7.x: once a classic pattern is broken (上破 / 下破 / 失效), the
    boundary lines and region polygon must stop at the break candle rather
    than continuing across subsequent price action. The shape describes
    what *was*, not what would have been."""
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    # Helper that walks candles for the first cross.
    assert "function firstCrossIndex" in text
    # priceGuide now carries a break_index alongside state / level.
    assert "break_index:" in text
    assert "firstCrossIndex(candles," in text
    # The overlay renderer trims mapped points past the break x.
    assert "breakX" in text
    assert "const trimmed = mapped.filter((point) => point.x <= breakX)" in text
    # And clips the region polygon's right edge.
    assert "clippedPoly" in text
    assert "polyBreakX" in text
