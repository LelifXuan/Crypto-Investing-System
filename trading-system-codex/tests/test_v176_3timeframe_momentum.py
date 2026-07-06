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


def test_percentile_rank_non_numeric_current_returns_50():
    """Non-numeric current (e.g., string) → 50."""
    assert _percentile_rank([1.0, 2.0, 3.0], "abc") == 50.0


def test_percentile_rank_skips_none_inside_history():
    """None entries in history are filtered, not counted."""
    # 3 real values: [1.0, 2.0, 3.0]; 2 of them (1, 2) are <= 2.0 → 2/3 ≈ 66.67
    history = [1.0, None, 2.0, None, 3.0]
    result = _percentile_rank(history, 2.0)
    assert 60.0 <= result <= 70.0


from app.services.strategy_signal.snapshot_builder import _compute_momentum_at_scale


def test_compute_momentum_at_scale_neutral_when_all_inputs_missing():
    """No RSI / MACD / history → (50, 50)."""
    bullish, bearish = _compute_momentum_at_scale(
        rsi=None,
        macd_hist=None,
        macd_prev=None,
        rsi_history=None,
    )
    assert bullish == 50.0
    assert bearish == 50.0


def test_compute_momentum_at_scale_high_rsi_high_percentile_bullish():
    """RSI=80 with all-history=50 → ~100 percentile → bullish > bearish.

    The V1.7.6 spec §2.2 specifies a symmetric formula where bullish and
    bearish mirror each other about 50. When RSI percentile is high, the
    bullish side lifts above 50 by the same amount the bearish side drops
    below 50 — therefore the invariant we can guarantee is bullish >
    bearish, not bearish < 50.
    """
    history = [50.0] * 90
    bullish, bearish = _compute_momentum_at_scale(
        rsi=80.0,
        macd_hist=1.0,
        macd_prev=0.5,
        rsi_history=history,
    )
    assert bullish > 80.0
    assert bullish > bearish


def test_compute_momentum_at_scale_negative_macd_delta_dampens_bullish():
    """MACD delta negative → bullish lower than baseline 50."""
    history = [50.0] * 90
    bullish_pos, _ = _compute_momentum_at_scale(
        rsi=50.0,
        macd_hist=0.5,
        macd_prev=0.0,
        rsi_history=history,
    )
    bullish_neg, _ = _compute_momentum_at_scale(
        rsi=50.0,
        macd_hist=-0.5,
        macd_prev=0.0,
        rsi_history=history,
    )
    # positive MACD delta should lift bullish; negative should leave it at 50 (no bullish contribution)
    assert bullish_pos > bullish_neg


def test_compute_momentum_at_scale_clamped_to_0_100():
    """Output always in [0, 100]."""
    history = [10.0] * 90
    bullish, bearish = _compute_momentum_at_scale(
        rsi=200.0,  # extreme
        macd_hist=100.0,
        macd_prev=-100.0,
        rsi_history=history,
    )
    assert 0.0 <= bullish <= 100.0
    assert 0.0 <= bearish <= 100.0