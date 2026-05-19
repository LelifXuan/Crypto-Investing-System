from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.services.macro.cache_store import CacheStore
from app.services.macro.secret_loader import SecretLoader
from app.services.macro.providers.base import MacroFetchResult
from app.core.decimal_utils import D

UTC = timezone.utc


class AlphaVantageMacroProvider:
    provider_key = "alpha_vantage"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://www.alphavantage.co/query"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in ("raw_series", "release_series")

    def _apikey(self) -> str:
        return self.secrets.get("ALPHA_VANTAGE_API_KEY", required=True) or ""

    async def _request(self, params: dict):
        cache_key = f"av:{params.get('function')}:{params.get('symbol', params.get('from_symbol', ''))}"
        if self.cache:
            cached = self.cache.get("alpha_vantage", cache_key, params)
            if cached is not None:
                return cached, 0, True

        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("AlphaVantage rate limited")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("alpha_vantage", cache_key, params, data, 21600)

        if data.get("Note") or data.get("Information"):
            raise RuntimeError(f"AlphaVantage rate limited: {data.get('Note') or data.get('Information')}")

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        parts = source_key.split(":")
        function = parts[0] if parts else "TIME_SERIES_DAILY"
        symbol = parts[1] if len(parts) > 1 else ""
        params = {"function": function, "apikey": self._apikey()}
        if function == "FX_DAILY" and len(parts) >= 3:
            params["from_symbol"] = parts[1]
            params["to_symbol"] = parts[2]
        elif symbol:
            params["symbol"] = symbol

        data, _, _ = await self._request(params)
        ts = data.get("Time Series (Daily)") or data.get("Time Series FX (Daily)") or {}
        if not ts:
            raise ValueError(f"AlphaVantage empty for {source_key}")
        dates = sorted(ts.keys())
        latest_row = ts[dates[-1]]
        return MacroFetchResult(
            observation_ts=datetime.fromisoformat(f"{dates[-1]}T00:00:00+00:00").astimezone(UTC),
            value=D(str(latest_row.get("4. close", 0))),
            source_ref=source_key,
            source_granularity="1d",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self._request({"function": "FX_DAILY", "from_symbol": "USD", "to_symbol": "EUR", "apikey": self._apikey()})
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._request({"function": "FX_DAILY", "from_symbol": "USD", "to_symbol": "EUR", "apikey": self._apikey()})
            return {"source": "alpha_vantage", "status": "ok", "latency_ms": int((time.time() - start) * 1000), "auth": "present", "error": None}
        except Exception as exc:
            return {"source": "alpha_vantage", "status": "error", "latency_ms": int((time.time() - start) * 1000), "auth": self.secrets.auth_state({"ALPHA_VANTAGE_API_KEY"}), "error": str(exc)[:200]}
