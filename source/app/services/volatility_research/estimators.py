from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Sequence

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
SECONDS_PER_YEAR = Decimal(365 * 24 * 60 * 60)


@dataclass(frozen=True, slots=True)
class OhlcBar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def _valid_bar(bar: OhlcBar) -> bool:
    return (
        bar.open > ZERO
        and bar.high > ZERO
        and bar.low > ZERO
        and bar.close > ZERO
        and bar.high >= max(bar.open, bar.close, bar.low)
        and bar.low <= min(bar.open, bar.close, bar.high)
    )


def _ln_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if numerator <= ZERO or denominator <= ZERO:
        raise ValueError("log-return inputs must be positive")
    with localcontext() as ctx:
        ctx.prec = 38
        return (numerator / denominator).ln()


def _sqrt_non_negative(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        return max(value, ZERO).sqrt()


def annualization_factor(bar_seconds: int) -> Decimal:
    if bar_seconds <= 0:
        raise ValueError("bar_seconds must be positive")
    return SECONDS_PER_YEAR / Decimal(bar_seconds)


def close_returns(bars: Sequence[OhlcBar]) -> list[Decimal]:
    valid = [bar for bar in bars if _valid_bar(bar)]
    return [_ln_ratio(valid[index].close, valid[index - 1].close) for index in range(1, len(valid))]


def atr_natr(
    bars: Sequence[OhlcBar], window: int = 14
) -> tuple[Decimal | None, Decimal | None]:
    valid = [bar for bar in bars if _valid_bar(bar)]
    if window < 1 or len(valid) < window + 1:
        return None, None
    true_ranges: list[Decimal] = []
    for index in range(1, len(valid)):
        current = valid[index]
        previous_close = valid[index - 1].close
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )
    atr = sum(true_ranges[:window], ZERO) / Decimal(window)
    for value in true_ranges[window:]:
        atr = (atr * Decimal(window - 1) + value) / Decimal(window)
    close = valid[-1].close
    return atr, (atr / close * Decimal(100) if close else None)


def realized_volatility(bars: Sequence[OhlcBar], bar_seconds: int) -> Decimal | None:
    returns = close_returns(bars)
    if not returns:
        return None
    variance = sum((item * item for item in returns), ZERO) / Decimal(len(returns))
    return _sqrt_non_negative(variance * annualization_factor(bar_seconds))


def ewma_volatility(
    bars: Sequence[OhlcBar], bar_seconds: int, decay: Decimal = Decimal("0.94")
) -> Decimal | None:
    if not ZERO < decay < ONE:
        raise ValueError("decay must be between zero and one")
    returns = close_returns(bars)
    if not returns:
        return None
    variance = returns[0] * returns[0]
    for item in returns[1:]:
        variance = decay * variance + (ONE - decay) * item * item
    return _sqrt_non_negative(variance * annualization_factor(bar_seconds))


def _range_variance(bars: Sequence[OhlcBar], kind: str) -> Decimal | None:
    valid = [bar for bar in bars if _valid_bar(bar)]
    if not valid:
        return None
    ln2 = TWO.ln()
    terms: list[Decimal] = []
    for bar in valid:
        hl = _ln_ratio(bar.high, bar.low)
        co = _ln_ratio(bar.close, bar.open)
        if kind == "parkinson":
            terms.append((hl * hl) / (Decimal(4) * ln2))
        elif kind == "garman_klass":
            terms.append(Decimal("0.5") * hl * hl - (TWO * ln2 - ONE) * co * co)
        elif kind == "rogers_satchell":
            terms.append(
                _ln_ratio(bar.high, bar.open) * _ln_ratio(bar.high, bar.close)
                + _ln_ratio(bar.low, bar.open) * _ln_ratio(bar.low, bar.close)
            )
        elif kind == "realized_range":
            terms.append(hl * hl)
        else:  # pragma: no cover - internal contract
            raise ValueError(f"unknown range estimator: {kind}")
    return max(sum(terms, ZERO) / Decimal(len(terms)), ZERO)


def range_volatility(
    bars: Sequence[OhlcBar], bar_seconds: int, kind: str
) -> Decimal | None:
    variance = _range_variance(bars, kind)
    if variance is None:
        return None
    return _sqrt_non_negative(variance * annualization_factor(bar_seconds))


def yang_zhang_volatility(bars: Sequence[OhlcBar], bar_seconds: int) -> Decimal | None:
    valid = [bar for bar in bars if _valid_bar(bar)]
    if len(valid) < 3:
        return None
    overnight = [_ln_ratio(valid[i].open, valid[i - 1].close) for i in range(1, len(valid))]
    open_close = [_ln_ratio(bar.close, bar.open) for bar in valid[1:]]
    rs = _range_variance(valid[1:], "rogers_satchell")
    if rs is None:
        return None

    def sample_variance(values: Sequence[Decimal]) -> Decimal:
        mean = sum(values, ZERO) / Decimal(len(values))
        return sum(((item - mean) ** 2 for item in values), ZERO) / Decimal(len(values) - 1)

    n = Decimal(len(valid))
    k = Decimal("0.34") / (Decimal("1.34") + (n + ONE) / (n - ONE))
    variance = sample_variance(overnight) + k * sample_variance(open_close) + (ONE - k) * rs
    return _sqrt_non_negative(variance * annualization_factor(bar_seconds))


def bipower_and_jump_volatility(
    bars: Sequence[OhlcBar], bar_seconds: int
) -> tuple[Decimal | None, Decimal | None]:
    returns = close_returns(bars)
    if len(returns) < 2:
        return None, None
    rv_variance = sum((item * item for item in returns), ZERO) / Decimal(len(returns))
    products = [abs(returns[index]) * abs(returns[index - 1]) for index in range(1, len(returns))]
    pi = Decimal("3.141592653589793238462643383279502884")
    bipower_variance = pi / TWO * sum(products, ZERO) / Decimal(len(products))
    factor = annualization_factor(bar_seconds)
    return (
        _sqrt_non_negative(bipower_variance * factor),
        _sqrt_non_negative(max(rv_variance - bipower_variance, ZERO) * factor),
    )


def bollinger_bandwidth(closes: Sequence[Decimal], window: int = 20) -> Decimal | None:
    if window < 2 or len(closes) < window:
        return None
    values = list(closes[-window:])
    if any(item <= ZERO for item in values):
        return None
    mean = sum(values, ZERO) / Decimal(window)
    variance = sum(((item - mean) ** 2 for item in values), ZERO) / Decimal(window)
    stddev = _sqrt_non_negative(variance)
    return (Decimal(4) * stddev / mean) if mean else None


def empirical_percentile(history: Sequence[Decimal], current: Decimal) -> Decimal | None:
    values = [item for item in history if item.is_finite()]
    if not values:
        return None
    below = sum(1 for item in values if item < current)
    equal = sum(1 for item in values if item == current)
    # Mid-rank avoids making repeated flat values look maximally extreme.
    return (Decimal(below) + Decimal(equal) / TWO) / Decimal(len(values)) * Decimal(100)


def safe_decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None
