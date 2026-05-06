from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.divergence import DivergenceService, Pivot


class Candle:
    def __init__(
        self, ts_open: datetime, high: float, low: float, close: float, volume: float = 1000
    ) -> None:
        self.ts_open = ts_open
        self.open = Decimal(str(close))
        self.high = Decimal(str(high))
        self.low = Decimal(str(low))
        self.close = Decimal(str(close))
        self.volume = Decimal(str(volume))


def _candles(length: int = 60) -> list[Candle]:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(length):
        price = 100 + index * 0.5
        candles.append(
            Candle(base + timedelta(hours=index), high=price + 2, low=price - 2, close=price)
        )
    return candles


def _series_with_pivots(
    length: int, left_index: int, left_value: float, right_index: int, right_value: float
) -> list[Decimal | None]:
    series = [Decimal("50") for _ in range(length)]
    for index in range(length):
        series[index] = Decimal(str(50 + (index % 3)))
    series[left_index - 2 : left_index + 3] = [
        Decimal("48"),
        Decimal("49"),
        Decimal(str(left_value)),
        Decimal("49"),
        Decimal("48"),
    ]
    series[right_index - 2 : right_index + 3] = [
        Decimal("48"),
        Decimal("49"),
        Decimal(str(right_value)),
        Decimal("49"),
        Decimal("48"),
    ]
    return series


def test_detects_regular_bearish_divergence_from_high_pivots() -> None:
    service = DivergenceService()
    candles = _candles()
    price_highs = [
        Pivot(18, candles[18].ts_open, 120, "high"),
        Pivot(34, candles[34].ts_open, 128, "high"),
    ]
    price_lows: list[Pivot] = []
    series = _series_with_pivots(len(candles), 18, 80, 34, 70)

    signals = service._detect_for_indicator(
        "RSI", series, candles, price_highs, price_lows, "1h", "uptrend"
    )

    assert signals
    assert signals[0]["type"] == "regular_bearish"
    assert signals[0]["direction"] == "bearish"
    assert signals[0]["signal_kind"] == "warning"
    assert signals[0]["entry_signal"] is False


def test_detects_regular_bullish_divergence_from_low_pivots() -> None:
    service = DivergenceService()
    candles = _candles()
    price_highs: list[Pivot] = []
    price_lows = [
        Pivot(20, candles[20].ts_open, 95, "low"),
        Pivot(40, candles[40].ts_open, 90, "low"),
    ]
    series = _series_with_pivots(len(candles), 20, 20, 40, 35)

    signals = service._detect_for_indicator(
        "MACD", series, candles, price_highs, price_lows, "4h", "downtrend"
    )

    assert signals
    assert signals[0]["type"] == "regular_bullish"
    assert signals[0]["cooldown"] == service.COOLDOWN_BY_TIMEFRAME["4h"]
    assert "MACD:regular_bullish:4h" in signals[0]["dedupe_key"]


def test_detects_hidden_bullish_and_hidden_bearish_divergence() -> None:
    service = DivergenceService()
    candles = _candles()

    hidden_bull = service._detect_for_indicator(
        "CCI",
        _series_with_pivots(len(candles), 18, 40, 38, 20),
        candles,
        [],
        [Pivot(18, candles[18].ts_open, 90, "low"), Pivot(38, candles[38].ts_open, 94, "low")],
        "1d",
        "uptrend",
    )
    hidden_bear = service._detect_for_indicator(
        "KDJ",
        _series_with_pivots(len(candles), 20, 70, 42, 90),
        candles,
        [Pivot(20, candles[20].ts_open, 118, "high"), Pivot(42, candles[42].ts_open, 112, "high")],
        [],
        "1d",
        "downtrend",
    )

    assert hidden_bull and hidden_bull[0]["type"] == "hidden_bullish"
    assert hidden_bear and hidden_bear[0]["type"] == "hidden_bearish"


def test_overall_result_stays_warning_only_and_has_confirmation_fields() -> None:
    service = DivergenceService()
    candles = _candles(80)
    payload = service.analyze("btc-usdt-perp", "1h", candles)

    assert payload["overall"]["signal_kind"] == "warning"
    assert payload["overall"]["entry_signal"] is False
    if payload["signals"]:
        signal = payload["signals"][0]
        assert signal["confirmation"]
        assert signal["invalidation"]
        assert signal["trend_context"] in {"uptrend", "downtrend", "sideways"}
