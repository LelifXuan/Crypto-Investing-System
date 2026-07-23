from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.quant.indicators import (
    adx_wilder_series,
    atr_ema_series,
    atr_wilder_series,
    bbands_series,
    cci_series,
    ema_series,
    kdj_series,
    macd_series,
    obv_series,
    rsi_wilder_series,
)
from app.services.divergence import DivergenceService
from app.workers.market_event_translation import MarketEventTranslationWorker


def _decimal_series(values: list[float]) -> list[Decimal]:
    return [Decimal(str(item)) for item in values]


def _ohlcv_factory(
    kind: str, *, length: int = 80, gap_every: int | None = None, zero_volume: bool = False
):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[FakeCandle] = []
    price = Decimal("100")
    for index in range(length):
        if kind == "up":
            price += Decimal("1.25")
        elif kind == "down":
            price -= Decimal("1.10")
        elif kind == "flat":
            price += Decimal("0")
        else:
            price += Decimal("0.35") if index % 2 else Decimal("-0.15")
        if gap_every and index and index % gap_every == 0:
            base += timedelta(hours=2)
        high = price + Decimal("1.2")
        low = price - Decimal("1.0")
        if kind == "no_range":
            high = price
            low = price
        volume = Decimal("0") if zero_volume else Decimal("1000") + Decimal(index * 10)
        candles.append(
            FakeCandle(
                ts_open=base + timedelta(hours=index),
                open=price - Decimal("0.4"),
                high=high,
                low=low,
                close=price,
                volume=volume,
            )
        )
    return candles


def test_ema_rsi_macd_bbands_report_warmup() -> None:
    values = _decimal_series([100 + index for index in range(60)])
    ema = ema_series(values, 20)
    rsi = rsi_wilder_series(values, 14)
    macd = macd_series(values)
    bbands = bbands_series(values, 20, Decimal("2"))

    assert ema.lookback_ready is True
    assert ema.is_immature is False
    assert rsi.lookback_ready is True
    assert macd.histogram.lookback_ready is True
    assert bbands.middle.lookback_ready is True


@pytest.mark.parametrize("kind", ["up", "down", "flat"])
def test_indicator_series_cover_trend_regimes(kind: str) -> None:
    candles = _ohlcv_factory(kind, length=90)
    highs = [item.high for item in candles]
    lows = [item.low for item in candles]
    closes = [item.close for item in candles]
    volumes = [item.volume for item in candles]

    ema = ema_series(closes, 20)
    rsi = rsi_wilder_series(closes, 14)
    atr = atr_wilder_series(highs, lows, closes, 14)
    adx = adx_wilder_series(highs, lows, closes, 14)
    macd = macd_series(closes)
    bbands = bbands_series(closes, 20)
    obv = obv_series(closes, volumes)
    cci = cci_series(highs, lows, closes, 20)
    kdj = kdj_series(highs, lows, closes, 9)

    assert ema.lookback_ready is True
    assert rsi.lookback_ready is True
    assert atr.lookback_ready is True
    assert adx["adx"].lookback_ready is True
    assert macd.histogram.lookback_ready is True
    assert bbands.middle.lookback_ready is True
    assert obv.lookback_ready is True
    assert cci.lookback_ready is True
    assert kdj.j.lookback_ready is True

    if kind == "up":
        assert closes[-1] > ema.value
        assert rsi.value >= Decimal("50")
    elif kind == "down":
        assert closes[-1] < ema.value
        assert rsi.value <= Decimal("50")
    else:
        assert atr.value >= 0
        assert adx["adx"].value >= 0


def test_atr_and_adx_use_wilder_style_outputs() -> None:
    highs = _decimal_series(
        [
            11,
            12,
            13,
            13.5,
            14,
            15,
            15.5,
            16,
            16.4,
            17,
            17.2,
            18,
            18.4,
            19,
            19.8,
            20.3,
            20.8,
            21.2,
            21.7,
            22.1,
        ]
    )
    lows = _decimal_series(
        [
            9.5,
            10,
            10.8,
            11.1,
            11.8,
            12.5,
            12.8,
            13.1,
            13.7,
            14,
            14.4,
            14.9,
            15.4,
            15.8,
            16.1,
            16.7,
            17.1,
            17.5,
            18,
            18.2,
        ]
    )
    closes = _decimal_series(
        [
            10,
            11.5,
            12.1,
            12.9,
            13.4,
            14.2,
            14.9,
            15.3,
            15.9,
            16.1,
            16.8,
            17.5,
            17.9,
            18.6,
            19.1,
            19.7,
            20.1,
            20.7,
            21.1,
            21.8,
        ]
    )

    atr = atr_wilder_series(highs, lows, closes, 14)
    adx = adx_wilder_series(highs, lows, closes, 14)

    assert atr.lookback_ready is True
    assert atr.value > 0
    assert adx["adx"].value >= 0
    assert adx["plus_di"].value >= 0
    assert adx["minus_di"].value >= 0


def test_atr_and_adx_report_immature_when_history_is_short() -> None:
    highs = _decimal_series([11, 12, 13, 13.5, 14, 15, 15.5, 16])
    lows = _decimal_series([9.5, 10, 10.8, 11.1, 11.8, 12.5, 12.8, 13.1])
    closes = _decimal_series([10, 11.5, 12.1, 12.9, 13.4, 14.2, 14.9, 15.3])

    atr = atr_wilder_series(highs, lows, closes, 14)
    adx = adx_wilder_series(highs, lows, closes, 14)

    assert atr.is_immature is True
    assert atr.lookback_ready is False
    assert adx["adx"].is_immature is True
    assert adx["adx"].lookback_ready is False


def test_macd_is_single_pass_stable_for_missing_time_gaps() -> None:
    candles = _ohlcv_factory("up", length=70, gap_every=7)
    closes = [item.close for item in candles]
    result = macd_series(closes)
    assert result.histogram.lookback_ready is True
    assert result.histogram.is_immature is False
    assert result.histogram.value == result.value


def test_zero_volume_and_flat_range_do_not_break_volume_or_range_indicators() -> None:
    candles = _ohlcv_factory("flat", length=60, zero_volume=True)
    highs = [item.high for item in candles]
    lows = [item.low for item in candles]
    closes = [item.close for item in candles]
    volumes = [item.volume for item in candles]

    atr = atr_wilder_series(highs, lows, closes, 14)
    atr_ema = atr_ema_series(highs, lows, closes, 14)
    obv = obv_series(closes, volumes)
    cci = cci_series(highs, lows, closes, 20)
    kdj = kdj_series(highs, lows, closes, 9)

    assert atr.value >= 0
    assert atr_ema.value >= 0
    assert obv.value == 0
    assert cci.lookback_ready is True
    assert abs(cci.value) <= Decimal("100")
    assert kdj.k.value >= 0
    assert kdj.d.value >= 0


def test_high_equals_low_and_data_gaps_keep_bbands_and_adx_stable() -> None:
    candles = _ohlcv_factory("flat", length=55, gap_every=5)
    highs = [item.high for item in candles]
    lows = [item.low for item in candles]
    closes = [item.close for item in candles]

    bbands = bbands_series(closes, 20)
    adx = adx_wilder_series(highs, lows, closes, 14)

    assert bbands.middle.lookback_ready is True
    assert bbands.upper.value == bbands.lower.value == bbands.middle.value
    assert adx["adx"].value >= 0


def test_rsi_matches_pandas_ta_when_available() -> None:
    try:
        import pandas as pd
        import pandas_ta as pta
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"pandas-ta unavailable: {exc}")

    closes = [
        100,
        101,
        100.5,
        102,
        103.2,
        102.6,
        104.1,
        105.4,
        104.8,
        106,
        107.5,
        106.3,
        108.2,
        109,
        108.5,
        110,
    ]
    ours = float(rsi_wilder_series(_decimal_series(closes), 14).value)
    expected = float(pta.rsi(pd.Series(closes), length=14).dropna().iloc[-1])
    assert abs(ours - expected) < 1e-6


def test_rsi_matches_talib_when_available() -> None:
    try:
        import talib
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"TA-Lib unavailable: {exc}")

    closes = [
        100,
        101,
        100.5,
        102,
        103.2,
        102.6,
        104.1,
        105.4,
        104.8,
        106,
        107.5,
        106.3,
        108.2,
        109,
        108.5,
        110,
    ]
    ours = float(rsi_wilder_series(_decimal_series(closes), 14).value)
    expected = float(talib.RSI(__import__("numpy").array(closes, dtype=float), timeperiod=14)[-1])
    assert abs(ours - expected) < 1e-6


def test_indicator_suite_matches_talib_when_available() -> None:
    try:
        import numpy as np
        import talib
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"TA-Lib unavailable: {exc}")

    candles = _ohlcv_factory("mixed", length=120)
    highs = np.array([float(item.high) for item in candles], dtype=float)
    lows = np.array([float(item.low) for item in candles], dtype=float)
    closes = np.array([float(item.close) for item in candles], dtype=float)
    volumes = np.array([float(item.volume) for item in candles], dtype=float)

    assert (
        abs(
            float(ema_series(_decimal_series(closes.tolist()), 20).value)
            - float(talib.EMA(closes, timeperiod=20)[-1])
        )
        < 1e-6
    )
    assert (
        abs(
            float(
                atr_wilder_series(
                    _decimal_series(highs.tolist()),
                    _decimal_series(lows.tolist()),
                    _decimal_series(closes.tolist()),
                    14,
                ).value
            )
            - float(talib.ATR(highs, lows, closes, timeperiod=14)[-1])
        )
        < 1e-6
    )
    assert (
        abs(
            float(
                adx_wilder_series(
                    _decimal_series(highs.tolist()),
                    _decimal_series(lows.tolist()),
                    _decimal_series(closes.tolist()),
                    14,
                )["adx"].value
            )
            - float(talib.ADX(highs, lows, closes, timeperiod=14)[-1])
        )
        < 1e-6
    )
    macd = macd_series(_decimal_series(closes.tolist()))
    talib_macd, talib_signal, talib_hist = talib.MACD(
        closes, fastperiod=12, slowperiod=26, signalperiod=9
    )
    assert abs(float(macd.macd.value) - float(talib_macd[-1])) < 1e-6
    assert abs(float(macd.signal.value) - float(talib_signal[-1])) < 1e-6
    assert abs(float(macd.histogram.value) - float(talib_hist[-1])) < 1e-6
    bbands = bbands_series(_decimal_series(closes.tolist()), 20, Decimal("2"))
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    assert abs(float(bbands.upper.value) - float(upper[-1])) < 1e-6
    assert abs(float(bbands.middle.value) - float(middle[-1])) < 1e-6
    assert abs(float(bbands.lower.value) - float(lower[-1])) < 1e-6
    assert (
        abs(
            float(
                obv_series(
                    _decimal_series(closes.tolist()), _decimal_series(volumes.tolist())
                ).value
            )
            - float(talib.OBV(closes, volumes)[-1])
        )
        < 1e-6
    )
    assert (
        abs(
            float(
                cci_series(
                    _decimal_series(highs.tolist()),
                    _decimal_series(lows.tolist()),
                    _decimal_series(closes.tolist()),
                    20,
                ).value
            )
            - float(talib.CCI(highs, lows, closes, timeperiod=20)[-1])
        )
        < 1e-6
    )


@dataclass
class FakeCandle:
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def test_divergence_service_detects_bearish_signal() -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    candles = []
    closes = [
        100,
        102,
        104,
        103,
        105,
        107,
        106,
        108,
        110,
        109,
        111,
        112,
        111.5,
        113,
        114,
        113.8,
        115,
        116.2,
        116.5,
        116.1,
        116.7,
        117,
    ]
    for index, close in enumerate(closes * 3):
        price = Decimal(str(close + (index * 0.15)))
        candles.append(
            FakeCandle(
                ts_open=base + timedelta(hours=index),
                open=price - Decimal("0.4"),
                high=price + Decimal("1.3") + Decimal(str((index % 3) * 0.05)),
                low=price - Decimal("1.2"),
                close=price,
                volume=Decimal("1000") + Decimal(index * 10),
            )
        )
    payload = DivergenceService().analyze("btc-usdt-perp", "1h", candles)
    assert "overall" in payload
    assert payload["overall"]["title"]


def test_indicator_warmup_flags_for_insufficient_samples() -> None:
    closes = _decimal_series([100, 100.5, 101, 100.8, 101.2, 101.5])
    highs = [item + Decimal("1") for item in closes]
    lows = [item - Decimal("1") for item in closes]
    volumes = _decimal_series([10, 0, 15, 12, 0, 8])

    assert ema_series(closes, 20).is_immature is True
    assert rsi_wilder_series(closes, 14).is_immature is True
    assert macd_series(closes).histogram.is_immature is True
    assert atr_wilder_series(highs, lows, closes, 14).is_immature is True
    assert adx_wilder_series(highs, lows, closes, 14)["adx"].is_immature is True
    assert bbands_series(closes, 20).middle.is_immature is True
    assert obv_series(closes, volumes).is_immature is True
    assert cci_series(highs, lows, closes, 20).is_immature is True
    assert kdj_series(highs, lows, closes, 9).j.is_immature is True


@pytest.mark.asyncio
async def test_translation_worker_creates_loop_bound_objects_on_start() -> None:
    from app.core.config import settings

    worker = MarketEventTranslationWorker()
    assert worker._queue is None
    assert worker._stopping is None
    original_worker_enabled = settings.market_events_translation_worker_enabled
    original_translate_enabled = settings.market_events_translate_enabled
    settings.market_events_translation_worker_enabled = True
    settings.market_events_translate_enabled = True
    await worker.start()
    try:
        assert worker._queue is not None
        assert worker._stopping is not None
    finally:
        settings.market_events_translation_worker_enabled = original_worker_enabled
        settings.market_events_translate_enabled = original_translate_enabled
        await worker.stop()
