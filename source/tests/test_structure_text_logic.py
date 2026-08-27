from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.structure.snapshot_service import (
    _compute_text_decision,
    _primary_boundary_evidence,
)
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


def test_inside_includes_the_exact_rendered_boundary_evidence():
    result = resolve_structure_text(
        local_state="inside",
        overall_bias="bullish",
        contribution_breakdown={"classic": 0.12},
        pattern_type="rectangle",
        pattern_label="矩形整理",
        lower_boundary=60.25,
        upper_boundary=72.5,
        boundary_as_of="2026-08-23T00:00:00+00:00",
        boundary_valid=True,
    )
    assert result["boundary_valid"] is True
    assert result["lower_boundary"] == 60.25
    assert result["upper_boundary"] == 72.5
    assert "矩形整理" in result["headline"]
    assert "60.2500–72.5000" in result["headline"]


def _candles(count: int, close: str = "65") -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            ts_open=datetime(2026, 8, 1, tzinfo=timezone.utc),
            close=Decimal(close),
        )
        for _ in range(count)
    ]


def _fusion(bias: str = "bullish") -> SimpleNamespace:
    return SimpleNamespace(
        overall_bias=bias,
        overall_score=0.2,
        overall_confidence=0.8,
        conflict_state=False,
        conflict_type=None,
        contribution_breakdown={"swing": 0.2},
        primary_drivers=[],
        opposing_factors=[],
    )


def test_snapshot_without_primary_pattern_never_claims_price_is_inside_range():
    classic_bundle = SimpleNamespace(score=SimpleNamespace(metadata={"classic_patterns": {}}))
    decision = _compute_text_decision(_fusion(), classic_bundle, _candles(5))
    assert decision["resolved_state"] == "no_actionable_pattern"
    assert decision["boundary_valid"] is False
    assert "区间内部" not in decision["headline"]


def test_boundary_evidence_rejects_missing_unrenderable_and_inverted_shapes():
    candles = _candles(5)
    assert _primary_boundary_evidence(None, candles)["boundary_valid"] is False
    assert _primary_boundary_evidence({"renderable": False}, candles)["boundary_valid"] is False
    inverted = {
        "renderable": True,
        "display_range": {"projection_end_index": 4},
        "levels": {"resistance": 50, "support": 70},
    }
    assert _primary_boundary_evidence(inverted, candles)["boundary_valid"] is False


def test_boundary_evidence_evaluates_sloped_lines_at_latest_index():
    primary = {
        "renderable": True,
        "pattern_type": "channel",
        "display_name": "上升通道",
        "status": "forming",
        "display_range": {"projection_end_index": 4},
        "lines": [
            {
                "role": "upper_boundary",
                "points": [{"index": 0, "price": 70}, {"index": 4, "price": 74}],
            },
            {
                "role": "lower_boundary",
                "points": [{"index": 0, "price": 60}, {"index": 4, "price": 64}],
            },
        ],
    }
    evidence = _primary_boundary_evidence(primary, _candles(5))
    assert evidence["boundary_valid"] is True
    assert evidence["upper_boundary"] == 74
    assert evidence["lower_boundary"] == 64


def test_boundary_evidence_marks_projection_expired_instead_of_extending_claim():
    primary = {
        "renderable": True,
        "pattern_type": "rectangle",
        "display_range": {"projection_end_index": 2},
        "levels": {"resistance": 72, "support": 60},
    }
    evidence = _primary_boundary_evidence(primary, _candles(5))
    assert evidence["boundary_expired"] is True
    assert evidence["boundary_valid"] is False


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
