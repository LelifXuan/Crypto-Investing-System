from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.services.macro.cache_store import CacheStore
from app.services.macro.secret_loader import SecretLoader
from app.services.macro.providers.base import MacroFetchResult
from app.core.decimal_utils import D

UTC = timezone.utc


class TiingoMacroProvider:
    provider_key = "tiingo"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.tiingo.com"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in ("raw_series", "release_series")

    async def _request(self, endpoint: str, params: dict = None):
        cache_key = f"tiingo:{endpoint}"
        cache_params = params or {}
        if self.cache:
            cached = self.cache.get("tiingo", cache_key, cache_params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("Tiingo rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("Tiingo auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("tiingo", cache_key, cache_params, data, 21600)

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        ticker = source_key
        key = self.secrets.get("TIINGO_API_KEY", required=True) or ""
        data, _, _ = await self._request(
            f"/tiingo/daily/{ticker}/prices",
            {"resampleFreq": "daily", "token": key},
        )
        if not isinstance(data, list) or not data:
            raise ValueError(f"Tiingo empty response for {ticker}")
        rows = sorted(data, key=lambda x: x.get("date", ""))
        latest = rows[-1]
        return MacroFetchResult(
            observation_ts=datetime.fromisoformat(f"{latest['date']}T00:00:00+00:00").astimezone(UTC),
            value=D(str(latest.get("close", 0))),
            source_ref=source_key,
            source_granularity="1d",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            key = self.secrets.get("TIINGO_API_KEY", required=True) or ""
            await self._request("/tiingo/daily/SPY/prices", {"resampleFreq": "daily", "token": key})
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            key = self.secrets.get("TIINGO_API_KEY", required=True) or ""
            await self._request("/tiingo/daily/SPY/prices", {"resampleFreq": "daily", "token": key})
            return {"source": "tiingo", "status": "ok", "latency_ms": int((time.time() - start) * 1000), "auth": "present", "error": None}
        except Exception as exc:
            return {"source": "tiingo", "status": "error", "latency_ms": int((time.time() - start) * 1000), "auth": self.secrets.auth_state({"TIINGO_API_KEY"}), "error": str(exc)[:200]}
