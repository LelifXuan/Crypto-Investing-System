from __future__ import annotations

from .common import Pivot, to_float


def detect_pivots(candles: list, window: int = 2) -> list[Pivot]:
    pivots: list[Pivot] = []
    values = [{"high": to_float(candle.high), "low": to_float(candle.low)} for candle in candles]
    for idx in range(window, max(len(candles) - window, window)):
        local = values[idx - window : idx + window + 1]
        high = values[idx]["high"]
        low = values[idx]["low"]
        if high == max(item["high"] for item in local):
            pivots.append(Pivot(ts=candles[idx].ts_open, price=high, kind="high", index=idx))
        if low == min(item["low"] for item in local):
            pivots.append(Pivot(ts=candles[idx].ts_open, price=low, kind="low", index=idx))
    pivots.sort(key=lambda item: item.ts)
    compressed: list[Pivot] = []
    for pivot in pivots:
        if compressed and compressed[-1].kind == pivot.kind:
            if pivot.kind == "high" and pivot.price > compressed[-1].price:
                compressed[-1] = pivot
            elif pivot.kind == "low" and pivot.price < compressed[-1].price:
                compressed[-1] = pivot
            continue
        compressed.append(pivot)
    return compressed[-14:]
