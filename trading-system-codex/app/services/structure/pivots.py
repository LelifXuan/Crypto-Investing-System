from __future__ import annotations

from .common import Pivot, clamp, to_float


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


def detect_pivots_adaptive(
    candles: list,
    timeframe: str = "1d",
    min_pivots: int = 12,
    max_pivots: int = 48,
) -> list[Pivot]:
    n = len(candles)
    if n < 20:
        return []

    if n < 120:
        window = 2
    elif n < 260:
        window = 3
    else:
        window = 4

    atr_pct = _compute_atr_pct(candles)
    min_reversal_pct = clamp(atr_pct * 1.6, 0.006, 0.045)

    raw: list[Pivot] = []
    values = [{"high": to_float(c.high), "low": to_float(c.low)} for c in candles]
    for idx in range(window, max(n - window, window)):
        local = values[idx - window : idx + window + 1]
        high = values[idx]["high"]
        low = values[idx]["low"]
        if high == max(item["high"] for item in local):
            raw.append(Pivot(ts=candles[idx].ts_open, price=high, kind="high", index=idx))
        if low == min(item["low"] for item in local):
            raw.append(Pivot(ts=candles[idx].ts_open, price=low, kind="low", index=idx))

    raw.sort(key=lambda p: (p.index, 0 if p.kind == "high" else 1))

    prominence_filtered: list[Pivot] = []
    for pivot in raw:
        prev_opposite = _find_opposite_before(raw, pivot)
        next_opposite = _find_opposite_after(raw, pivot)
        if prev_opposite is None or next_opposite is None:
            prominence_filtered.append(pivot)
            continue
        if pivot.kind == "high":
            ref_price = max(prev_opposite.price, next_opposite.price)
            if ref_price <= 0:
                prominence_filtered.append(pivot)
                continue
            reversal = (pivot.price - ref_price) / ref_price
        else:
            ref_price = min(prev_opposite.price, next_opposite.price)
            if ref_price <= 0:
                prominence_filtered.append(pivot)
                continue
            reversal = (ref_price - pivot.price) / ref_price
        if reversal >= min_reversal_pct:
            prominence_filtered.append(pivot)

    prominence_filtered.sort(key=lambda p: p.ts)
    compressed: list[Pivot] = []
    for pivot in prominence_filtered:
        if compressed and compressed[-1].kind == pivot.kind:
            if pivot.kind == "high" and pivot.price > compressed[-1].price:
                compressed[-1] = pivot
            elif pivot.kind == "low" and pivot.price < compressed[-1].price:
                compressed[-1] = pivot
            continue
        compressed.append(pivot)

    compressed.sort(key=lambda p: p.index)
    return compressed[-max_pivots:] if len(compressed) >= min_pivots else compressed


def _compute_atr_pct(candles: list) -> float:
    n = len(candles)
    if n < 14:
        return 0.012
    true_ranges = []
    for i in range(1, min(n, 60)):
        prev = candles[i - 1]
        curr = candles[i]
        high = to_float(curr.high)
        low = to_float(curr.low)
        prev_close = to_float(prev.close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ref = max(to_float(curr.close), 0.0001)
        true_ranges.append(tr / ref)
    if not true_ranges:
        return 0.012
    avg_tr = sum(true_ranges) / len(true_ranges)
    return clamp(avg_tr, 0.004, 0.060)


def _find_opposite_before(all_pivots: list[Pivot], current: Pivot) -> Pivot | None:
    for p in reversed(all_pivots):
        if p.index >= current.index:
            continue
        if p.kind != current.kind:
            return p
        if p.kind == "high" and p.price > current.price:
            break
        if p.kind == "low" and p.price < current.price:
            break
    return None


def _find_opposite_after(all_pivots: list[Pivot], current: Pivot) -> Pivot | None:
    for p in all_pivots:
        if p.index <= current.index:
            continue
        if p.kind != current.kind:
            return p
        if p.kind == "high" and p.price > current.price:
            break
        if p.kind == "low" and p.price < current.price:
            break
    return None
