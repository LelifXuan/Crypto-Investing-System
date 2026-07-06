"""Unit tests for V1.7.6 — Layer B + Layer C: Funding regime sub-score."""

from __future__ import annotations

from app.services.strategy_signal.snapshot_builder import (
    _compute_funding_pressure,
    _remap_funding_crowding,
)


def test_funding_pressure_positive_hot_suppresses_long_rewards_short():
    long, short, degraded = _compute_funding_pressure("positive_hot")
    assert long == 15.0
    assert short == 85.0
    assert degraded is False


def test_funding_pressure_negative_hot_suppresses_short_rewards_long():
    long, short, degraded = _compute_funding_pressure("negative_hot")
    assert long == 85.0
    assert short == 15.0
    assert degraded is False


def test_funding_pressure_neutral_is_50_50():
    long, short, degraded = _compute_funding_pressure("neutral")
    assert long == 50.0
    assert short == 50.0
    assert degraded is False


def test_funding_pressure_missing_returns_none_with_degraded_flag():
    for value in (None, "", "DATA_MISSING", "missing", "degraded", "unexpected_state"):
        long, short, degraded = _compute_funding_pressure(value)
        assert long is None, f"expected None for {value!r}, got {long}"
        assert short is None, f"expected None for {value!r}, got {short}"
        assert degraded is True, f"expected degraded=True for {value!r}"


def test_remap_funding_crowding_positive_hot_returns_80():
    assert _remap_funding_crowding("positive_hot") == 80.0


def test_remap_funding_crowding_negative_hot_returns_80():
    assert _remap_funding_crowding("negative_hot") == 80.0


def test_remap_funding_crowding_neutral_returns_20():
    assert _remap_funding_crowding("neutral") == 20.0


def test_remap_funding_crowding_missing_returns_0():
    for value in (None, "DATA_MISSING", "missing", "degraded", "extreme_positive_hot"):
        assert _remap_funding_crowding(value) == 0.0, f"expected 0 for {value!r}"


# --- weighted_score_skip (V1.7.6 funding slot degradation) ---


from app.services.strategy_signal.scoring_engine import weighted_score_skip


def test_weighted_score_skip_all_slots_present_normal_behavior():
    """When no slots are None, output equals old weighted_score."""
    values = {"a": 80.0, "b": 40.0}
    weights = {"a": 0.5, "b": 0.5}
    result = weighted_score_skip(values, weights)
    assert result == 60.0


def test_weighted_score_skip_none_slot_renormalizes():
    """Skip None, renormalize the remaining slots to original total weight."""
    # Without skip: (80 * 0.5 + 40 * 0.5) = 60
    # With skip and funding_pressure_long=None:
    #   used_pairs = [(80, 0.4), (40, 0.5)]  (a weights 0.5, b 0.5)
    #   sum_weights = 0.4 + 0.5 = 0.9
    #   score = (80*0.4 + 40*0.5) / 0.9 * (0.5 + 0.5) = (32 + 20)/0.9 = 57.78
    values = {"a": 80.0, "b": 40.0, "funding_pressure_long": None}
    weights = {"a": 0.4, "b": 0.5, "funding_pressure_long": 0.1}
    result = weighted_score_skip(values, weights)
    # Expected renormalization: (80*0.4 + 40*0.5) / 0.9 * 1.0 = 32+20=52/0.9 = 57.778
    assert abs(result - (52.0 / 0.9)) < 0.01


def test_weighted_score_skip_all_slots_none_returns_50():
    """All degraded → neutral 50."""
    values = {"a": None, "b": None}
    weights = {"a": 0.5, "b": 0.5}
    result = weighted_score_skip(values, weights)
    assert result == 50.0


def test_weighted_score_skip_clamps_to_0_100():
    """Output always in [0, 100]."""
    values = {"a": 200.0}  # out-of-band
    weights = {"a": 1.0}
    result = weighted_score_skip(values, weights)
    assert 0.0 <= result <= 100.0
