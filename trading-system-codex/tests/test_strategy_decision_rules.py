from __future__ import annotations

from app.services.strategy_signal.config_loader import DEFAULT_STRATEGY_SIGNAL_CONFIG
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
        "derivatives_data_availability": 80,
        "orderbook_data_availability": 80,
        "macro_event_availability": 80,
        "mtf_trend_bullish": 82,
        "bullish_structure": 80,
        "bullish_momentum": 76,
        "bullish_flow": 75,
        "derivatives_long_confirmation": 70,
        "execution_quality": 78,
        "regime_fit_long": 78,
        "mtf_trend_bearish": 25,
        "bearish_structure": 22,
        "bearish_momentum": 30,
        "bearish_flow": 28,
        "derivatives_short_confirmation": 30,
        "regime_fit_short": 24,
        "range_structure": 25,
        "low_adx": 15,
        "low_volume_confirmation": 35,
        "funding_crowding_score": 20,
        "oi_price_divergence_score": 10,
        "cvd_divergence_score": 10,
        "late_entry_risk_score": 20,
        "event_risk_score": 20,
        "conflict_score": 10,
        "spread_bps": 5,
        "slippage_bps": 8,
        "depth_score": 80,
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
    config = DEFAULT_STRATEGY_SIGNAL_CONFIG
    scores = DirectionScoringEngine(config).compute(snapshot)
    return StrategyGenerator(config).build_decision(snapshot, scores)


def test_v16_generates_market_long_signal_without_position_context():
    decision = _decision(_snapshot())

    assert decision["strategy_bias"] == "long"
    assert decision["strategy_state"] in {"WAIT_LONG_CONFIRMATION", "LONG_TRIGGERED"}
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
        bullish_momentum=25,
        bullish_flow=22,
        derivatives_long_confirmation=25,
        regime_fit_long=20,
        mtf_trend_bearish=84,
        bearish_structure=82,
        bearish_momentum=78,
        bearish_flow=76,
        derivatives_short_confirmation=74,
        regime_fit_short=80,
        long_setup_ready=False,
        long_trigger_ready=False,
        short_setup_ready=True,
        short_trigger_ready=True,
    )

    decision = _decision(snapshot)

    assert decision["strategy_bias"] == "short"
    assert decision["strategy_state"] in {"WAIT_SHORT_CONFIRMATION", "SHORT_TRIGGERED"}
    assert decision["short_score"] > decision["long_score"]
    assert decision["primary_strategy"]["direction"] == "short"


def test_v16_triggered_state_requires_ready_trigger_and_rr():
    snapshot = _snapshot(
        mtf_trend_bullish=100,
        bullish_structure=100,
        bullish_momentum=100,
        bullish_flow=100,
        derivatives_long_confirmation=100,
        execution_quality=100,
        regime_fit_long=100,
        mtf_trend_bearish=0,
        bearish_structure=0,
        bearish_momentum=0,
        bearish_flow=0,
        derivatives_short_confirmation=0,
        regime_fit_short=0,
        long_setup_ready=True,
        long_trigger_ready=True,
        long_entry=100,
        long_stop=96,
        long_tp1=112,
    )

    decision = _decision(snapshot)

    assert decision["strategy_state"] == "LONG_TRIGGERED"


def test_v16_blocks_high_conflict_market():
    snapshot = _snapshot(
        mtf_trend_bullish=82,
        bullish_structure=82,
        bullish_momentum=80,
        bullish_flow=78,
        derivatives_long_confirmation=74,
        regime_fit_long=78,
        mtf_trend_bearish=80,
        bearish_structure=80,
        bearish_momentum=78,
        bearish_flow=76,
        derivatives_short_confirmation=74,
        regime_fit_short=78,
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
            derivatives_data_availability=20,
            orderbook_data_availability=20,
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
