from __future__ import annotations

from app.services.strategy_signal.config_loader import DEFAULT_STRATEGY_SIGNAL_CONFIG
from app.services.strategy_signal.scoring_engine import DirectionScoringEngine
from app.services.strategy_signal.setup_lifecycle import (
    build_frozen_setup,
    evaluate_lower_tf_trigger,
    evaluate_setup_lifecycle,
    evaluate_strong_trend_follow,
    normalize_direction_metrics,
    normalize_plan_levels,
)
from app.services.strategy_signal.strategy_generator import StrategyGenerator


def test_short_setup_that_has_reached_tp1_is_not_waiting_for_confirmation():
    levels = normalize_plan_levels("short", 82000, 83500, 79800, 76000, 82000, 1000)
    setup = build_frozen_setup(
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        side="short",
        levels=levels,
        entry_mode="pullback_confirm",
        snapshot={"current_price": 82000},
    )

    lifecycle = evaluate_setup_lifecycle(
        setup,
        {"current_price": 78000, "atr_14": 1000},
        DEFAULT_STRATEGY_SIGNAL_CONFIG,
    )

    assert lifecycle["state"] in {"TP1_HIT", "MOVE_MISSED"}
    assert lifecycle["state"] != "WAIT_SHORT_CONFIRMATION"


def test_direction_score_normalization_supports_signed_and_legacy_scores():
    bearish = normalize_direction_metrics(-100, scale="signed")
    bullish = normalize_direction_metrics(80, scale="legacy_0_100")

    assert bearish["bearish"] == 100
    assert bearish["bullish"] == 0
    assert bullish["bullish"] == 80
    assert bullish["bearish"] == 20


def test_invalid_short_level_order_is_reported_without_repair():
    levels = normalize_plan_levels(
        "short",
        entry=82000,
        stop=81000,
        tp1=83000,
        tp2=84000,
        current_price=82000,
        atr=1000,
        allow_repair=False,
    )

    assert not levels["is_valid"]
    assert levels["invalid_reason"] == "short plan requires stop > entry > tp1 > tp2"


def test_lower_timeframe_missing_returns_wait_state_and_diagnostic():
    result = evaluate_lower_tf_trigger(
        "short",
        {"timeframe": "1d"},
        None,
        DEFAULT_STRATEGY_SIGNAL_CONFIG,
    )

    assert result["state"] == "WAIT_LOWER_TF_CONFIRMATION"
    assert result["missing"] is True
    assert result["diagnostics"][0]["code"] == "lower_tf_missing"


def test_strong_trend_far_from_trigger_waits_for_retest():
    snapshot = {
        "current_price": 78000,
        "atr_14": 1000,
        "adx_14": 35,
        "ema_20": 79000,
        "ema_50": 80500,
        "ema20_slope": -100,
        "bearish_momentum": 80,
        "bearish_flow": 70,
        "atr_expansion_score": 80,
        "short_entry": 82000,
        "breakout_down": True,
    }

    result = evaluate_strong_trend_follow("short", snapshot, DEFAULT_STRATEGY_SIGNAL_CONFIG)

    assert result["state"] == "WAIT_RETEST_AFTER_MISSED_MOVE"


def test_generator_marks_invalid_plan_levels():
    config = DEFAULT_STRATEGY_SIGNAL_CONFIG
    snapshot = {
        "current_price": 82000,
        "candle_completeness": 100,
        "candle_freshness": 100,
        "multi_timeframe_availability": 100,
        "derivatives_data_availability": 100,
        "orderbook_data_availability": 100,
        "macro_event_availability": 100,
        "mtf_trend_bullish": 0,
        "mtf_trend_bearish": 100,
        "bullish_structure": 0,
        "bearish_structure": 100,
        "bullish_momentum": 0,
        "bearish_momentum": 100,
        "bullish_flow": 0,
        "bearish_flow": 100,
        "derivatives_long_confirmation": 0,
        "derivatives_short_confirmation": 100,
        "execution_quality": 100,
        "regime_fit_long": 0,
        "regime_fit_short": 100,
        "range_structure": 0,
        "low_adx": 0,
        "low_volume_confirmation": 0,
        "event_risk_score": 0,
        "spread_bps": 0,
        "slippage_bps": 0,
        "depth_score": 100,
        "short_setup_ready": True,
        "short_trigger_ready": True,
        "short_entry": 82000,
        "short_stop": 81000,
        "short_tp1": 83000,
        "short_tp2": 84000,
        "atr_14": 1000,
    }
    scores = DirectionScoringEngine(config).compute(snapshot)
    decision = StrategyGenerator(config).build_decision(snapshot, scores)

    assert decision["strategy_state"] == "INVALID_PLAN_LEVELS"
    assert decision["primary_strategy"]["is_valid"] is False


def test_frozen_setup_keeps_entry_across_lifecycle_evaluations():
    levels = normalize_plan_levels("long", 100, 96, 108, 114, 100, 3)
    setup = build_frozen_setup(
        instrument_id="eth-usdt-perp",
        timeframe="4h",
        side="long",
        levels=levels,
        entry_mode="pullback_confirm",
        snapshot={"current_price": 100},
    )

    first = evaluate_setup_lifecycle(
        setup,
        {"current_price": 101, "atr_14": 3},
        DEFAULT_STRATEGY_SIGNAL_CONFIG,
    )
    second = evaluate_setup_lifecycle(
        setup,
        {"current_price": 102, "atr_14": 3},
        DEFAULT_STRATEGY_SIGNAL_CONFIG,
    )

    assert first["levels"]["entry"] == 100
    assert second["levels"]["entry"] == 100
