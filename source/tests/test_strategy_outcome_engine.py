from __future__ import annotations

import asyncio
from datetime import timezone
from decimal import Decimal
from types import SimpleNamespace

UTC = timezone.utc


def _make_candle(close, high=None, low=None, ts_open=None):
    return SimpleNamespace(
        close=close, high=high or close, low=low or close,
        ts_open=ts_open or None,
    )


def _make_signal(signal_key="test-key", direction="long", entry=100, stop=95, tp1=110,
                 tp2=120, metadata=None):
    return SimpleNamespace(
        signal_key=signal_key, signal_type="market_strategy_signal",
        recommendation_id=None,
        instrument_id="btc-usdt-perp", timeframe="1d",
        signal_ts=SimpleNamespace(), direction=direction,
        signal_state="LONG_TRIGGERED",
        confidence_score=Decimal("70"),
        risk_reward_ratio=Decimal("2.0"),
        entry_price=Decimal(str(entry)),
        stop_loss_price=Decimal(str(stop)),
        take_profit_price=Decimal(str(tp1)),
        metadata_json=metadata or {},
    )


class TestOutcomeBuild:
    def test_long_tp1_hit(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="long", entry=100, stop=95, tp1=110)
        candles = [
            _make_candle(102, 103, 101),
            _make_candle(105, 112, 104),
            _make_candle(108, 109, 106),
        ]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.outcome_status == "tp1_hit"
        assert result.take_profit_hit_first is True
        assert result.stop_hit_first is not True
        assert result.mfe is not None and float(result.mfe) > 0
        assert result.mae is not None

    def test_short_stop_hit(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="short", entry=100, stop=105, tp1=90)
        candles = [
            _make_candle(101, 102, 100),
            _make_candle(103, 106, 101),
            _make_candle(104, 105, 102),
        ]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.outcome_status == "stop_hit"
        assert result.stop_hit_first is True
        assert result.take_profit_hit_first is not True

    def test_ambiguous_same_bar(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="long", entry=100, stop=95, tp1=110)
        candles = [
            _make_candle(108, 112, 94),  # same bar hits both TP (>110) and SL (<95)
        ]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.outcome_status == "active"
        assert result.payload_json.get("hit_order") == "ambiguous_same_bar"

    def test_insufficient_data(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="long", entry=100, stop=95, tp1=110)
        candles = [_make_candle(101)]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.outcome_status in ("active", "insufficient_data")

    def test_neutral_skipped(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = SimpleNamespace(
            signal_key="test", signal_type="market_strategy_signal",
            instrument_id="btc-usdt-perp", timeframe="1d",
            direction="neutral",
            entry_price=None, stop_loss_price=None, take_profit_price=None,
            signal_ts=None, recommendation_id=None, metadata_json={},
        )
        engine = StrategyOutcomeEngine(None)
        result = asyncio.run(engine.build_outcome_for_signal(signal))
        assert result is None

    def test_direction_return_long(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="long", entry=100, stop=95, tp1=110)
        candles = [_make_candle(102), _make_candle(105), _make_candle(108)]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.return_1 is not None and float(result.return_1) > 0
        assert result.return_3 is not None and float(result.return_3) > 0

    def test_direction_return_short(self):
        from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

        signal = _make_signal(direction="short", entry=100, stop=105, tp1=90)
        candles = [_make_candle(98), _make_candle(95), _make_candle(92)]
        engine = object.__new__(StrategyOutcomeEngine)
        result = engine._build_full_outcome(signal, candles, entry=100, windows=[1, 3, 6])
        assert result.return_1 is not None and float(result.return_1) > 0
