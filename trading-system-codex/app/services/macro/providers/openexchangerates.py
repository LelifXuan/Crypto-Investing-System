from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc


class OpenExchangeRatesMacroProvider:
    provider_key = "openexchangerates"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://openexchangerates.org/api"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    def _app_id(self) -> str:
        return self.secrets.get("OPENEXCHANGERATES_APP_ID", required=True) or ""

    async def _request(self, endpoint: str, params: dict = None):
        cache_key = f"oer:{endpoint}"
        cache_params = params or {}
        if self.cache:
            cached = self.cache.get("openexchangerates", cache_key, cache_params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with client_for_source("openexchangerates", timeout=20) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("OER rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("OER auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("openexchangerates", cache_key, cache_params, data, 21600)

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        data, _, _ = await self._request("/latest.json", {"app_id": self._app_id()})
        rate = float(data.get("rates", {}).get(source_key, 0))
        return MacroFetchResult(
            observation_ts=datetime.now(UTC),
            value=D(str(rate)),
            source_ref=source_key,
            source_granularity="1d",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self._request("/latest.json", {"app_id": self._app_id()})
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._request("/latest.json", {"app_id": self._app_id()})
            return {
                "source": "openexchangerates",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "present",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "openexchangerates",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": self.secrets.auth_state({"OPENEXCHANGERATES_APP_ID"}),
                "error": str(exc)[:200],
            }
