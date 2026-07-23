from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.structure.text_logic import resolve_structure_text

PHI = "若综合仍偏多"
PHI2 = "说明其他系统"
PHI3 = "自行判断"


def test_breakdown_overall_bullish():
    result = resolve_structure_text(
        local_state="breakdown",
        overall_bias="weak_bullish",
        conflict_state=True,
        contribution_breakdown={"classic": -0.22, "swing": 0.31, "profile": 0.18},
    )
    assert result["resolved_state"] == "local_breakdown_overall_bullish_downgraded"
    assert result["permission"] == "observe_only"
    assert result["show_trade_action"] is False
    assert PHI not in result["message"]
    assert PHI2 not in result["message"]
    assert PHI3 not in result["message"]


def test_breakdown_overall_bearish():
    result = resolve_structure_text(
        local_state="breakdown",
        overall_bias="bearish",
        conflict_state=False,
        contribution_breakdown={"classic": -0.25, "swing": -0.18, "profile": -0.14},
    )
    assert result["resolved_state"] == "breakdown_aligned_bearish"
    assert result["permission"] == "conditional_short"


def test_breakout_overall_bearish():
    result = resolve_structure_text(
        local_state="breakout",
        overall_bias="bearish",
        conflict_state=True,
        contribution_breakdown={"classic": 0.18, "swing": -0.30, "profile": -0.15},
    )
    assert result["resolved_state"] == "local_breakout_overall_bearish_downgraded"
    assert result["permission"] == "observe_only"
    assert result["show_trade_action"] is False


def test_invalidated():
    result = resolve_structure_text(
        local_state="invalidated",
        overall_bias="bullish",
        conflict_state=False,
        contribution_breakdown={},
    )
    assert result["resolved_state"] == "pattern_invalidated"
    assert result["permission"] == "observe_only"
    assert result["show_trade_action"] is False


def test_inside():
    result = resolve_structure_text(
        local_state="inside",
        overall_bias="neutral",
        conflict_state=False,
        contribution_breakdown={},
    )
    assert result["resolved_state"] == "inside_range"
    assert result["permission"] == "observe_only"


def test_retest():
    result = resolve_structure_text(
        local_state="retest",
        overall_bias="bullish",
        conflict_state=False,
        contribution_breakdown={},
    )
    assert result["resolved_state"] == "retest_phase"
    assert result["permission"] == "observe_only"


def test_breakout_aligned_bullish():
    result = resolve_structure_text(
        local_state="breakout",
        overall_bias="bullish",
        conflict_state=False,
        contribution_breakdown={"classic": 0.30, "swing": 0.25, "profile": 0.20},
    )
    assert result["resolved_state"] == "breakout_aligned_bullish"
    assert result["permission"] == "conditional_long"
    assert result["show_trade_action"] is True


def test_no_forbidden_text():
    for local in ("breakdown", "breakout", "invalidated", "inside", "retest"):
        for bias in ("bullish", "bearish", "neutral"):
            result = resolve_structure_text(
                local_state=local,
                overall_bias=bias,
                contribution_breakdown={},
            )
            combined = result["message"] + result.get("next_trigger", "")
            assert PHI not in combined, f"{local}/{bias}: {PHI} found"
            assert PHI2 not in combined, f"{local}/{bias}: {PHI2} found"
            assert PHI3 not in combined, f"{local}/{bias}: {PHI3} found"
