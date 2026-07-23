"""Acceptance tests for the explicit direction-score scale contract.

The T01 audit found that ``normalize_direction_metrics(direction_score)``
silently auto-detected a ``0..100`` input as legacy 50-neutral percentages,
which flipped ``chip_structure.direction_score = 0`` (a true neutral reading
in the signed ``-100..100`` contract) into a 100 % bearish signal. The
fix forces callers to declare the scale. These tests pin the new contract
at the regression points the audit called out.
"""

from __future__ import annotations

import math

import pytest

from app.services.strategy_signal.setup_lifecycle import normalize_direction_metrics


def test_signed_zero_is_neutral_not_max_bearish():
    """The P0 regression: signed 0 must be neutral, not max bearish."""
    metrics = normalize_direction_metrics(0, scale="signed")

    assert metrics["bullish"] == 0
    assert metrics["bearish"] == 0
    assert metrics["range"] == 100
    assert metrics["raw"] == 0
    assert metrics["scale"] == "signed"


def test_signed_positive_40_does_not_satisfy_short_setup():
    """Signed +40 must not be read as a strong bearish signal."""
    metrics = normalize_direction_metrics(40, scale="signed")

    assert metrics["bullish"] == 40
    assert metrics["bearish"] == 0
    assert metrics["scale"] == "signed"
    assert metrics["bullish"] < 58
    assert metrics["bearish"] < 58


def test_signed_negative_40_does_not_satisfy_long_setup():
    """Signed -40 must not be read as a strong bullish signal."""
    metrics = normalize_direction_metrics(-40, scale="signed")

    assert metrics["bullish"] == 0
    assert metrics["bearish"] == 40
    assert metrics["scale"] == "signed"
    assert metrics["bearish"] < 58
    assert metrics["bullish"] < 58


@pytest.mark.parametrize(
    "score, expected_bullish, expected_bearish, expected_range",
    [
        (100, 100, 0, 0),
        (80, 80, 0, 20),
        (20, 20, 0, 80),
        (0, 0, 0, 100),
        (-20, 0, 20, 80),
        (-40, 0, 40, 60),
        (-80, 0, 80, 20),
        (-100, 0, 100, 0),
    ],
)
def test_signed_scale_boundaries(score, expected_bullish, expected_bearish, expected_range):
    metrics = normalize_direction_metrics(score, scale="signed")
    assert metrics["bullish"] == expected_bullish
    assert metrics["bearish"] == expected_bearish
    assert metrics["range"] == expected_range
    assert metrics["raw"] == score
    assert metrics["scale"] == "signed"


def test_signed_clamps_out_of_range_inputs():
    metrics_pos = normalize_direction_metrics(250, scale="signed")
    metrics_neg = normalize_direction_metrics(-250, scale="signed")

    assert metrics_pos["raw"] == 100
    assert metrics_pos["bullish"] == 100
    assert metrics_neg["raw"] == -100
    assert metrics_neg["bearish"] == 100


def test_legacy_zero_is_max_bearish_legacy_contract():
    """Legacy 0..100 contract: 0% bullish == 100% bearish."""
    metrics = normalize_direction_metrics(0, scale="legacy_0_100")
    assert metrics["bullish"] == 0
    assert metrics["bearish"] == 100
    assert metrics["range"] == 0
    assert metrics["scale"] == "legacy_0_100"


def test_legacy_fifty_is_neutral():
    metrics = normalize_direction_metrics(50, scale="legacy_0_100")
    assert metrics["bullish"] == 50
    assert metrics["bearish"] == 50
    assert metrics["range"] == 100


def test_legacy_rejects_signed_range():
    """Out-of-legacy-range scores must fail loudly, not silently coerce."""
    with pytest.raises(ValueError, match="legacy_0_100"):
        normalize_direction_metrics(-50, scale="legacy_0_100")
    with pytest.raises(ValueError, match="legacy_0_100"):
        normalize_direction_metrics(150, scale="legacy_0_100")


def test_scale_must_be_explicit():
    with pytest.raises(TypeError):
        normalize_direction_metrics(0)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="scale"):
        normalize_direction_metrics(0, scale="not-a-scale")  # type: ignore[arg-type]


def test_non_numeric_inputs_fall_back_to_scale_neutral():
    """to_float fallback uses scale-appropriate default (0 for signed, 50 for legacy)."""
    signed = normalize_direction_metrics(None, scale="signed")
    legacy = normalize_direction_metrics(None, scale="legacy_0_100")

    assert signed["raw"] == 0
    assert signed["bullish"] == 0
    assert signed["bearish"] == 0
    assert legacy["raw"] == 50
    assert legacy["bullish"] == 50
    assert legacy["bearish"] == 50


def test_metrics_are_floats_and_rounded_to_4():
    metrics = normalize_direction_metrics(33.333_333, scale="signed")
    assert all(isinstance(v, float) for v in metrics.values() if isinstance(v, float))
    for value in (metrics["bullish"], metrics["bearish"], metrics["range"], metrics["raw"]):
        assert math.isclose(value, round(value, 4))
