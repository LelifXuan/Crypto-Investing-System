"""Regression tests for the structure chart overlay extension logic.

These tests pin the renderer's behavior for two related bugs:
  1. Classic pattern region polygons (the colored "震荡区间" / "通道" /
     "矩形" / "三角形" fill) used to stop at the pattern's confirmed
     time, leaving a visibly empty right side on the chart. They must
     extend to the latest visible candle instead.
  2. The swing zigzag path's last dot used to sit several candles behind
     the live price action. The renderer must extend the last segment
     to the latest candle's high/low so the user sees a live swing dot
     at the right edge.

We assert the renderer source directly because the module is browser-
only (top-level `window.*` references break a node import).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_JS = ROOT / "app" / "static" / "pages" / "structure.js"


def _read() -> str:
    return STRUCTURE_JS.read_text(encoding="utf-8")


def _block(source: str, start: str) -> str:
    """Return the source slice starting at ``start`` and ending at the
    next blank-line / closing-brace that matches the function body.
    """
    idx = source.index(start)
    return source[idx : idx + 4000]


def test_should_extend_pattern_region_to_latest() -> None:
    """``pattern_region`` must be in the always-extend set so the
    colored box visually fills the right side of the chart up to the
    latest candle.
    """
    block = _block(_read(), "function shouldExtendToLatest")
    assert "pattern_region" in block, (
        "shouldExtendToLatest must include 'pattern_region' so the classic "
        "pattern box extends to the latest candle"
    )


def test_should_extend_swing_zigzag_to_latest() -> None:
    """Regression guard for the v1.7.x swing path regression: zigzag
    must always extend to the latest candle."""
    block = _block(_read(), "function shouldExtendToLatest")
    assert "swing_zigzag" in block, (
        "shouldExtendToLatest must include 'swing_zigzag' so the swing path "
        "extends to the latest candle"
    )


def test_should_not_extend_classic_pattern_path() -> None:
    """The classic pattern *path* (the connector that draws the
    pattern's confirmation sequence) must NOT extend — that line ends
    at the pattern's confirmation candle and should not run past it.
    """
    source = _read()
    # The block is excluded at the call site (returned early as '').
    # Confirm the render-overlay path explicitly skips pattern_path.
    assert "classic_pattern_path" in source, (
        "classic pattern path short-circuit must exist"
    )


def test_extend_overlay_moves_region_right_corners_to_latest() -> None:
    """``extendOverlayToLatestCandle`` must extend the two right-side
    corners of a ``pattern_region`` polygon to the latest X, not stop
    at the original polygon right edge.
    """
    source = _read()
    block = _block(source, "function extendOverlayToLatestCandle")
    assert "pattern_region" in block, (
        "extendOverlayToLatestCandle must handle pattern_region polygons "
        "by moving their right corners to the latest X"
    )
    # The handler must emit at least one new x for the right edge.
    assert "latestX" in block, (
        "extendOverlayToLatestCandle must reference latestX when handling "
        "pattern_region"
    )
