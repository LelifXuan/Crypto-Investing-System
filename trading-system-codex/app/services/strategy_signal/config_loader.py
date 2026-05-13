from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.paths import app_paths

DEFAULT_STRATEGY_SIGNAL_CONFIG: dict[str, Any] = {
    "version": "market-strategy-signal-v1.6",
    "model_versions": {
        "strategy_model": "strategy-signal-v1.6",
        "scoring_engine": "direction-scoring-v1.6",
        "review_engine": "review-engine-v0.2",
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
    return app_paths.repo_root / "app" / "monitoring" / "configs" / "market_strategy_signal_config_v16.json"


def load_strategy_signal_config() -> dict[str, Any]:
    candidates = [
        strategy_signal_config_path(),
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

