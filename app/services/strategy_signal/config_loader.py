from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.paths import app_paths

DEFAULT_STRATEGY_SIGNAL_CONFIG: dict[str, Any] = {
    "version": "market-strategy-signal-v1.7",
    "model_versions": {
        "strategy_model": "strategy-signal-v1.7",
        "scoring_engine": "direction-scoring-v1.7",
        "setup_lifecycle_engine": "setup-lifecycle-v1.7",
        "review_engine": "review-engine-v0.3",
    },
    "timeframe_mapping": {
        "1w": "1d",
        "1d": "4h",
        "4h": "1h",
        "1h": "15m",
    },
    "data_quality_weights": {
        "candle_completeness": 0.25,
        "candle_freshness": 0.20,
        "multi_timeframe_availability": 0.20,
        "technical_risk_availability": 0.10,
        "macro_event_availability": 0.15,
        "execution_quality": 0.10,
    },
    "long_weights": {
        "mtf_trend_bullish": 0.18,
        "bullish_structure": 0.18,
        "momentum_short": 0.06,
        "momentum_mid": 0.05,
        "momentum_long": 0.05,
        "long_risk_reward": 0.12,
        "regime_fit_long": 0.13,
        "execution_quality": 0.10,
        "range_structure": 0.06,
        "funding_pressure_long": 0.07,
    },
    "short_weights": {
        "mtf_trend_bearish": 0.18,
        "bearish_structure": 0.18,
        "momentum_short_bearish": 0.06,
        "momentum_mid_bearish": 0.05,
        "momentum_long_bearish": 0.05,
        "short_risk_reward": 0.12,
        "regime_fit_short": 0.13,
        "execution_quality": 0.10,
        "range_structure": 0.06,
        "funding_pressure_short": 0.07,
    },
    "neutral_weights": {
        "range_structure": 0.25,
        "low_adx": 0.20,
        "low_volume_confirmation": 0.20,
        "low_directional_spread": 0.15,
        "high_conflict_score": 0.10,
        "event_uncertainty": 0.10,
    },
    "vwap_cost_channel": {
        "enabled": True,
        "short_window": 50,
        "long_window": 100,
        "alt_short_window": 30,
        "alt_long_window": 120,
        "price_buffer": 0.01,
        "spread_buffer": 0.005,
        "slope_lookback": 10,
        "use_as_filter_not_trigger": True,
    },
    "thresholds": {
        "data_quality_min_decision": 40,
        "event_wait": 75,
        "no_edge_score": 55,
        "bias_score": 58,
        "setup_score": 66,
        "trigger_score": 72,
        "dominant_gap": 18,
        "conflict_both_high": 65,
        "conflict_gap": 15,
        "min_rr_trade": 1.5,
        "missed_move_r_multiple": 1.0,
        "missed_move_atr_multiple": 1.5,
        "tp_hit_tolerance_atr": 0.1,
        "lower_tf_trigger_min_score": 60,
        "lower_tf_momentum_min_score": 55,
        "strong_trend_adx_min": 25,
        "strong_trend_momentum_min": 60,
        "strong_trend_atr_expansion_min": 60,
        "strong_trend_flow_min": 55,
        "chase_max_distance_atr": 1.5,
        "setup_valid_bars": {"1w": 8, "1d": 10, "4h": 12, "1h": 16, "15m": 20},
    },
    "state_permissions": {
        "NO_EDGE": "observe_only",
        "OBSERVE": "observe_only",
        "CONFLICTED_NO_TRADE": "observe_only",
        "LONG_BIAS": "observe_only",
        "SHORT_BIAS": "observe_only",
        "SETUP_DETECTED": "conditional",
        "WAIT_LONG_CONFIRMATION": "conditional",
        "WAIT_SHORT_CONFIRMATION": "conditional",
        "WAIT_LOWER_TF_CONFIRMATION": "conditional",
        "WAIT_PULLBACK_CONFIRMATION": "conditional",
        "LONG_TRIGGERED": "allow",
        "SHORT_TRIGGERED": "allow",
        "TREND_FOLLOW_TRIGGERED": "allow",
        "BREAKDOWN_TRIGGERED": "allow",
        "BREAKOUT_TRIGGERED": "allow",
        "MOVE_MISSED": "observe_only",
        "WAIT_RETEST_AFTER_MISSED_MOVE": "observe_only",
        "TP1_HIT": "observe_only",
        "TP2_HIT": "observe_only",
        "STOP_HIT": "observe_only",
        "SETUP_EXPIRED": "observe_only",
        "SETUP_INVALIDATED": "observe_only",
        "INVALID_PLAN_LEVELS": "blocked",
        "EVENT_WAIT": "observe_only",
        "RISK_OFF": "blocked",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def strategy_signal_config_path() -> Path:
    return (
        app_paths.resource_root
        / "app"
        / "monitoring"
        / "configs"
        / "market_strategy_signal_config_v17.json"
    )


def load_strategy_signal_config() -> dict[str, Any]:
    path = strategy_signal_config_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _deep_merge(DEFAULT_STRATEGY_SIGNAL_CONFIG, payload)
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_STRATEGY_SIGNAL_CONFIG


def detect_mode(
    regime: str | None,
    adx: float | None,
    asset_class: str | None = "stock",
    timeframe: str | None = "1d",
) -> str:
    """5-layer decision: returns 'trend' | 'range' | 'transition'.

    Used by snapshot_builder to select which per-mode weight table to apply.
    """
    regime_norm = str(regime or "").strip().lower()
    # Layer 1: explicit regime wins
    if regime_norm in ("trend", "trending"):
        return "trend"
    if regime_norm in ("balance", "range", "ranging"):
        return "range"
    if regime_norm in ("transition", "shock"):
        return "transition"
    # Layer 2: crypto + short TF defaults to range (scalping-friendly)
    if asset_class == "crypto" and timeframe in ("1h", "15m"):
        return "range"
    # Layer 3: ADX drives the decision (when we have meaningful ADX data)
    adx_value = float(adx) if adx is not None else 0.0
    if adx_value >= 25:
        return "trend"
    if 0 < adx_value < 20:
        return "range"
    # Layer 4: ambiguous ADX (20..25) OR no ADX data (None/0) → transition
    return "transition"


def detect_asset_class(instrument_id: str | None) -> str:
    """Detect 'crypto' vs 'stock' from instrument_id string.

    Defaults to 'stock' when the instrument_id is empty or unrecognized.
    """
    if not instrument_id:
        return "stock"
    crypto_patterns = ("btc", "eth", "usdt-perp", "btc-usdt", "eth-usdt")
    inst_lower = instrument_id.lower()
    if any(p in inst_lower for p in crypto_patterns):
        return "crypto"
    return "stock"
