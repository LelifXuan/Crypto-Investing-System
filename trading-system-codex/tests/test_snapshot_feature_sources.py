"""Acceptance tests for T04: split independent feature sources.

The audit found that the same ``direction_metrics`` value was reused for
``mtf_trend_bullish/bearish``, ``bullish_structure/bearish_structure`` and
``regime_fit_long/short`` so any change in chip direction was triple-
counted. After the fix each feature family reads from a distinct source:

* trend  -> EMA 20/50/200 + slope + ADX
* structure -> ``structure_overall`` (BOS / swing / value area)
* regime_fit -> market regime classifier
* momentum -> RSI + MACD histogram
* technical risk -> OHLCV divergence risk, not microstructure proxies

These tests pin the independence: changing one source must not affect the
other feature families.
"""

from __future__ import annotations

from app.services.strategy_signal.snapshot_builder import (
    StrategySnapshotBuilder,
    _build_regime_fit,
    _build_structure_score,
    _build_trend_score,
)


def test_trend_score_bullish_ema_alignment() -> None:
    """EMA20 > EMA50 > EMA200 with positive slope = strong bullish trend."""

    indicators = {
        "ema_20": 110.0,
        "ema_20_prev": 108.0,
        "ema_50": 105.0,
        "ema_200": 100.0,
        "adx_14": 30.0,
    }
    bullish, bearish = _build_trend_score(indicators)
    assert bullish > 70
    assert bearish < 50
    assert bullish > bearish


def test_trend_score_bearish_ema_alignment() -> None:
    indicators = {
        "ema_20": 95.0,
        "ema_20_prev": 98.0,
        "ema_50": 100.0,
        "ema_200": 105.0,
        "adx_14": 30.0,
    }
    bullish, bearish = _build_trend_score(indicators)
    assert bearish > 70
    assert bullish < 50
    assert bearish > bullish


def test_trend_score_neutral_when_no_ema_data() -> None:
    bullish, bearish = _build_trend_score({"adx_14": 20.0})
    assert bullish == 50
    assert bearish == 50


def test_trend_score_low_adx_does_not_reinforce() -> None:
    """ADX < 25 means no trend reinforcement even if EMAs align."""
    strong_bull_no_adx = _build_trend_score(
        {"ema_20": 110, "ema_50": 105, "ema_200": 100, "adx_14": 20}
    )
    strong_bull_weak_trend = _build_trend_score(
        {"ema_20": 110, "ema_50": 105, "ema_200": 100, "adx_14": 30}
    )
    assert strong_bull_weak_trend[0] > strong_bull_no_adx[0]


def test_structure_score_uses_bias_score_when_present() -> None:
    bullish, bearish = _build_structure_score({"bias_score": 70.0})
    assert bullish == 70
    assert bearish == 30


def test_structure_score_falls_back_to_bias_label_bullish() -> None:
    bullish, bearish = _build_structure_score({"bias": "bullish"})
    assert bullish == 70
    assert bearish == 30


def test_structure_score_falls_back_to_bias_label_bearish() -> None:
    bullish, bearish = _build_structure_score({"overall_bias": "short"})
    assert bullish == 30
    assert bearish == 70


def test_structure_score_neutral_default() -> None:
    bullish, bearish = _build_structure_score({})
    assert bullish == 50
    assert bearish == 50


def test_regime_fit_trend_supports_both_sides() -> None:
    long, short, range_score = _build_regime_fit({"regime": "trend"}, "trend")
    assert long == 65
    assert short == 65
    assert range_score == 35


def test_regime_fit_balance_punishes_both_sides() -> None:
    long, short, range_score = _build_regime_fit({}, "balance")
    assert long == 35
    assert short == 35
    assert range_score == 80


def test_regime_fit_transition_neutral_with_range_bias() -> None:
    long, short, range_score = _build_regime_fit({}, "transition")
    assert long == 40
    assert short == 40
    assert range_score == 60


def test_regime_fit_unknown_defaults_to_neutral() -> None:
    long, short, range_score = _build_regime_fit({}, None)
    assert long == 50
    assert short == 50
    assert range_score == 50


def test_feature_components_do_not_emit_microstructure_scores() -> None:
    components = StrategySnapshotBuilder._feature_components(
        indicators={
            "ema_20": 110,
            "ema_20_prev": 108,
            "ema_50": 105,
            "ema_200": 100,
            "adx_14": 30,
        },
        structure_overall={"bias": "bullish"},
        regime="trend",
        direction_metrics={"bullish": 65.0, "bearish": 35.0},
        rsi=58.0,
        macd=1.4,
        macd_prev=0.9,
        adx=30.0,
    )
    removed_keys = {
        "bullish_flow",
        "bearish_flow",
        "flow_source",
        "derivatives_long_confirmation",
        "derivatives_short_confirmation",
    }
    assert not (removed_keys & set(components))
    assert components["mtf_trend_source"] == "ema+adx+vwap"
    assert components["structure_source"] == "structure_overall"
    assert components["momentum_source"] == "rsi+macd"


def test_feature_components_keep_momentum_independent_from_direction_score() -> None:
    base = {
        "indicators": {
            "ema_20": 100,
            "ema_20_prev": 99,
            "ema_50": 98,
            "ema_200": 95,
            "adx_14": 25,
        },
        "structure_overall": {"bias": "neutral"},
        "regime": "trend",
        "rsi": 62.0,
        "macd": 1.0,
        "macd_prev": 0.5,
        "adx": 25.0,
    }
    bullish_direction = StrategySnapshotBuilder._feature_components(
        **base,
        direction_metrics={"bullish": 90.0, "bearish": 10.0},
    )
    bearish_direction = StrategySnapshotBuilder._feature_components(
        **base,
        direction_metrics={"bullish": 10.0, "bearish": 90.0},
    )
    assert bullish_direction["bullish_momentum"] == bearish_direction["bullish_momentum"]
    assert bullish_direction["bearish_momentum"] == bearish_direction["bearish_momentum"]
    assert bullish_direction["direction_score_aggregate"] != bearish_direction[
        "direction_score_aggregate"
    ]


def test_independence_trend_does_not_drive_structure() -> None:
    """Changing trend inputs must not change structure output."""
    structure_baseline = _build_structure_score({"bias": "bullish"})
    # wild trend input
    _build_trend_score(
        {"ema_20": 200, "ema_50": 100, "ema_200": 50, "adx_14": 50}
    )
    structure_after = _build_structure_score({"bias": "bullish"})
    assert structure_baseline == structure_after


def test_independence_structure_does_not_drive_regime() -> None:
    regime_baseline = _build_regime_fit({"regime": "trend"}, "trend")
    _build_structure_score({"bias": "bearish", "bias_score": 20})
    regime_after = _build_regime_fit({"regime": "trend"}, "trend")
    assert regime_baseline == regime_after
