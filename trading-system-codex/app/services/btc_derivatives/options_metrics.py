from __future__ import annotations

from math import isfinite
from typing import Any, Iterable, Sequence

from app.services.btc_derivatives.models import OptionChainRow, OptionQuote


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def mid_price(bid: Any, ask: Any, mark: Any = None) -> float | None:
    bid_value = safe_float(bid)
    ask_value = safe_float(ask)
    if (
        bid_value is not None
        and ask_value is not None
        and bid_value >= 0
        and ask_value > 0
        and ask_value >= bid_value
    ):
        return (bid_value + ask_value) / 2
    return safe_float(mark)


def spread_pct(bid: Any, ask: Any) -> float | None:
    bid_value = safe_float(bid)
    ask_value = safe_float(ask)
    if (
        bid_value is None
        or ask_value is None
        or bid_value < 0
        or ask_value <= 0
        or ask_value < bid_value
    ):
        return None
    midpoint = (bid_value + ask_value) / 2
    return (ask_value - bid_value) / midpoint if midpoint > 0 else None


def liquidity_class(quote: OptionQuote) -> str:
    spread = spread_pct(quote.bid, quote.ask)
    open_interest = safe_float(quote.open_interest) or 0
    volume = safe_float(quote.volume_24h) or 0
    if spread is None:
        return "poor"
    if spread <= 0.05 and (open_interest > 0 or volume > 0):
        return "good"
    if spread <= 0.10 and open_interest > 0:
        return "usable"
    return "poor"


def group_options_by_expiry(quotes: Iterable[OptionQuote]) -> dict[str, list[OptionQuote]]:
    grouped: dict[str, list[OptionQuote]] = {}
    for quote in quotes:
        grouped.setdefault(quote.expiry, []).append(quote)
    return grouped


def chain_rows_for_expiry(
    quotes: Sequence[OptionQuote],
    expiry: str,
) -> list[OptionChainRow]:
    grouped: dict[float, dict[str, OptionQuote]] = {}
    for quote in quotes:
        if quote.expiry == expiry:
            grouped.setdefault(float(quote.strike), {})[quote.option_type] = quote
    return [
        OptionChainRow(
            expiry=expiry,
            strike=strike,
            call=sides.get("call"),
            put=sides.get("put"),
        )
        for strike, sides in sorted(grouped.items())
    ]


def option_walls(rows: Sequence[OptionChainRow]) -> dict[str, Any]:
    calls = [
        (row.strike, value)
        for row in rows
        if row.call and (value := safe_float(row.call.open_interest)) is not None
    ]
    puts = [
        (row.strike, value)
        for row in rows
        if row.put and (value := safe_float(row.put.open_interest)) is not None
    ]
    call_wall = max(calls, key=lambda item: item[1]) if calls else None
    put_wall = max(puts, key=lambda item: item[1]) if puts else None
    return {
        "call_wall_strike": call_wall[0] if call_wall else None,
        "call_wall_oi": call_wall[1] if call_wall else None,
        "put_wall_strike": put_wall[0] if put_wall else None,
        "put_wall_oi": put_wall[1] if put_wall else None,
        "status": "ok" if call_wall or put_wall else "data_insufficient",
        "warning": "期权墙仅反映持仓集中与潜在对冲敏感区，不是确定支撑或阻力。",
    }


def max_pain(rows: Sequence[OptionChainRow]) -> dict[str, Any]:
    strikes = sorted({row.strike for row in rows})
    if not strikes:
        return {
            "strike": None,
            "total_payout": None,
            "payout_curve": [],
            "status": "data_insufficient",
            "warning": "最大痛点缺少可计算的期权持仓数据，不是价格预测。",
        }
    curve: list[dict[str, float]] = []
    for settlement in strikes:
        payout = 0.0
        for row in rows:
            call_oi = safe_float(row.call.open_interest) if row.call else 0.0
            put_oi = safe_float(row.put.open_interest) if row.put else 0.0
            payout += max(0.0, settlement - row.strike) * (call_oi or 0.0)
            payout += max(0.0, row.strike - settlement) * (put_oi or 0.0)
        curve.append({"strike": settlement, "total_payout": payout})
    best = min(curve, key=lambda item: (item["total_payout"], item["strike"]))
    return {
        "strike": best["strike"],
        "total_payout": best["total_payout"],
        "payout_curve": curve,
        "status": "ok",
        "warning": "最大痛点仅作为期权持仓分布参考，不是价格预测。",
    }


def nearest_strike_row(
    rows: Sequence[OptionChainRow],
    spot_price: float,
) -> OptionChainRow | None:
    return min(rows, key=lambda row: abs(row.strike - spot_price)) if rows else None


def atm_iv_for_expiry(
    rows: Sequence[OptionChainRow],
    spot_price: float,
) -> dict[str, Any]:
    row = nearest_strike_row(rows, spot_price)
    if row is None:
        return {"strike": None, "atm_iv": None, "status": "data_insufficient"}
    values = [
        value
        for value in (
            safe_float(row.call.iv) if row.call else None,
            safe_float(row.put.iv) if row.put else None,
        )
        if value is not None
    ]
    return {
        "strike": row.strike,
        "atm_iv": sum(values) / len(values) if values else None,
        "status": "ok" if values else "data_insufficient",
    }


def atm_iv_term_structure(
    quotes: Sequence[OptionQuote],
    spot_price: float,
) -> list[dict[str, Any]]:
    return [
        {
            "expiry": expiry,
            **atm_iv_for_expiry(chain_rows_for_expiry(quotes, expiry), spot_price),
        }
        for expiry in sorted(group_options_by_expiry(quotes))
    ]


def iv_smile(rows: Sequence[OptionChainRow]) -> list[dict[str, Any]]:
    return [
        {
            "strike": row.strike,
            "call_iv": safe_float(row.call.iv) if row.call else None,
            "put_iv": safe_float(row.put.iv) if row.put else None,
        }
        for row in rows
    ]


def _nearest_delta(
    quotes: Sequence[OptionQuote],
    target: float,
    option_type: str,
) -> OptionQuote | None:
    candidates = [
        quote
        for quote in quotes
        if quote.option_type == option_type
        and safe_float(quote.delta) is not None
        and safe_float(quote.iv) is not None
    ]
    return (
        min(
            candidates,
            key=lambda quote: abs(float(quote.delta or 0) - target),
        )
        if candidates
        else None
    )


def skew_25d(quotes: Sequence[OptionQuote]) -> dict[str, Any]:
    call = _nearest_delta(quotes, 0.25, "call")
    put = _nearest_delta(quotes, -0.25, "put")
    if call is None or put is None:
        return {
            "put_call_skew": None,
            "risk_reversal": None,
            "status": "data_insufficient",
        }
    put_call_skew = round(float(put.iv or 0) - float(call.iv or 0), 10)
    return {
        "put_call_skew": put_call_skew,
        "risk_reversal": -put_call_skew,
        "call_strike": call.strike,
        "put_strike": put.strike,
        "call_iv": call.iv,
        "put_iv": put.iv,
        "status": "ok",
    }


def put_call_ratios(rows: Sequence[OptionChainRow]) -> dict[str, Any]:
    call_oi = sum(safe_float(row.call.open_interest) or 0 for row in rows if row.call)
    put_oi = sum(safe_float(row.put.open_interest) or 0 for row in rows if row.put)
    call_volume = sum(safe_float(row.call.volume_24h) or 0 for row in rows if row.call)
    put_volume = sum(safe_float(row.put.volume_24h) or 0 for row in rows if row.put)
    return {
        "call_oi": call_oi,
        "put_oi": put_oi,
        "put_call_oi_ratio": put_oi / call_oi if call_oi > 0 else None,
        "call_volume_24h": call_volume,
        "put_volume_24h": put_volume,
        "put_call_volume_ratio": put_volume / call_volume if call_volume > 0 else None,
    }
