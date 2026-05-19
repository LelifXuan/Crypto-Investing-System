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
        "candle_completeness": 0.30,
        "candle_freshness": 0.20,
        "multi_timeframe_availability": 0.15,
        "derivatives_data_availability": 0.15,
        "orderbook_data_availability": 0.10,
        "macro_event_availability": 0.10,
    },
    "long_weights": {
        "mtf_trend_bullish": 0.18,
        "bullish_structure": 0.18,
        "bullish_momentum": 0.14,
        "bullish_flow": 0.14,
        "derivatives_long_confirmation": 0.10,
        "execution_quality": 0.08,
        "long_risk_reward": 0.10,
        "regime_fit_long": 0.08,
    },
    "short_weights": {
        "mtf_trend_bearish": 0.18,
        "bearish_structure": 0.18,
        "bearish_momentum": 0.14,
        "bearish_flow": 0.14,
        "derivatives_short_confirmation": 0.10,
        "execution_quality": 0.08,
        "short_risk_reward": 0.10,
        "regime_fit_short": 0.08,
    },
    "neutral_weights": {
        "range_structure": 0.25,
        "low_adx": 0.20,
        "low_volume_confirmation": 0.20,
        "low_directional_spread": 0.15,
        "high_conflict_score": 0.10,
        "event_uncertainty": 0.10,
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
        "spread_hard_limit_bps": 25,
        "slippage_hard_limit_bps": 40,
        "min_depth_score": 25,
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
        "setup_valid_bars": {"1w": 8, "1d": 10, "4h": 12, "1h": 16},
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
    return app_paths.repo_root / "app" / "monitoring" / "configs" / "market_strategy_signal_config_v17.json"


def load_strategy_signal_config() -> dict[str, Any]:
    candidates = [
        strategy_signal_config_path(),
        app_paths.repo_root / "app" / "monitoring" / "configs" / "market_strategy_signal_config_v16.json",
        app_paths.repo_root / "app" / "monitoring" / "configs" / "market_strategy_signal_config_v15.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return _deep_merge(DEFAULT_STRATEGY_SIGNAL_CONFIG, payload)
    return DEFAULT_STRATEGY_SIGNAL_CONFIG
