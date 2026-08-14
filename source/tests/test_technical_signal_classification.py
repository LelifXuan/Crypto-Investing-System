from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_classifier_handles_empty_input():
    from app.services.technical_signal_classifier import classify_signals
    result = classify_signals([], {}, {})
    assert isinstance(result, list)
    assert len(result) == 0


def test_classifier_ema_bullish_order():
    from app.services.technical_signal_classifier import _classify_ema_structure
    class Candle:
        close = 100.0
    candles = [Candle()]
    core = {"ema_20": {"values": [99]}, "ema_50": {"values": [97]}, "ema_200": {"values": [95]}}
    result = _classify_ema_structure(candles, core, 100)
    assert result is not None
    assert result["signal_state"] in ("bullish", "strong_bullish")
    assert "多头排列" in result.get("signal_label", "")


def test_classifier_ema_bearish_order():
    from app.services.technical_signal_classifier import _classify_ema_structure
    class Candle:
        close = 100.0
    candles = [Candle()]
    core = {"ema_20": {"values": [95]}, "ema_50": {"values": [97]}, "ema_200": {"values": [99]}}
    result = _classify_ema_structure(candles, core, 100)
    assert result is not None
    assert result["signal_state"] in ("bearish", "strong_bearish")


def test_classifier_rsi_overbought():
    from app.services.technical_signal_classifier import _classify_rsi
    result = _classify_rsi({"rsi_14": {"values": [78]}})
    assert result is not None
    assert result["signal_state"] == "risk_hot"


def test_classifier_rsi_oversold():
    from app.services.technical_signal_classifier import _classify_rsi
    result = _classify_rsi({"rsi_14": {"values": [25]}})
    assert result is not None
    assert result["signal_state"] == "risk_cold"


def test_classifier_adx_strong_trend():
    from app.services.technical_signal_classifier import _classify_adx_direction
    result = _classify_adx_direction({"adx_14": {"values": [32]}, "plus_di": {"values": [28]}, "minus_di": {"values": [15]}})
    assert result is not None
    assert result["signal_state"] == "strong_bullish"


def test_classifier_adx_without_di_does_not_pick_direction():
    from app.services.technical_signal_classifier import _classify_adx_direction
    result = _classify_adx_direction({"adx_14": {"values": [32]}})
    assert result is not None
    assert result["signal_state"] == "neutral"
    assert result["tone"] == "neutral"


def test_classifier_bollinger_compression():
    from app.services.technical_signal_classifier import _classify_bollinger
    result = _classify_bollinger({"bbands_upper": {"values": [110]}, "bbands_lower": {"values": [104]}, "bbands_middle": {"values": [107]}}, 108)
    assert result is not None
    assert result["signal_state"] == "neutral"


def test_classifier_bollinger_breakout_is_volatility_event_not_direction():
    from app.services.technical_signal_classifier import _classify_bollinger
    result = _classify_bollinger({"bbands_upper": {"values": [110]}, "bbands_lower": {"values": [90]}, "bbands_middle": {"values": [100]}}, 112)
    assert result is not None
    assert result["signal_state"] == "volatility_breakout_up"
    assert result["tone"] == "event"


def test_classifier_atr_uses_natr():
    from app.services.technical_signal_classifier import _classify_atr
    result = _classify_atr({"atr_14": {"values": [5.0]}}, 100.0)
    assert result is not None
    assert "NATR" in result.get("formula", "")
