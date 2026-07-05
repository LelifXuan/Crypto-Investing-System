"""Tests for V1.7.4 mode detection and asset classification helpers."""

from __future__ import annotations

from app.services.strategy_signal.config_loader import (
    detect_asset_class,
    detect_mode,
)


def test_mode_regime_trend_returns_trend():
    assert detect_mode("trend", 30, "stock", "1d") == "trend"


def test_mode_regime_balance_returns_range():
    assert detect_mode("balance", 15, "stock", "1d") == "range"


def test_mode_regime_transition_returns_transition():
    assert detect_mode("transition", 22, "stock", "4h") == "transition"


def test_mode_crypto_short_tf_defaults_to_range():
    """Even with no regime, crypto + 1h/15m defaults to range."""
    assert detect_mode("unknown", 28, "crypto", "1h") == "range"
    assert detect_mode("unknown", 28, "crypto", "15m") == "range"


def test_mode_crypto_long_tf_does_not_default_to_range():
    """crypto + 4h+ goes by ADX/regime, not short-TF default."""
    assert detect_mode("unknown", 30, "crypto", "4h") == "trend"
    assert detect_mode("unknown", 15, "crypto", "4h") == "range"


def test_mode_high_adx_returns_trend():
    assert detect_mode("unknown", 30, "stock", "1d") == "trend"


def test_mode_low_adx_returns_range():
    assert detect_mode("unknown", 18, "stock", "1d") == "range"


def test_mode_falls_back_to_transition_for_ambiguous():
    """ADX in 20..25 range + unknown regime + non-crypto → transition."""
    assert detect_mode("unknown", 22, "stock", "1d") == "transition"


def test_mode_handles_none_inputs():
    assert detect_mode(None, None, "stock", "1d") == "transition"
    assert detect_mode("", 0, "stock", "1d") == "transition"


def test_asset_class_btc_is_crypto():
    assert detect_asset_class("btc-usdt-perp") == "crypto"


def test_asset_class_eth_is_crypto():
    assert detect_asset_class("eth-usdt-perp") == "crypto"


def test_asset_class_usdt_perp_is_crypto():
    assert detect_asset_class("usdt-perp-btc") == "crypto"


def test_asset_class_unknown_is_stock():
    assert detect_asset_class("aapl") == "stock"
    assert detect_asset_class("spy") == "stock"


def test_asset_class_handles_none():
    assert detect_asset_class(None) == "stock"
    assert detect_asset_class("") == "stock"
