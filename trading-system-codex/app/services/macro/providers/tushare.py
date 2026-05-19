from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.services.macro.cache_store import CacheStore
from app.services.macro.secret_loader import SecretLoader
from app.services.macro.providers.base import MacroFetchResult
from app.core.decimal_utils import D

UTC = timezone.utc


class TushareMacroProvider:
    provider_key = "tushare"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.tushare.pro"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in ("raw_series", "release_series")

    def _token(self) -> str:
        return self.secrets.get("TUSHARE_TOKEN", required=False) or ""

    async def _api_call(self, api_name: str, params: dict = None, fields: list = None) -> dict:
        payload = {
            "api_name": api_name,
            "token": self._token(),
            "params": params or {},
            "fields": fields or [],
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload)
        latency = int((time.time() - start) * 1000)
        if resp.status_code != 200:
            raise RuntimeError(f"Tushare HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        code = data.get("code", -1)
        if code != 0:
            raise RuntimeError(f"Tushare error code={code}: {data.get('msg', '')}")
        return {"data": data, "latency_ms": latency}

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        raise NotImplementedError(f"Tushare fetch_latest not yet implemented for {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        token = self._token()
        if not token:
            return "auth_missing", "TUSHARE_TOKEN not set"
        try:
            await self._api_call("stock_basic", {"exchange": "", "list_status": "L", "limit": 1}, ["ts_code", "name"])
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        token = self._token()
        if not token:
            return {"source": "tushare", "status": "auth_missing", "latency_ms": 0, "auth": "missing", "error": "TUSHARE_TOKEN not set"}
        start = time.time()
        try:
            await self._api_call("stock_basic", {"exchange": "", "list_status": "L", "limit": 1}, ["ts_code", "name"])
            return {"source": "tushare", "status": "ok", "latency_ms": int((time.time() - start) * 1000), "auth": "present", "error": None}
        except Exception as exc:
            return {"source": "tushare", "status": "error", "latency_ms": int((time.time() - start) * 1000), "auth": "present" if token else "missing", "error": str(exc)[:200]}
