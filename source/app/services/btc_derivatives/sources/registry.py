from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    capability: str
    method: str
    path: str
    ttl_seconds: int
    params: dict[str, str] | None = None
    json_body: dict[str, object] | None = None


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    capabilities: tuple[str, ...]
    endpoints: tuple[EndpointSpec, ...]
    requires_auth: bool = False


PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    "deribit": ProviderSpec(
        "deribit",
        "Deribit",
        "https://www.deribit.com",
        ("options", "perps", "futures"),
        (
            EndpointSpec(
                "instruments",
                "options",
                "GET",
                "/api/v2/public/get_instruments",
                21600,
                {"currency": "BTC", "kind": "option", "expired": "false"},
            ),
            EndpointSpec(
                "option_book",
                "options",
                "GET",
                "/api/v2/public/get_book_summary_by_currency",
                120,
                {"currency": "BTC", "kind": "option"},
            ),
            EndpointSpec(
                "future_book",
                "perps",
                "GET",
                "/api/v2/public/get_book_summary_by_currency",
                60,
                {"currency": "BTC", "kind": "future"},
            ),
        ),
    ),
    "okx": ProviderSpec(
        "okx",
        "OKX",
        "https://www.okx.com",
        ("options", "perps", "futures"),
        (
            EndpointSpec(
                "option_instruments",
                "options",
                "GET",
                "/api/v5/public/instruments",
                21600,
                {"instType": "OPTION", "uly": "BTC-USD"},
            ),
            EndpointSpec(
                "option_tickers",
                "options",
                "GET",
                "/api/v5/market/tickers",
                120,
                {"instType": "OPTION", "uly": "BTC-USD"},
            ),
            EndpointSpec(
                "option_summary",
                "options",
                "GET",
                "/api/v5/public/opt-summary",
                120,
                {"uly": "BTC-USD"},
            ),
            EndpointSpec(
                "swap_tickers",
                "perps",
                "GET",
                "/api/v5/market/tickers",
                60,
                {"instType": "SWAP"},
            ),
            EndpointSpec(
                "open_interest",
                "perps",
                "GET",
                "/api/v5/public/open-interest",
                60,
                {"instType": "SWAP", "uly": "BTC-USDT"},
            ),
        ),
    ),
    "bybit": ProviderSpec(
        "bybit",
        "Bybit",
        "https://api.bybit.com",
        ("options", "perps"),
        (
            EndpointSpec(
                "option_instruments",
                "options",
                "GET",
                "/v5/market/instruments-info",
                21600,
                {"category": "option", "baseCoin": "BTC"},
            ),
            EndpointSpec(
                "option_tickers",
                "options",
                "GET",
                "/v5/market/tickers",
                120,
                {"category": "option", "baseCoin": "BTC"},
            ),
            EndpointSpec(
                "linear_tickers",
                "perps",
                "GET",
                "/v5/market/tickers",
                60,
                {"category": "linear", "symbol": "BTCUSDT"},
            ),
        ),
    ),
    "binance_futures": ProviderSpec(
        "binance_futures",
        "Binance Futures",
        "https://fapi.binance.com",
        ("perps", "history"),
        (
            EndpointSpec(
                "premium_index",
                "perps",
                "GET",
                "/fapi/v1/premiumIndex",
                30,
                {"symbol": "BTCUSDT"},
            ),
            EndpointSpec(
                "open_interest",
                "perps",
                "GET",
                "/fapi/v1/openInterest",
                60,
                {"symbol": "BTCUSDT"},
            ),
            EndpointSpec(
                "ticker_24h",
                "perps",
                "GET",
                "/fapi/v1/ticker/24hr",
                60,
                {"symbol": "BTCUSDT"},
            ),
            EndpointSpec(
                "funding_history",
                "history",
                "GET",
                "/fapi/v1/fundingRate",
                900,
                {"symbol": "BTCUSDT", "limit": "1000"},
            ),
            EndpointSpec(
                "oi_history",
                "history",
                "GET",
                "/futures/data/openInterestHist",
                1800,
                {"symbol": "BTCUSDT", "period": "1d", "limit": "90"},
            ),
            EndpointSpec(
                "mark_history",
                "history",
                "GET",
                "/fapi/v1/markPriceKlines",
                1800,
                {"symbol": "BTCUSDT", "interval": "1d", "limit": "90"},
            ),
        ),
    ),
    "bitget": ProviderSpec(
        "bitget",
        "Bitget",
        "https://api.bitget.com",
        ("perps",),
        (
            EndpointSpec(
                "ticker",
                "perps",
                "GET",
                "/api/v2/mix/market/ticker",
                60,
                {"symbol": "BTCUSDT", "productType": "USDT-FUTURES"},
            ),
            EndpointSpec(
                "funding",
                "perps",
                "GET",
                "/api/v2/mix/market/current-fund-rate",
                60,
                {"symbol": "BTCUSDT", "productType": "USDT-FUTURES"},
            ),
            EndpointSpec(
                "open_interest",
                "perps",
                "GET",
                "/api/v2/mix/market/open-interest",
                60,
                {"symbol": "BTCUSDT", "productType": "USDT-FUTURES"},
            ),
        ),
    ),
    "hyperliquid": ProviderSpec(
        "hyperliquid",
        "Hyperliquid",
        "https://api.hyperliquid.xyz",
        ("perps",),
        (
            EndpointSpec(
                "meta_and_contexts",
                "perps",
                "POST",
                "/info",
                60,
                json_body={"type": "metaAndAssetCtxs"},
            ),
        ),
    ),
}
