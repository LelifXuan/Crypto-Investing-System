from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.btc_derivatives_sources import (
    NormalizedOptionQuote,
    NormalizedPerpSnapshot,
)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: Any) -> datetime | None:
    numeric = _float(value)
    if numeric is None:
        return None
    if numeric > 10_000_000_000:
        numeric /= 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc)


def _iv(value: Any) -> float | None:
    numeric = _float(value)
    if numeric is None:
        return None
    return round(numeric / 100, 8) if abs(numeric) > 3 else numeric


def _mid(bid: float | None, ask: float | None, mark: float | None) -> float | None:
    if bid is not None and ask is not None and ask >= bid:
        return (bid + ask) / 2
    return mark


def _premium_usd(
    value: float | None,
    premium_currency: str,
    underlying: float | None,
) -> float | None:
    if value is None:
        return None
    if premium_currency == "BTC":
        return value * underlying if underlying is not None else None
    return value


def _missing(mapping: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if mapping.get(field) is None]


def normalize_deribit_option(
    item: dict[str, Any],
    *,
    collected_at: datetime | None = None,
) -> NormalizedOptionQuote:
    instrument = str(item.get("instrument_name") or "")
    parts = instrument.split("-")
    if len(parts) < 4:
        raise ValueError(f"invalid Deribit option instrument: {instrument}")
    expiry = datetime.strptime(parts[1], "%d%b%y").date().isoformat()
    strike = float(parts[2])
    option_type = "call" if parts[3].upper() == "C" else "put"
    underlying = _float(item.get("underlying_price"))
    native_bid = _float(item.get("bid_price"))
    native_ask = _float(item.get("ask_price"))
    native_mark = _float(item.get("mark_price"))

    def usd(value: float | None) -> float | None:
        return value * underlying if value is not None and underlying is not None else None

    greeks = item.get("greeks") or {}
    values = {
        "bid": usd(native_bid),
        "ask": usd(native_ask),
        "mark_price": usd(native_mark),
        "underlying_price": underlying,
        "iv": _iv(item.get("mark_iv")),
        "delta": _float(greeks.get("delta")),
        "open_interest": _float(item.get("open_interest")),
    }
    return NormalizedOptionQuote(
        provider="deribit",
        instrument=instrument,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        **values,
        mid=_mid(values["bid"], values["ask"], values["mark_price"]),
        native_bid=native_bid,
        native_ask=native_ask,
        native_mark=native_mark,
        premium_currency="BTC",
        gamma=_float(greeks.get("gamma")),
        theta=_float(greeks.get("theta")),
        vega=_float(greeks.get("vega")),
        volume_24h=_float(item.get("volume")),
        provider_timestamp=_timestamp(item.get("timestamp")),
        collected_at=collected_at or _utc_now(),
        conversion="BTC premium × underlying USD",
        missing_fields=_missing(
            values, ("bid", "ask", "mark_price", "underlying_price", "iv", "delta", "open_interest")
        ),
        raw_units={"premium": "BTC", "open_interest": "BTC contracts"},
    )


def normalize_okx_options(
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    *,
    collected_at: datetime | None = None,
) -> list[NormalizedOptionQuote]:
    instrument_map = {str(item.get("instId")): item for item in instruments}
    summary_map = {str(item.get("instId")): item for item in summaries}
    output: list[NormalizedOptionQuote] = []
    for ticker in tickers:
        instrument_id = str(ticker.get("instId") or "")
        instrument = instrument_map.get(instrument_id, {})
        summary = summary_map.get(instrument_id, {})
        parts = instrument_id.split("-")
        if len(parts) < 5 or parts[0] != "BTC":
            continue
        expiry = datetime.strptime(parts[-3], "%y%m%d").date().isoformat()
        strike = _float(instrument.get("stk")) or _float(parts[-2])
        if strike is None:
            continue
        option_type = (
            "call"
            if str(instrument.get("optType") or parts[-1]).upper() == "C"
            else "put"
        )
        underlying = _float(ticker.get("idxPx")) or _float(summary.get("fwdPx"))
        native_bid = _float(ticker.get("bidPx"))
        native_ask = _float(ticker.get("askPx"))
        native_mark = _float(ticker.get("markPx"))
        premium_currency = "BTC" if "-USD-" in instrument_id else "USDT"

        delta_bs = _float(summary.get("deltaBS"))
        delta_pa = _float(summary.get("deltaPA"))
        quality_notes = ["greeks_pa_fallback"] if delta_bs is None and delta_pa is not None else []
        bid = _premium_usd(native_bid, premium_currency, underlying)
        ask = _premium_usd(native_ask, premium_currency, underlying)
        mark = _premium_usd(native_mark, premium_currency, underlying)
        values = {
            "bid": bid,
            "ask": ask,
            "mark_price": mark,
            "underlying_price": underlying,
            "iv": _iv(summary.get("markVol") or ticker.get("markVol")),
            "delta": delta_bs if delta_bs is not None else delta_pa,
            "open_interest": _float(ticker.get("oi")),
        }
        output.append(
            NormalizedOptionQuote(
                provider="okx",
                instrument=instrument_id,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                **values,
                mid=_mid(bid, ask, mark),
                native_bid=native_bid,
                native_ask=native_ask,
                native_mark=native_mark,
                premium_currency=premium_currency,
                gamma=_float(summary.get("gammaBS") or summary.get("gammaPA")),
                theta=_float(summary.get("thetaBS") or summary.get("thetaPA")),
                vega=_float(summary.get("vegaBS") or summary.get("vegaPA")),
                volume_24h=_float(ticker.get("vol24h")),
                provider_timestamp=_timestamp(ticker.get("ts")),
                collected_at=collected_at or _utc_now(),
                conversion=(
                    "BTC premium × index USD"
                    if premium_currency == "BTC"
                    else "native USD"
                ),
                quality_notes=quality_notes,
                missing_fields=_missing(
                    values,
                    (
                        "bid",
                        "ask",
                        "mark_price",
                        "underlying_price",
                        "iv",
                        "delta",
                        "open_interest",
                    ),
                ),
            )
        )
    return output


def normalize_binance_perp(
    premium: dict[str, Any],
    *,
    open_interest: dict[str, Any],
    ticker: dict[str, Any],
    collected_at: datetime | None = None,
) -> NormalizedPerpSnapshot:
    mark = _float(premium.get("markPrice"))
    oi_contracts = _float(open_interest.get("openInterest"))
    values = {
        "mark_price": mark,
        "index_price": _float(premium.get("indexPrice")),
        "funding_rate": _float(premium.get("lastFundingRate")),
        "open_interest_contracts": oi_contracts,
        "open_interest_usd": (
            oi_contracts * mark if oi_contracts is not None and mark is not None else None
        ),
        "volume_24h_usd": _float(ticker.get("quoteVolume")),
    }
    return NormalizedPerpSnapshot(
        provider="binance_futures",
        instrument=str(premium.get("symbol") or "BTCUSDT"),
        **values,
        provider_timestamp=_timestamp(premium.get("time")),
        collected_at=collected_at or _utc_now(),
        conversion="base-asset OI × mark USD",
        missing_fields=_missing(
            values,
            (
                "mark_price",
                "index_price",
                "funding_rate",
                "open_interest_contracts",
                "open_interest_usd",
            ),
        ),
        raw_units={"open_interest_contracts": "BTC", "volume_24h_usd": "USDT"},
    )


def normalize_simple_perp(
    provider: str,
    instrument: str,
    *,
    mark_price: Any = None,
    index_price: Any = None,
    funding_rate: Any = None,
    open_interest_contracts: Any = None,
    open_interest_usd: Any = None,
    volume_24h_usd: Any = None,
    timestamp: Any = None,
    contract_multiplier: float = 1,
    collected_at: datetime | None = None,
) -> NormalizedPerpSnapshot:
    mark = _float(mark_price)
    contracts = _float(open_interest_contracts)
    oi_usd = _float(open_interest_usd)
    conversion = "provider USD field"
    if oi_usd is None and contracts is not None and mark is not None:
        oi_usd = contracts * mark * contract_multiplier
        conversion = "contracts × multiplier × mark USD"
    values = {
        "mark_price": mark,
        "index_price": _float(index_price),
        "funding_rate": _float(funding_rate),
        "open_interest_contracts": contracts,
        "open_interest_usd": oi_usd,
        "volume_24h_usd": _float(volume_24h_usd),
    }
    return NormalizedPerpSnapshot(
        provider=provider,
        instrument=instrument,
        **values,
        provider_timestamp=_timestamp(timestamp),
        collected_at=collected_at or _utc_now(),
        conversion=conversion,
        missing_fields=_missing(
            values,
            ("mark_price", "funding_rate", "open_interest_contracts", "open_interest_usd"),
        ),
    )


def normalize_bybit_options(
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    *,
    collected_at: datetime | None = None,
) -> list[NormalizedOptionQuote]:
    instrument_map = {str(item.get("symbol")): item for item in instruments}
    output: list[NormalizedOptionQuote] = []
    for ticker in tickers:
        symbol = str(ticker.get("symbol") or "")
        parts = symbol.split("-")
        if len(parts) < 4 or parts[0] != "BTC":
            continue
        try:
            expiry = datetime.strptime(parts[1], "%d%b%y").date().isoformat()
            strike = float(parts[2])
        except (ValueError, IndexError):
            continue
        instrument = instrument_map.get(symbol, {})
        bid = _float(ticker.get("bid1Price"))
        ask = _float(ticker.get("ask1Price"))
        mark = _float(ticker.get("markPrice"))
        underlying = _float(ticker.get("underlyingPrice"))
        values = {
            "bid": bid,
            "ask": ask,
            "mark_price": mark,
            "underlying_price": underlying,
            "iv": _iv(ticker.get("markIv")),
            "delta": _float(ticker.get("delta")),
            "open_interest": _float(ticker.get("openInterest")),
        }
        output.append(
            NormalizedOptionQuote(
                provider="bybit",
                instrument=symbol,
                expiry=expiry,
                strike=strike,
                option_type="call" if parts[3].upper() == "C" else "put",
                **values,
                mid=_mid(bid, ask, mark),
                native_bid=bid,
                native_ask=ask,
                native_mark=mark,
                premium_currency=str(instrument.get("settleCoin") or "USDC"),
                gamma=_float(ticker.get("gamma")),
                theta=_float(ticker.get("theta")),
                vega=_float(ticker.get("vega")),
                volume_24h=_float(ticker.get("volume24h")),
                provider_timestamp=_timestamp(ticker.get("timestamp")),
                collected_at=collected_at or _utc_now(),
                conversion="native USD stablecoin",
                missing_fields=_missing(
                    values,
                    (
                        "bid",
                        "ask",
                        "mark_price",
                        "underlying_price",
                        "iv",
                        "delta",
                        "open_interest",
                    ),
                ),
            )
        )
    return output
