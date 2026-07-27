"""Regression tests for the structural system '已确认' chip tone.

The right-side system cards (摆动结构 / 经典图形 / 成交量·市场轮廓) all
show a '已确认' chip. We want its background to follow the system's
direction (偏多 / 偏空) so users can read the verdict at a glance.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_JS = ROOT / "app" / "static" / "pages" / "structure.js"


def _read() -> str:
    return STRUCTURE_JS.read_text(encoding="utf-8")


def test_chip_tone_for_direction_function_exists() -> None:
    source = _read()
    assert "function chipToneForDirection" in source, (
        "structure.js must export chipToneForDirection() to map a system's "
        "direction to a chip class (chip-bullish / chip-bearish / chip-neutral)."
    )


def test_chip_tone_for_direction_maps_bullish_variants() -> None:
    source = _read()
    # Find the function body.
    idx = source.index("function chipToneForDirection")
    body = source[idx : idx + 600]
    assert "chip-bullish" in body, (
        "chipToneForDirection must map bullish / weak_bullish to chip-bullish"
    )
    assert "chip-bearish" in body, (
        "chipToneForDirection must map bearish / weak_bearish to chip-bearish"
    )
    assert "chip-neutral" in body, (
        "chipToneForDirection must fall back to chip-neutral"
    )


def test_system_card_invokes_chip_tone() -> None:
    """The system tile must pass the derived tone into statusChip."""
    source = _read()
    # The system tile renders `statusChip(labelFor(...))` — assert the
    # call now also passes a class derived from the system direction.
    assert "chipToneForDirection(system.direction" in source, (
        "system tile must derive its chip class from system.direction via "
        "chipToneForDirection()"
    )
