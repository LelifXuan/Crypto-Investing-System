from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc


def _parse_iso_dt(value: str) -> datetime:
    if not value:
        raise ValueError("empty date")
    v = str(value).strip()
    if "T" in v:
        return datetime.fromisoformat(v).astimezone(UTC)
    return datetime.fromisoformat(f"{v}T00:00:00+00:00").astimezone(UTC)


class TwelveDataMacroProvider:
    provider_key = "twelvedata"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.twelvedata.com"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    def _apikey(self) -> str:
        return self.secrets.get("TWELVEDATA_API_KEY", required=True) or ""

    async def _request(self, endpoint: str, params: dict = None):
        cache_key = f"td:{endpoint}"
        cache_params = params or {}
        if self.cache:
            cached = self.cache.get("twelvedata", cache_key, cache_params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with client_for_source("twelvedata", timeout=20) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("TwelveData rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("TwelveData auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("twelvedata", cache_key, cache_params, data, 3600)

        if data.get("status") == "error":
            raise RuntimeError(f"TwelveData error: {data.get('message', 'unknown')}")

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        parts = source_key.split(":")
        symbol = parts[0] if parts else ""
        interval = parts[1] if len(parts) > 1 else "1day"
        data, _, _ = await self._request(
            "/time_series",
            {"symbol": symbol, "interval": interval, "outputsize": 5, "apikey": self._apikey()},
        )
        values = data.get("values", [])
        if not values:
            raise ValueError(f"TwelveData empty for {source_key}")
        rows = sorted(values, key=lambda x: x.get("datetime", ""))
        latest = rows[-1]
        return MacroFetchResult(
            observation_ts=_parse_iso_dt(str(latest.get("datetime", ""))),
            value=D(str(latest.get("close", 0))),
            source_ref=source_key,
            source_granularity="1d",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self._request(
                "/time_series",
                {"symbol": "SPY", "interval": "1day", "outputsize": 1, "apikey": self._apikey()},
            )
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._request(
                "/time_series",
                {"symbol": "SPY", "interval": "1day", "outputsize": 1, "apikey": self._apikey()},
            )
            return {
                "source": "twelvedata",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "present",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "twelvedata",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": self.secrets.auth_state({"TWELVEDATA_API_KEY"}),
                "error": str(exc)[:200],
            }
