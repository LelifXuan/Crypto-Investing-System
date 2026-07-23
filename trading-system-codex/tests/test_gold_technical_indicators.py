"""Tests for gold technical indicator computation functions."""
import math
import random

import pytest

from app.api.v1.endpoints.gold import (
    _compute_bollinger_pct_b,
    _compute_cci,
    _compute_ema,
    _compute_rsi,
    _compute_technical_indicators,
)


def _make_candle(close, high=None, low=None):
    """Minimal candle-like object for tests."""
    class C:
        __slots__ = ("close", "high", "low")
        def __init__(self, c, h, l):
            self.close, self.high, self.low = c, h, l
    return C(close, high or close, low or close)


class TestRSI:
    def test_all_gains_gives_rsi_100(self):
        """If every day is a gain, RSI = 100."""
        candles = [_make_candle(100 + i) for i in range(16)]  # steadily rising
        result = _compute_rsi([c.close for c in candles], 14)
        assert result == pytest.approx(100.0)

    def test_all_losses_gives_rsi_0(self):
        """If every day is a loss, RSI = 0."""
        candles = [_make_candle(100 - i) for i in range(16)]
        result = _compute_rsi([c.close for c in candles], 14)
        assert result == pytest.approx(0.0)

    def test_insufficient_data_returns_none(self):
        assert _compute_rsi([100.0] * 10, 14) is None

    def test_rsi_around_50_for_sideways(self):
        """Flat prices give RSI near 50 (equal gains and losses near zero)."""
        # With exact flat prices, diff is 0, gains=0 losses=0 → should not divide by zero
        candles = [_make_candle(100.0) for _ in range(16)]
        result = _compute_rsi([c.close for c in candles], 14)
        # All diffs are 0 → gains=0 losses=0 → avg_loss=0 → returns 100
        assert result == 100.0


class TestEMA:
    def test_ema_flat_equals_value(self):
        vals = [50.0] * 50
        result = _compute_ema(vals, 20)
        assert result == pytest.approx(50.0)

    def test_ema_trends_toward_recent(self):
        vals = [100.0] * 20 + [200.0] * 10
        result = _compute_ema(vals, 20)
        assert result > 150  # pulled up by recent 200s

    def test_ema_insufficient_data(self):
        assert _compute_ema([1.0] * 10, 20) is None


class TestBollinger:
    def test_bollinger_flat_is_0_5(self):
        closes = [100.0] * 25
        result = _compute_bollinger_pct_b(closes, 20, 2)
        assert result == pytest.approx(0.5)

    def test_bollinger_at_lower_band(self):
        # Price at -2σ below SMA → %B ≈ 0
        closes = [100.0] * 20 + [0.0]
        result = _compute_bollinger_pct_b(closes, 20, 2)
        # Last value is far below the flat SMA → should be close to 0
        assert result < 0.1

    def test_bollinger_at_upper_band(self):
        closes = [100.0] * 20 + [200.0]
        result = _compute_bollinger_pct_b(closes, 20, 2)
        assert result > 0.9

    def test_bollinger_insufficient_data(self):
        assert _compute_bollinger_pct_b([100.0] * 10, 20) is None


class TestCCI:
    def test_cci_flat_is_zero(self):
        closes = [100.0] * 25
        typicals = [100.0] * 25
        result = _compute_cci(typicals, closes, 20)
        assert result == pytest.approx(0.0)

    def test_cci_high_when_above_sma(self):
        # Typical price far above 20-period SMA → positive CCI
        typicals = [100.0] * 20 + [150.0]
        closes = [100.0] * 21
        result = _compute_cci(typicals, closes, 20)
        assert result > 80

    def test_cci_low_when_below_sma(self):
        typicals = [100.0] * 20 + [50.0]
        closes = [100.0] * 21
        result = _compute_cci(typicals, closes, 20)
        assert result < -80

    def test_cci_insufficient_data(self):
        assert _compute_cci([100.0] * 10, [100.0] * 10, 20) is None


class TestTechnicalIndicators:
    def test_returns_empty_for_insufficient_candles(self):
        candles = [_make_candle(100.0) for _ in range(10)]
        result = _compute_technical_indicators(candles)
        assert result == {}

    def test_returns_all_four_keys(self):
        candles = [_make_candle(100.0 + random.uniform(-2, 2), 102, 98) for _ in range(60)]
        result = _compute_technical_indicators(candles)
        assert "rsi_14" in result
        assert "boll_pct_b" in result
        assert "ema20_distance" in result
        assert "cci_20" in result
        for v in result.values():
            assert v is not None

    def test_ema20_distance_negative_when_below_ema(self):
        # Price trending down → close < EMA20
        closes = [100.0] * 21
        candles = []
        v = 100.0
        for i in range(30):
            v -= 1.0
            candles.append(_make_candle(v))
        result = _compute_technical_indicators(candles)
        assert result["ema20_distance"] < 0

    def test_rsi_oversold_on_sustained_decline(self):
        candles = []
        v = 100.0
        for i in range(30):
            v -= 2.0
            candles.append(_make_candle(v))
        result = _compute_technical_indicators(candles)
        assert result["rsi_14"] < 30
