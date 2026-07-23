from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

ZERO = Decimal("0")


@dataclass(slots=True)
class TradeSample:
    price: Decimal
    size: Decimal
    side: str | None = None


@dataclass(slots=True)
class CvdDelta:
    buy_volume: Decimal
    sell_volume: Decimal
    delta: Decimal
    cvd: Decimal
    trade_count: int


@dataclass(slots=True)
class OpenInterestSummary:
    open_interest: Decimal
    open_interest_notional: Decimal
    open_interest_change: Decimal | None
    open_interest_change_pct: Decimal | None


@dataclass(slots=True)
class DepthSlippage:
    spread_bps: Decimal
    depth_10bps: Decimal
    depth_50bps: Decimal
    depth_100bps: Decimal
    buy_slippage_bps: Decimal | None
    sell_slippage_bps: Decimal | None


def aggregate_cvd_delta(
    trades: Iterable[TradeSample | dict], *, previous_cvd: Decimal = ZERO
) -> CvdDelta:
    buy_volume = ZERO
    sell_volume = ZERO
    trade_count = 0
    for raw in trades:
        trade = _coerce_trade(raw)
        trade_count += 1
        side = (trade.side or "").lower()
        signed_size = trade.size
        if side == "buy" or signed_size > ZERO and side not in {"sell", "short"}:
            buy_volume += abs(signed_size)
        elif side == "sell" or signed_size < ZERO:
            sell_volume += abs(signed_size)
    delta = buy_volume - sell_volume
    return CvdDelta(
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        delta=delta,
        cvd=previous_cvd + delta,
        trade_count=trade_count,
    )


def summarize_open_interest(
    open_interest: Decimal,
    mark_price: Decimal,
    *,
    previous_open_interest: Decimal | None = None,
    contract_multiplier: Decimal = Decimal("1"),
) -> OpenInterestSummary:
    notional = open_interest * mark_price * contract_multiplier
    change = None
    change_pct = None
    if previous_open_interest is not None:
        change = open_interest - previous_open_interest
        if previous_open_interest:
            change_pct = change / previous_open_interest
    return OpenInterestSummary(
        open_interest=open_interest,
        open_interest_notional=notional,
        open_interest_change=change,
        open_interest_change_pct=change_pct,
    )


def summarize_depth_slippage(
    bids: Iterable[tuple[Decimal, Decimal] | list | dict],
    asks: Iterable[tuple[Decimal, Decimal] | list | dict],
    *,
    notional: Decimal,
) -> DepthSlippage:
    bid_levels = sorted(_coerce_levels(bids), key=lambda item: item[0], reverse=True)
    ask_levels = sorted(_coerce_levels(asks), key=lambda item: item[0])
    best_bid = bid_levels[0][0] if bid_levels else ZERO
    best_ask = ask_levels[0][0] if ask_levels else ZERO
    mid = (best_bid + best_ask) / Decimal("2") if best_bid and best_ask else ZERO
    spread_bps = ((best_ask - best_bid) / mid * Decimal("10000")) if mid else ZERO
    return DepthSlippage(
        spread_bps=spread_bps,
        depth_10bps=_depth_within_bps(bid_levels, ask_levels, mid, Decimal("10")),
        depth_50bps=_depth_within_bps(bid_levels, ask_levels, mid, Decimal("50")),
        depth_100bps=_depth_within_bps(bid_levels, ask_levels, mid, Decimal("100")),
        buy_slippage_bps=_slippage_bps(ask_levels, notional=notional, mid=mid),
        sell_slippage_bps=_slippage_bps(bid_levels, notional=notional, mid=mid),
    )


def _coerce_trade(raw: TradeSample | dict) -> TradeSample:
    if isinstance(raw, TradeSample):
        return raw
    return TradeSample(
        price=Decimal(str(raw.get("price") or 0)),
        size=Decimal(str(raw.get("size") or raw.get("amount") or raw.get("qty") or 0)),
        side=raw.get("side"),
    )


def _coerce_levels(
    levels: Iterable[tuple[Decimal, Decimal] | list | dict],
) -> list[tuple[Decimal, Decimal]]:
    parsed: list[tuple[Decimal, Decimal]] = []
    for level in levels:
        if isinstance(level, dict):
            price = level.get("price") or level.get("p")
            size = level.get("size") or level.get("s") or level.get("amount")
        else:
            price = level[0] if len(level) > 0 else None
            size = level[1] if len(level) > 1 else None
        if price is None or size is None:
            continue
        parsed.append((Decimal(str(price)), abs(Decimal(str(size)))))
    return parsed


def _depth_within_bps(
    bids: list[tuple[Decimal, Decimal]],
    asks: list[tuple[Decimal, Decimal]],
    mid: Decimal,
    bps: Decimal,
) -> Decimal:
    if not mid:
        return ZERO
    lower = mid * (Decimal("1") - bps / Decimal("10000"))
    upper = mid * (Decimal("1") + bps / Decimal("10000"))
    bid_notional = sum(price * size for price, size in bids if price >= lower)
    ask_notional = sum(price * size for price, size in asks if price <= upper)
    return bid_notional + ask_notional


def _slippage_bps(
    levels: list[tuple[Decimal, Decimal]], *, notional: Decimal, mid: Decimal
) -> Decimal | None:
    if not levels or not mid or notional <= ZERO:
        return None
    remaining = notional
    filled_base = ZERO
    paid_notional = ZERO
    for price, size in levels:
        level_notional = price * size
        take_notional = min(level_notional, remaining)
        if take_notional <= ZERO:
            continue
        take_base = take_notional / price
        filled_base += take_base
        paid_notional += take_notional
        remaining -= take_notional
        if remaining <= ZERO:
            break
    if remaining > ZERO or filled_base <= ZERO:
        return None
    average_price = paid_notional / filled_base
    return abs(average_price - mid) / mid * Decimal("10000")
