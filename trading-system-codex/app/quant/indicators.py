from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Sequence

from app.core.decimal_utils import DECIMAL_ZERO


def _to_decimal(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_sqrt(value: Decimal) -> Decimal:
    return Decimal(str(sqrt(float(value)))) if value > 0 else DECIMAL_ZERO


@dataclass(slots=True)
class IndicatorSeriesResult:
    series: list[Decimal | None]
    warmup: int
    lookback_ready: bool
    is_immature: bool

    @property
    def value(self) -> Decimal:
        for item in reversed(self.series):
            if item is not None:
                return item
        return DECIMAL_ZERO


@dataclass(slots=True)
class MACDSeriesResult:
    macd: IndicatorSeriesResult
    signal: IndicatorSeriesResult
    histogram: IndicatorSeriesResult

    @property
    def value(self) -> Decimal:
        return self.histogram.value


@dataclass(slots=True)
class BBandsSeriesResult:
    middle: IndicatorSeriesResult
    upper: IndicatorSeriesResult
    lower: IndicatorSeriesResult
    bandwidth: IndicatorSeriesResult
    percent_b: IndicatorSeriesResult


@dataclass(slots=True)
class KDJSeriesResult:
    k: IndicatorSeriesResult
    d: IndicatorSeriesResult
    j: IndicatorSeriesResult


def _seed_average(values: Sequence[Decimal], window: int) -> Decimal | None:
    if len(values) < window or window <= 0:
        return None
    return sum(values[:window], DECIMAL_ZERO) / Decimal(window)


def _lookback_status(length: int, ready_at: int, warmup: int) -> tuple[bool, bool]:
    if length <= 0:
        return False, True
    ready = length >= ready_at
    mature = length >= ready_at + warmup
    return ready, not mature


def sma_series(values: Sequence[Decimal | float | int], window: int) -> IndicatorSeriesResult:
    prices = [_to_decimal(item) for item in values]
    series: list[Decimal | None] = []
    for index in range(len(prices)):
        if index + 1 < window:
            series.append(None)
            continue
        chunk = prices[index - window + 1 : index + 1]
        series.append(sum(chunk, DECIMAL_ZERO) / Decimal(window))
    ready, immature = _lookback_status(len(prices), window, max(2, window // 3))
    return IndicatorSeriesResult(
        series=series, warmup=max(2, window // 3), lookback_ready=ready, is_immature=immature
    )


def ema_series(values: Sequence[Decimal | float | int], window: int) -> IndicatorSeriesResult:
    prices = [_to_decimal(item) for item in values]
    series: list[Decimal | None] = []
    if not prices:
        return IndicatorSeriesResult(
            series=[], warmup=max(2, window // 2), lookback_ready=False, is_immature=True
        )
    multiplier = Decimal("2") / (Decimal(window) + Decimal("1"))
    ema_value = prices[0]
    for price in prices:
        ema_value = price if not series else ((price - ema_value) * multiplier) + ema_value
        series.append(ema_value)
    ready, immature = _lookback_status(len(prices), window, max(2, window // 2))
    return IndicatorSeriesResult(
        series=series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
    )


def vwap_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    volumes: Sequence[Decimal | float | int],
    window: int = 50,
) -> IndicatorSeriesResult:
    high_values = [_to_decimal(item) for item in highs]
    low_values = [_to_decimal(item) for item in lows]
    close_values = [_to_decimal(item) for item in closes]
    volume_values = [_to_decimal(item) for item in volumes]
    length = min(len(high_values), len(low_values), len(close_values), len(volume_values))
    typical = [
        (high_values[index] + low_values[index] + close_values[index]) / Decimal("3")
        for index in range(length)
    ]
    series: list[Decimal | None] = []
    for index in range(length):
        if index + 1 < window:
            series.append(None)
            continue
        start = index - window + 1
        volume_window = volume_values[start : index + 1]
        volume_sum = sum(volume_window, DECIMAL_ZERO)
        if volume_sum == 0:
            series.append(None)
            continue
        pv_sum = sum(
            typical[item_index] * volume_values[item_index]
            for item_index in range(start, index + 1)
        )
        series.append(pv_sum / volume_sum)
    ready, immature = _lookback_status(length, window, max(2, window // 3))
    return IndicatorSeriesResult(
        series=series,
        warmup=max(2, window // 3),
        lookback_ready=ready,
        is_immature=immature,
    )


def rsi_wilder_series(
    values: Sequence[Decimal | float | int], window: int = 14
) -> IndicatorSeriesResult:
    prices = [_to_decimal(item) for item in values]
    if len(prices) < 2:
        return IndicatorSeriesResult(
            series=[None for _ in prices], warmup=window, lookback_ready=False, is_immature=True
        )
    deltas = [prices[idx] - prices[idx - 1] for idx in range(1, len(prices))]
    gains = [max(delta, DECIMAL_ZERO) for delta in deltas]
    losses = [abs(min(delta, DECIMAL_ZERO)) for delta in deltas]
    avg_gain = _seed_average(gains, window)
    avg_loss = _seed_average(losses, window)
    series: list[Decimal | None] = [None]
    for index in range(len(deltas)):
        if index + 1 < window:
            series.append(None)
            continue
        if index + 1 == window:
            current_gain = avg_gain or DECIMAL_ZERO
            current_loss = avg_loss or DECIMAL_ZERO
        else:
            current_gain = ((current_gain * Decimal(window - 1)) + gains[index]) / Decimal(window)
            current_loss = ((current_loss * Decimal(window - 1)) + losses[index]) / Decimal(window)
        if current_loss == 0:
            series.append(Decimal("100"))
        else:
            rs = current_gain / current_loss
            series.append(Decimal("100") - (Decimal("100") / (Decimal("1") + rs)))
    ready, immature = _lookback_status(len(prices), window + 1, window)
    return IndicatorSeriesResult(
        series=series, warmup=window, lookback_ready=ready, is_immature=immature
    )


def true_range_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
) -> list[Decimal]:
    high_values = [_to_decimal(item) for item in highs]
    low_values = [_to_decimal(item) for item in lows]
    close_values = [_to_decimal(item) for item in closes]
    if not high_values or not low_values or not close_values:
        return []
    series: list[Decimal] = [high_values[0] - low_values[0]]
    for index in range(1, len(close_values)):
        tr = max(
            high_values[index] - low_values[index],
            abs(high_values[index] - close_values[index - 1]),
            abs(low_values[index] - close_values[index - 1]),
        )
        series.append(tr)
    return series


def _wilder_smooth(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    series: list[Decimal | None] = []
    if window <= 0:
        return series
    seed = _seed_average(values, window)
    current = seed
    for index, value in enumerate(values):
        if index + 1 < window:
            series.append(None)
            continue
        if index + 1 == window:
            current = seed
            series.append(current)
            continue
        current = ((current or DECIMAL_ZERO) * Decimal(window - 1) + value) / Decimal(window)
        series.append(current)
    return series


def atr_wilder_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    window: int = 14,
) -> IndicatorSeriesResult:
    tr = true_range_series(highs, lows, closes)
    series = _wilder_smooth(tr, window)
    ready, immature = _lookback_status(len(tr), window, window)
    return IndicatorSeriesResult(
        series=series, warmup=window, lookback_ready=ready, is_immature=immature
    )


def atr_ema_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    window: int = 14,
) -> IndicatorSeriesResult:
    tr = true_range_series(highs, lows, closes)
    result = ema_series(tr, window)
    return IndicatorSeriesResult(
        series=result.series,
        warmup=result.warmup,
        lookback_ready=result.lookback_ready,
        is_immature=result.is_immature,
    )


def macd_series(
    values: Sequence[Decimal | float | int],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDSeriesResult:
    prices = [_to_decimal(item) for item in values]
    if not prices:
        empty = IndicatorSeriesResult(
            series=[], warmup=signal, lookback_ready=False, is_immature=True
        )
        return MACDSeriesResult(macd=empty, signal=empty, histogram=empty)
    fast_multiplier = Decimal("2") / (Decimal(fast) + Decimal("1"))
    slow_multiplier = Decimal("2") / (Decimal(slow) + Decimal("1"))
    signal_multiplier = Decimal("2") / (Decimal(signal) + Decimal("1"))
    fast_ema = prices[0]
    slow_ema = prices[0]
    signal_ema: Decimal | None = None
    macd_values: list[Decimal] = []
    signal_values: list[Decimal | None] = []
    histogram_values: list[Decimal | None] = []
    for index, price in enumerate(prices):
        if index == 0:
            fast_ema = price
            slow_ema = price
        else:
            fast_ema = ((price - fast_ema) * fast_multiplier) + fast_ema
            slow_ema = ((price - slow_ema) * slow_multiplier) + slow_ema
        macd_value = fast_ema - slow_ema
        macd_values.append(macd_value)
        if signal_ema is None:
            signal_ema = macd_value
        else:
            signal_ema = ((macd_value - signal_ema) * signal_multiplier) + signal_ema
        signal_values.append(signal_ema)
        histogram_values.append(macd_value - signal_ema)
    macd_ready, macd_immature = _lookback_status(len(prices), slow, max(signal, slow // 3))
    signal_ready, signal_immature = _lookback_status(len(prices), slow + signal - 1, signal)
    macd_result = IndicatorSeriesResult(
        series=macd_values,
        warmup=max(signal, slow // 3),
        lookback_ready=macd_ready,
        is_immature=macd_immature,
    )
    signal_result = IndicatorSeriesResult(
        series=signal_values,
        warmup=signal,
        lookback_ready=signal_ready,
        is_immature=signal_immature,
    )
    hist_result = IndicatorSeriesResult(
        series=histogram_values,
        warmup=signal,
        lookback_ready=signal_ready,
        is_immature=signal_immature,
    )
    return MACDSeriesResult(macd=macd_result, signal=signal_result, histogram=hist_result)


def bbands_series(
    values: Sequence[Decimal | float | int],
    window: int = 20,
    stddev: Decimal | float | int = Decimal("2"),
) -> BBandsSeriesResult:
    prices = [_to_decimal(item) for item in values]
    multiplier = _to_decimal(stddev)
    middles: list[Decimal | None] = []
    uppers: list[Decimal | None] = []
    lowers: list[Decimal | None] = []
    widths: list[Decimal | None] = []
    percent_b_series: list[Decimal | None] = []
    for index in range(len(prices)):
        if index + 1 < window:
            middles.append(None)
            uppers.append(None)
            lowers.append(None)
            widths.append(None)
            percent_b_series.append(None)
            continue
        sample = prices[index - window + 1 : index + 1]
        middle = sum(sample, DECIMAL_ZERO) / Decimal(window)
        variance = sum(((item - middle) ** 2 for item in sample), DECIMAL_ZERO) / Decimal(window)
        std = _decimal_sqrt(variance)
        upper = middle + (std * multiplier)
        lower = middle - (std * multiplier)
        width = ((upper - lower) / middle) if middle else DECIMAL_ZERO
        percent_b = ((sample[-1] - lower) / (upper - lower)) if upper != lower else DECIMAL_ZERO
        middles.append(middle)
        uppers.append(upper)
        lowers.append(lower)
        widths.append(width)
        percent_b_series.append(percent_b)
    ready, immature = _lookback_status(len(prices), window, max(2, window // 2))
    return BBandsSeriesResult(
        middle=IndicatorSeriesResult(
            middles, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        upper=IndicatorSeriesResult(
            uppers, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        lower=IndicatorSeriesResult(
            lowers, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        bandwidth=IndicatorSeriesResult(
            widths, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        percent_b=IndicatorSeriesResult(
            percent_b_series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
    )


def adx_wilder_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    window: int = 14,
) -> dict[str, IndicatorSeriesResult]:
    high_values = [_to_decimal(item) for item in highs]
    low_values = [_to_decimal(item) for item in lows]
    close_values = [_to_decimal(item) for item in closes]
    if len(close_values) < 2:
        empty = IndicatorSeriesResult(
            series=[None for _ in close_values],
            warmup=window,
            lookback_ready=False,
            is_immature=True,
        )
        return {"adx": empty, "plus_di": empty, "minus_di": empty, "dx": empty}
    plus_dm_raw: list[Decimal] = [DECIMAL_ZERO]
    minus_dm_raw: list[Decimal] = [DECIMAL_ZERO]
    for index in range(1, len(close_values)):
        up_move = high_values[index] - high_values[index - 1]
        down_move = low_values[index - 1] - low_values[index]
        plus_dm_raw.append(up_move if up_move > down_move and up_move > 0 else DECIMAL_ZERO)
        minus_dm_raw.append(down_move if down_move > up_move and down_move > 0 else DECIMAL_ZERO)
    tr = true_range_series(high_values, low_values, close_values)
    tr_smooth = _wilder_smooth(tr, window)
    plus_smooth = _wilder_smooth(plus_dm_raw, window)
    minus_smooth = _wilder_smooth(minus_dm_raw, window)
    plus_di_series: list[Decimal | None] = []
    minus_di_series: list[Decimal | None] = []
    dx_series: list[Decimal | None] = []
    for index in range(len(close_values)):
        atr_value = tr_smooth[index] if index < len(tr_smooth) else None
        plus_value = plus_smooth[index] if index < len(plus_smooth) else None
        minus_value = minus_smooth[index] if index < len(minus_smooth) else None
        if atr_value in {None, DECIMAL_ZERO} or plus_value is None or minus_value is None:
            plus_di_series.append(None)
            minus_di_series.append(None)
            dx_series.append(None)
            continue
        plus_di = (plus_value / atr_value) * Decimal("100")
        minus_di = (minus_value / atr_value) * Decimal("100")
        total = plus_di + minus_di
        dx = (abs(plus_di - minus_di) / total) * Decimal("100") if total else DECIMAL_ZERO
        plus_di_series.append(plus_di)
        minus_di_series.append(minus_di)
        dx_series.append(dx)
    dx_numeric = [item if item is not None else DECIMAL_ZERO for item in dx_series]
    adx_series = _wilder_smooth(dx_numeric, window)
    di_ready, di_immature = _lookback_status(len(close_values), window + 1, window)
    adx_ready, adx_immature = _lookback_status(len(close_values), (window * 2) - 1, window)
    return {
        "plus_di": IndicatorSeriesResult(
            plus_di_series, warmup=window, lookback_ready=di_ready, is_immature=di_immature
        ),
        "minus_di": IndicatorSeriesResult(
            minus_di_series, warmup=window, lookback_ready=di_ready, is_immature=di_immature
        ),
        "dx": IndicatorSeriesResult(
            dx_series, warmup=window, lookback_ready=di_ready, is_immature=di_immature
        ),
        "adx": IndicatorSeriesResult(
            adx_series, warmup=window, lookback_ready=adx_ready, is_immature=adx_immature
        ),
    }


def obv_series(
    closes: Sequence[Decimal | float | int],
    volumes: Sequence[Decimal | float | int],
) -> IndicatorSeriesResult:
    c = [_to_decimal(item) for item in closes]
    v = [_to_decimal(item) for item in volumes]
    current = DECIMAL_ZERO
    series: list[Decimal | None] = []
    for index, close in enumerate(c):
        if index == 0:
            series.append(current)
            continue
        if close > c[index - 1]:
            current += v[index]
        elif close < c[index - 1]:
            current -= v[index]
        series.append(current)
    ready, immature = _lookback_status(len(c), 2, 5)
    return IndicatorSeriesResult(
        series=series, warmup=5, lookback_ready=ready, is_immature=immature
    )


def cci_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    window: int = 20,
) -> IndicatorSeriesResult:
    high_values = [_to_decimal(item) for item in highs]
    low_values = [_to_decimal(item) for item in lows]
    close_values = [_to_decimal(item) for item in closes]
    typical_prices = [
        (high_values[idx] + low_values[idx] + close_values[idx]) / Decimal("3")
        for idx in range(len(close_values))
    ]
    basis = sma_series(typical_prices, window).series
    series: list[Decimal | None] = []
    for index, typical in enumerate(typical_prices):
        middle = basis[index]
        if middle is None or index + 1 < window:
            series.append(None)
            continue
        sample = typical_prices[index - window + 1 : index + 1]
        mean_deviation = sum((abs(item - middle) for item in sample), DECIMAL_ZERO) / Decimal(
            window
        )
        if mean_deviation == 0:
            series.append(DECIMAL_ZERO)
            continue
        series.append((typical - middle) / (Decimal("0.015") * mean_deviation))
    ready, immature = _lookback_status(len(close_values), window, max(2, window // 2))
    return IndicatorSeriesResult(
        series=series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
    )


def kdj_series(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    window: int = 9,
) -> KDJSeriesResult:
    high_values = [_to_decimal(item) for item in highs]
    low_values = [_to_decimal(item) for item in lows]
    close_values = [_to_decimal(item) for item in closes]
    k_value = Decimal("50")
    d_value = Decimal("50")
    k_series: list[Decimal | None] = []
    d_series: list[Decimal | None] = []
    j_series: list[Decimal | None] = []
    for index in range(len(close_values)):
        start = max(0, index - window + 1)
        highest = max(high_values[start : index + 1])
        lowest = min(low_values[start : index + 1])
        rsv = (
            Decimal("50")
            if highest == lowest
            else ((close_values[index] - lowest) / (highest - lowest)) * Decimal("100")
        )
        k_value = (Decimal("2") / Decimal("3")) * k_value + (Decimal("1") / Decimal("3")) * rsv
        d_value = (Decimal("2") / Decimal("3")) * d_value + (Decimal("1") / Decimal("3")) * k_value
        j_value = (Decimal("3") * k_value) - (Decimal("2") * d_value)
        k_series.append(k_value)
        d_series.append(d_value)
        j_series.append(j_value)
    ready, immature = _lookback_status(len(close_values), window, max(2, window // 2))
    return KDJSeriesResult(
        k=IndicatorSeriesResult(
            series=k_series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        d=IndicatorSeriesResult(
            series=d_series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
        j=IndicatorSeriesResult(
            series=j_series, warmup=max(2, window // 2), lookback_ready=ready, is_immature=immature
        ),
    )
