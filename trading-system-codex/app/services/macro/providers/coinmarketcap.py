from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc


class CoinMarketCapMacroProvider:
    provider_key = "coinmarketcap"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://pro-api.coinmarketcap.com"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    def _headers(self) -> dict:
        key = self.secrets.get("COINMARKETCAP_API_KEY", required=True) or ""
        return {"X-CMC_PRO_API_KEY": key, "Accept": "application/json"}

    async def _request(self, endpoint: str, params: dict = None):
        cache_endpoint = f"cmc:{endpoint}"
        cache_params = params or {}
        if self.cache:
            cached = self.cache.get("coinmarketcap", cache_endpoint, cache_params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with client_for_source("coinmarketcap", timeout=20) as client:
            resp = await client.get(url, params=params, headers=self._headers())
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("CMC rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("CMC auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("coinmarketcap", cache_endpoint, cache_params, data, 900)

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        if source_key == "btc_dominance":
            data, _, _ = await self._request("/v1/global-metrics/quotes/latest")
            value = float(data.get("data", {}).get("btc_dominance", 0))
            return MacroFetchResult(
                observation_ts=datetime.now(UTC),
                value=D(str(value)),
                source_ref=source_key,
                source_granularity="1d",
            )
        parts = source_key.split(":")
        symbol = parts[0] if parts else "BTC"
        convert = parts[1] if len(parts) > 1 else "USD"
        data, _, _ = await self._request(
            "/v2/cryptocurrency/quotes/latest",
            {"symbol": symbol, "convert": convert},
        )
        rows = data.get("data", {}).get(symbol, [])
        row = rows[0] if rows else {}
        value = float(row.get("quote", {}).get(convert, {}).get("price", 0))
        return MacroFetchResult(
            observation_ts=datetime.now(UTC),
            value=D(str(value)),
            source_ref=source_key,
            source_granularity="1d",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self._request("/v1/global-metrics/quotes/latest")
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._request("/v1/global-metrics/quotes/latest")
            return {
                "source": "coinmarketcap",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "present",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "coinmarketcap",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": self.secrets.auth_state({"COINMARKETCAP_API_KEY"}),
                "error": str(exc)[:200],
            }
