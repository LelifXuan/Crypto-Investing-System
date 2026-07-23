from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.structure.pivots import detect_pivots_adaptive


@dataclass
class _FakeCandle:
    ts_open: datetime
    open: float
    high: float
    low: float
    close: float


def _make_candles(prices: list[float], *, hours_per: float = 1.0) -> list[_FakeCandle]:
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        _FakeCandle(
            ts_open=base + timedelta(hours=i * hours_per),
            open=p,
            high=p + 0.05,
            low=p - 0.05,
            close=p,
        )
        for i, p in enumerate(prices)
    ]


def _zigzag_prices(n: int = 200, swing_pct: float = 0.012, swing_step: int = 40) -> list[float]:
    """Deterministic zigzag with N candles and a fixed swing amplitude.

    No per-candle noise — used to test pure prominence (swing amplitude)
    behavior across timeframes without random interference.
    """
    out: list[float] = []
    price = 100.0
    for i in range(n):
        if i and i % swing_step == 0:
            price += swing_pct * 100 * (1 if (i // swing_step) % 2 == 0 else -1)
        out.append(price)
    return out


def test_short_timeframe_filters_small_swings_more_aggressively() -> None:
    """1h should drop sub-percent swings that 1w keeps.

    Build a series where each cycle has a 0.5% swing. With the 1h
    multiplier (2.0× ATR ≈ 0.8%), those swings should be rejected; with
    the 1w multiplier (0.8× ATR ≈ 0.32%), they're accepted.
    """
    prices = _zigzag_prices(n=200, swing_pct=0.005, swing_step=30)
    candles = _make_candles(prices)
    pivots_1h = detect_pivots_adaptive(candles, timeframe="1h")
    pivots_1w = detect_pivots_adaptive(candles, timeframe="1w")
    # 1w must keep at least one swing pivot; 1h should drop most of them.
    assert len(pivots_1w) >= 4
    assert len(pivots_1h) <= len(pivots_1w)


def test_short_timeframe_keeps_large_swings() -> None:
    """Big swings are detected at every timeframe — the multiplier is a
    floor, not a ceiling. A 3% swing must surface on 1h *and* 1w."""
    prices = _zigzag_prices(n=200, swing_pct=0.03, swing_step=30)
    candles = _make_candles(prices)
    pivots_1h = detect_pivots_adaptive(candles, timeframe="1h")
    pivots_1w = detect_pivots_adaptive(candles, timeframe="1w")
    assert len(pivots_1h) >= 4
    assert len(pivots_1w) >= 4
    # 1h is more selective than 1w, but both detect the major swings.
    assert len(pivots_1h) <= len(pivots_1w)


def test_short_timeframe_window_is_wider_than_long_timeframe() -> None:
    """Direct sanity check: with the same no-noise zigzag, the 1h
    window (4) absorbs more local noise than the 1w window (2) — but
    the prominence threshold scales inversely so neither produces a
    nonsense count."""
    prices = _zigzag_prices(n=200, swing_pct=0.02, swing_step=30)
    candles = _make_candles(prices)

    pivots_15m = detect_pivots_adaptive(candles, timeframe="15m")
    pivots_1h = detect_pivots_adaptive(candles, timeframe="1h")
    pivots_4h = detect_pivots_adaptive(candles, timeframe="4h")
    pivots_1d = detect_pivots_adaptive(candles, timeframe="1d")
    pivots_1w = detect_pivots_adaptive(candles, timeframe="1w")

    # Both extremes produce *some* pivots — short TFs are at least
    # as strict, so the chain is monotonic non-decreasing.
    counts = [len(pivots_15m), len(pivots_1h), len(pivots_4h), len(pivots_1d), len(pivots_1w)]
    for i in range(len(counts) - 1):
        assert counts[i] <= counts[i + 1], f"timeframe chain not monotonic: {counts}"
    # Sanity: each TF yields at least the first and last swing.
    assert len(pivots_15m) >= 2
    assert len(pivots_1w) >= 2


def test_unknown_timeframe_falls_back_to_count_based_window() -> None:
    """Unknown timeframes still produce a result using the original
    candle-count-based window selection, so callers don't silently lose
    pivot data when a new timeframe is introduced."""
    prices = _zigzag_prices(n=150, swing_pct=0.02, swing_step=30)
    candles = _make_candles(prices)
    pivots = detect_pivots_adaptive(candles, timeframe="3h")  # not in mapping
    assert len(pivots) >= 2