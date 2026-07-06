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
