from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.services.macro.cache_store import CacheStore
from app.services.macro.secret_loader import SecretLoader
from app.services.macro.providers.base import MacroFetchResult
from app.core.decimal_utils import D

UTC = timezone.utc


class ZhituapiMacroProvider:
    provider_key = "zhituapi"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.zhituapi.com"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in ("raw_series", "release_series")

    def _token(self) -> str:
        return self.secrets.get("ZHITUAPI_TOKEN", required=False) or ""

    async def _request(self, endpoint: str, params: dict = None):
        params = params or {}
        cache_key = f"zhituapi:{endpoint}"
        if self.cache:
            cached = self.cache.get("zhituapi", cache_key, params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("zhituapi rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("zhituapi auth failed")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("zhituapi", cache_key, params, data, 3600)

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        raise NotImplementedError(f"zhituapi fetch_latest not yet implemented for {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        token = self._token()
        if not token:
            return "auth_missing", "ZHITUAPI_TOKEN not set"
        try:
            data, _, _ = await self._request("/fund/list/etf", {"token": token})
            if isinstance(data, list) or (isinstance(data, dict) and data.get("code") == 200):
                return "healthy", None
            return "unhealthy", f"Unexpected response: {str(data)[:200]}"
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        token = self._token()
        if not token:
            return {"source": "zhituapi", "status": "auth_missing", "latency_ms": 0, "auth": "missing", "error": "ZHITUAPI_TOKEN not set"}
        start = time.time()
        try:
            data, latency, _ = await self._request("/fund/list/etf", {"token": token})
            return {"source": "zhituapi", "status": "ok", "latency_ms": latency, "auth": "present", "error": None}
        except Exception as exc:
            return {"source": "zhituapi", "status": "error", "latency_ms": int((time.time() - start) * 1000), "auth": "present", "error": str(exc)[:200]}
