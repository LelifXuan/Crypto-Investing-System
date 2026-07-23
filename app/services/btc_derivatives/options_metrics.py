from __future__ import annotations

from datetime import date, datetime
from math import erf, isfinite, log, sqrt
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
    *,
    spot_price: float | None = None,
    as_of: date | None = None,
) -> OptionQuote | None:
    candidates = [
        quote
        for quote in quotes
        if quote.option_type == option_type
        and _effective_delta(quote, spot_price=spot_price, as_of=as_of) is not None
        and safe_float(quote.iv) is not None
    ]
    return (
        min(
            candidates,
            key=lambda quote: abs(
                float(_effective_delta(quote, spot_price=spot_price, as_of=as_of) or 0)
                - target
            ),
        )
        if candidates
        else None
    )


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def model_delta(
    quote: OptionQuote,
    *,
    spot_price: float | None,
    as_of: date | None,
) -> float | None:
    expiry = None
    try:
        expiry = datetime.strptime(quote.expiry, "%Y-%m-%d").date()
    except ValueError:
        return None
    spot = safe_float(spot_price)
    volatility = safe_float(quote.iv)
    if spot in {None, 0} or volatility in {None, 0} or as_of is None:
        return None
    years = (expiry - as_of).days / 365
    if years <= 0 or quote.strike <= 0:
        return None
    d1 = (log(float(spot) / quote.strike) + 0.5 * volatility**2 * years) / (
        volatility * sqrt(years)
    )
    call_delta = _normal_cdf(d1)
    return call_delta if quote.option_type == "call" else call_delta - 1


def _effective_delta(
    quote: OptionQuote,
    *,
    spot_price: float | None,
    as_of: date | None,
) -> float | None:
    return safe_float(quote.delta) or model_delta(
        quote, spot_price=spot_price, as_of=as_of
    )


def _interpolated_delta_iv(
    quotes: Sequence[OptionQuote],
    *,
    option_type: str,
    target: float,
    spot_price: float | None,
    as_of: date | None,
) -> dict[str, Any] | None:
    candidates = sorted(
        (
            (float(delta), quote)
            for quote in quotes
            if quote.option_type == option_type
            and (delta := _effective_delta(quote, spot_price=spot_price, as_of=as_of))
            is not None
            and safe_float(quote.iv) is not None
        ),
        key=lambda item: item[0],
    )
    if not candidates:
        return None
    lower = max(
        (item for item in candidates if item[0] <= target),
        key=lambda item: item[0],
        default=None,
    )
    upper = min(
        (item for item in candidates if item[0] >= target),
        key=lambda item: item[0],
        default=None,
    )
    if lower and upper and lower[0] != upper[0]:
        weight = (target - lower[0]) / (upper[0] - lower[0])
        iv = float(lower[1].iv or 0) + weight * (
            float(upper[1].iv or 0) - float(lower[1].iv or 0)
        )
        representative = min((lower, upper), key=lambda item: abs(item[0] - target))[1]
        return {
            "iv": iv,
            "strike": representative.strike,
            "delta": target,
            "interpolated": True,
        }
    delta, quote = min(candidates, key=lambda item: abs(item[0] - target))
    return {
        "iv": float(quote.iv or 0),
        "strike": quote.strike,
        "delta": delta,
        "interpolated": False,
    }


def skew_25d(
    quotes: Sequence[OptionQuote],
    spot_price: float | None = None,
    *,
    as_of: date | None = None,
    fallback_quotes: Sequence[OptionQuote] = (),
    delta_tolerance: float = 0.15,
) -> dict[str, Any]:
    """Compute 25-delta put/call skew with graceful degradation.

    Primary lookup walks ``quotes`` (the selected-expiry chain). When one
    side (call or put) cannot be resolved on the primary chain, the missing
    side is borrowed from ``fallback_quotes`` (a neighbouring standard
    expiry's chain) so the user sees a continuous series instead of an
    unexplained gap.

    Single candidates whose |delta| falls inside the
    ``[0.25 - delta_tolerance, 0.25 + delta_tolerance]`` band are accepted
    as ``near_25d``; tighter or wider hits are reported via the
    ``delta_band`` field so the chart layer can decide whether to draw an
    "approximate" annotation.
    """

    def _classify_band(abs_delta: float) -> str:
        # exact = a real lower/upper interpolation bracketed 0.25; otherwise
        # we accepted a single nearest-neighbour strike and need to tell
        # the caller how close that strike was to the target.
        return "exact_25d" if abs(abs_delta - 0.25) < 1e-9 else "near_25d"

    def _resolve_side(
        option_type: str,
        target: float,
        source_pool: Sequence[OptionQuote],
    ) -> dict[str, Any] | None:
        result = _interpolated_delta_iv(
            source_pool,
            option_type=option_type,
            target=target,
            spot_price=spot_price,
            as_of=as_of,
        )
        if result is None:
            return None
        abs_delta = abs(float(result["delta"]))
        # Tighten: if the single-nearest pick falls outside the tolerance
        # band we still return it (callers asked for graceful degradation),
        # but we record the band so the chart layer can flag it.
        result["delta_band"] = (
            _classify_band(abs_delta)
            if abs_delta <= 0.25 + delta_tolerance
            else "outside_band"
        )
        return result

    primary_call = _resolve_side("call", 0.25, quotes)
    primary_put = _resolve_side("put", -0.25, quotes)
    fallback_used_for: list[str] = []
    call = primary_call
    put = primary_put
    if call is None or put is None:
        # Borrow only the missing side(s); never replace a side that the
        # primary chain already resolved.
        if call is None:
            call = _resolve_side("call", 0.25, fallback_quotes)
            if call is not None:
                fallback_used_for.append("call")
        if put is None:
            put = _resolve_side("put", -0.25, fallback_quotes)
            if put is not None:
                fallback_used_for.append("put")
    if call is None or put is None:
        return {
            "put_call_skew": None,
            "risk_reversal": None,
            "status": "data_insufficient",
            "delta_source": "unavailable",
            "delta_band": "outside_band",
            "fallback_sides": fallback_used_for,
        }
    put_call_skew = round(float(put["iv"]) - float(call["iv"]), 10)
    provider_delta_count = sum(safe_float(item.delta) is not None for item in quotes)
    combined_pool = list(quotes) + list(fallback_quotes)
    delta_source = (
        "cross_expiry"
        if fallback_used_for
        else "provider"
        if provider_delta_count
        else "model_estimate"
    )
    return {
        "put_call_skew": put_call_skew,
        "risk_reversal": -put_call_skew,
        "call_strike": call["strike"],
        "put_strike": put["strike"],
        "call_iv": call["iv"],
        "put_iv": put["iv"],
        "call_delta": call["delta"],
        "put_delta": put["delta"],
        "interpolated": bool(call["interpolated"] or put["interpolated"]),
        "delta_source": delta_source,
        "delta_band": (
            "exact_25d"
            if call["delta_band"] == "exact_25d" and put["delta_band"] == "exact_25d"
            else "near_25d"
        ),
        "fallback_sides": fallback_used_for,
        "provider_delta_coverage": (
            provider_delta_count / len(combined_pool) if combined_pool else 0
        ),
        "status": "ok",
    }


def standardized_protection_costs(
    quotes: Sequence[OptionQuote],
    *,
    spot_price: float,
    as_of: date,
) -> dict[str, Any]:
    def choose(option_type: str, target: float) -> OptionQuote | None:
        return _nearest_delta(
            quotes,
            target if option_type == "call" else -target,
            option_type,
            spot_price=spot_price,
            as_of=as_of,
        )

    long_call = choose("call", 0.25)
    long_put = choose("put", 0.25)
    short_call = choose("call", 0.10)
    call_mid = mid_price(long_call.bid, long_call.ask, long_call.mark) if long_call else None
    put_mid = mid_price(long_put.bid, long_put.ask, long_put.mark) if long_put else None
    short_mid = mid_price(short_call.bid, short_call.ask, short_call.mark) if short_call else None
    debit = (
        max(call_mid - short_mid, 0)
        if call_mid is not None
        and short_mid is not None
        and long_call is not None
        and short_call is not None
        and short_call.strike > long_call.strike
        else None
    )
    selected = [item for item in (long_call, long_put, short_call) if item is not None]
    provider_delta_count = sum(safe_float(item.delta) is not None for item in selected)
    return {
        "call_protection_cost_pct": call_mid / spot_price if call_mid is not None else None,
        "put_protection_cost_pct": put_mid / spot_price if put_mid is not None else None,
        "debit_spread_cost_pct": debit / spot_price if debit is not None else None,
        "selection_method": "constant_delta",
        "delta_source": (
            "provider" if selected and provider_delta_count == len(selected)
            else "model_estimate" if selected else "unavailable"
        ),
        "liquidity_status": (
            "usable" if selected and all(liquidity_class(item) != "poor" for item in selected)
            else "degraded"
        ),
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
