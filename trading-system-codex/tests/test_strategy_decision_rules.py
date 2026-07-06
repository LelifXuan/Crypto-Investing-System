from __future__ import annotations

from app.services.strategy_signal.config_loader import load_strategy_signal_config
from app.services.strategy_signal.scoring_engine import DirectionScoringEngine
from app.services.strategy_signal.strategy_generator import StrategyGenerator


def _snapshot(**overrides):
    base = {
        "instrument_id": "eth-usdt-perp",
        "symbol": "eth-usdt-perp",
        "timeframe": "4h",
        "current_price": "100",
        "candle_completeness": 95,
        "candle_freshness": 90,
        "multi_timeframe_availability": 90,
        "technical_risk_availability": 80,
        "macro_event_availability": 80,
        "mtf_trend_bullish": 82,
        "bullish_structure": 80,
        "momentum_short": 76,
        "momentum_mid": 76,
        "momentum_long": 76,
        "long_risk_reward": 80.0,
        "execution_quality": 78,
        "regime_fit_long": 78,
        "mtf_trend_bearish": 25,
        "bearish_structure": 22,
        "momentum_short_bearish": 30,
        "momentum_mid_bearish": 30,
        "momentum_long_bearish": 30,
        "short_risk_reward": 80.0,
        "regime_fit_short": 24,
        "range_structure": 25,
        "low_adx": 15,
        "low_volume_confirmation": 35,
        "funding_pressure_long": 50.0,
        "funding_pressure_short": 50.0,
        "funding_crowding_score": 20,
        "opposite_divergence_risk_score": 10,
        "late_entry_risk_score": 20,
        "event_risk_score": 20,
        "conflict_score": 10,
        "long_setup_ready": True,
        "long_trigger_ready": True,
        "short_setup_ready": False,
        "short_trigger_ready": False,
        "long_entry": 100,
        "long_stop": 96,
        "long_tp1": 108,
        "long_tp2": 114,
        "short_entry": 100,
        "short_stop": 104,
        "short_tp1": 94,
        "short_tp2": 90,
        "atr_14": 3,
    }
    base.update(overrides)
    return base


def _decision(snapshot):
    config = load_strategy_signal_config()
    scores = DirectionScoringEngine(config).compute(snapshot)
    return StrategyGenerator(config).build_decision(snapshot, scores)


def test_v16_generates_market_long_signal_without_position_context():
    decision = _decision(_snapshot())

    assert decision["strategy_bias"] == "long"
    # V1.7.4: weights no longer include volume_proxy_confirmation / divergence_support_long;
    # the rescaled long_score lands in [bias_score, setup_score) under these fixtures, so
    # the strategy may settle in LONG_BIAS before lower-TF confirmation arrives.
    assert decision["strategy_state"] in {
        "LONG_BIAS",
        "WAIT_LONG_CONFIRMATION",
        "WAIT_LOWER_TF_CONFIRMATION",
        "LONG_TRIGGERED",
    }
    assert decision["long_score"] > decision["short_score"]
    assert decision["primary_strategy"]["direction"] == "long"
    assert decision["primary_strategy"]["entry_price"] is not None
    assert decision["primary_strategy"]["stop_price"] is not None
    assert decision["primary_strategy"]["take_profit_1"] is not None
    assert decision["primary_strategy"]["risk_reward_ratio"] is not None
    assert "ADD_LONG" not in str(decision)
    assert "CLOSE_LONG" not in str(decision)


def test_v16_generates_short_signal_when_market_evidence_is_bearish():
    snapshot = _snapshot(
        mtf_trend_bullish=20,
        bullish_structure=24,
        momentum_short=25,
        momentum_mid=25,
        momentum_long=25,
        regime_fit_long=20,
        mtf_trend_bearish=84,
        bearish_structure=82,
        momentum_short_bearish=78,
        momentum_mid_bearish=78,
        momentum_long_bearish=78,
        regime_fit_short=80,
        long_setup_ready=False,
        long_trigger_ready=False,
        short_setup_ready=True,
        short_trigger_ready=True,
    )

    decision = _decision(snapshot)

    assert decision["strategy_bias"] == "short"
    # V1.7.4: drop in the 20% contribution from the removed sub-scores means the
    # rescaled short_score may sit in [bias_score, setup_score) before confirmation.
    assert decision["strategy_state"] in {
        "SHORT_BIAS",
        "WAIT_SHORT_CONFIRMATION",
        "WAIT_LOWER_TF_CONFIRMATION",
        "SHORT_TRIGGERED",
    }
    assert decision["short_score"] > decision["long_score"]
    assert decision["primary_strategy"]["direction"] == "short"


def test_v16_triggered_state_requires_ready_trigger_and_rr():
    snapshot = _snapshot(
        mtf_trend_bullish=100,
        bullish_structure=100,
        momentum_short=100,
        momentum_mid=100,
        momentum_long=100,
        execution_quality=100,
        regime_fit_long=100,
        mtf_trend_bearish=0,
        bearish_structure=0,
        momentum_short_bearish=0,
        momentum_mid_bearish=0,
        momentum_long_bearish=0,
        regime_fit_short=0,
        long_setup_ready=True,
        long_trigger_ready=True,
        long_entry=100,
        long_stop=96,
        long_tp1=112,
    )

    decision = _decision(snapshot)

    assert decision["strategy_state"] == "LONG_TRIGGERED"


def test_trigger_state_uses_ev_score():
    """Trigger condition now uses ev_score (p_win * rr * 100) instead of just rr threshold.

    With V1.7.5 the trigger fires only when ev_score = setup_probability * rr * 100
    is >= ev_threshold (65). A low setup_probability must suppress the trigger
    even when rr alone is high enough to clear the old min_rr_trade gate.
    """
    # rr = (103 - 100) / (100 - 98) = 1.5 (just at min_rr_trade); old code would
    # accept this. With setup_probability=0.4, ev_score = 0.4 * 1.5 * 100 = 60
    # which is below ev_threshold=65, so the new trigger must NOT fire.
    snapshot = _snapshot(
        mtf_trend_bullish=100,
        bullish_structure=100,
        momentum_short=100,
        momentum_mid=100,
        momentum_long=100,
        execution_quality=100,
        regime_fit_long=100,
        mtf_trend_bearish=0,
        bearish_structure=0,
        momentum_short_bearish=0,
        momentum_mid_bearish=0,
        momentum_long_bearish=0,
        regime_fit_short=0,
        long_setup_ready=True,
        long_trigger_ready=True,
        long_entry=100,
        long_stop=98,
        long_tp1=103,
        long_tp2=106,
        setup_probability=0.4,
    )

    decision = _decision(snapshot)

    assert decision["strategy_state"] != "LONG_TRIGGERED"


def test_v16_blocks_high_conflict_market():
    # V1.7.4: weights no longer include volume_proxy_confirmation / divergence_support_*.
    # The conflict threshold (conflict_both_high=65) requires both sides to climb
    # slightly higher under the rescaled flat weights, so we boost the directional
    # sub-scores vs the V1.6 fixture while keeping the conflict geometry.
    snapshot = _snapshot(
        mtf_trend_bullish=90,
        bullish_structure=90,
        momentum_short=88,
        momentum_mid=88,
        momentum_long=88,
        regime_fit_long=85,
        execution_quality=90,
        mtf_trend_bearish=90,
        bearish_structure=90,
        momentum_short_bearish=88,
        momentum_mid_bearish=88,
        momentum_long_bearish=88,
        regime_fit_short=85,
        long_setup_ready=True,
        short_setup_ready=True,
    )

    decision = _decision(snapshot)

    assert decision["strategy_state"] == "CONFLICTED_NO_TRADE"
    assert decision["strategy_permission"] == "observe_only"
    assert decision["conflict_reasons"]


def test_v16_low_data_quality_degrades_to_no_edge():
    decision = _decision(
        _snapshot(
            candle_completeness=20,
            candle_freshness=20,
            multi_timeframe_availability=20,
            technical_risk_availability=20,
            macro_event_availability=20,
        )
    )

    assert decision["strategy_state"] == "NO_EDGE"
    assert decision["strategy_permission"] == "observe_only"
    assert "数据质量" in "".join(decision["no_trade_reasons"])


def test_v16_event_risk_waits_instead_of_triggering():
    decision = _decision(_snapshot(event_risk_score=85))

    assert decision["strategy_state"] == "EVENT_WAIT"
    assert decision["strategy_permission"] == "observe_only"
