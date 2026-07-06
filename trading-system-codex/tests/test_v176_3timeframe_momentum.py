"""Unit tests for V1.7.6 — Layer A: 3-timeframe momentum."""

from __future__ import annotations

import math

from app.services.strategy_signal.risk_reward import _percentile_rank


def test_percentile_rank_empty_history_returns_50():
    """No history → neutral 50."""
    assert _percentile_rank([], 70.0) == 50.0


def test_percentile_rank_none_current_returns_50():
    """NaN/None current → neutral 50."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile_rank(history, None) == 50.0
    assert _percentile_rank(history, math.nan) == 50.0


def test_percentile_rank_median_value_returns_50():
    """Current value at exact median → 50."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]  # 5 values, median = 30
    result = _percentile_rank(history, 30.0)
    assert 50.0 <= result <= 70.0


def test_percentile_rank_extreme_high_value():
    """Highest value in history → ~100."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile_rank(history, 50.0) == 100.0


def test_percentile_rank_extreme_low_value():
    """Lowest value in history → 0 (if none below) else <20."""
    history = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile_rank(history, 5.0) == 0.0


def test_percentile_rank_clamps_to_0_100():
    """Output never escapes [0, 100]."""
    history = [10.0] * 90
    result = _percentile_rank(history, 10.0)
    assert 0.0 <= result <= 100.0
    assert result == 100.0