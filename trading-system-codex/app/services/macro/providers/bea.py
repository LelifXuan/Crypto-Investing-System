from __future__ import annotations

import time
from datetime import date, datetime, timezone

import httpx

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader

UTC = timezone.utc


class BeaMacroProvider:
    provider_key = "bea"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://apps.bea.gov/api/data"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    def _api_key(self) -> str:
        return self.secrets.get("BEA_API_KEY", required=True) or ""

    async def _fetch(self, params: dict):
        cache_key = (
            f"bea:{params.get('datasetname')}:{params.get('TableName')}:{params.get('LineNumber')}"
        )
        if self.cache:
            cached = self.cache.get("bea", cache_key, params)
            if cached is not None:
                return cached, 0, True

        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("BEA rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("BEA auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("bea", cache_key, params, data, 43200)

        return data, latency, False

    def _extract_points(self, data: dict) -> list[dict]:
        bea_api = data.get("BEAAPI", {})
        results = bea_api.get("Results", {})
        rows = results.get("Data", []) if isinstance(results, dict) else []
        points = []
        for row in rows:
            time_period = row.get("TimePeriod") or row.get("TimePeriodName")
            value = row.get("DataValue")
            if time_period:
                s = str(time_period)
                if "M" in s:
                    y, m = s.split("M", 1)
                    iso = date(int(y), int(m), 1).isoformat()
                elif "Q" in s:
                    y, q = s.split("Q", 1)
                    iso = date(int(y), 1 + (int(q) - 1) * 3, 1).isoformat()
                else:
                    try:
                        iso = date(int(s[:4]), 1, 1).isoformat()
                    except ValueError:
                        continue
                points.append({"date": iso, "value": value})
        return points

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        parts = source_key.split(":")
        datasetname = parts[0] if len(parts) > 0 else "NIPA"
        table_name = parts[1] if len(parts) > 1 else ""
        line_number = parts[2] if len(parts) > 2 else ""
        frequency = parts[3] if len(parts) > 3 else "M"

        params = {
            "UserID": self._api_key(),
            "method": "GetData",
            "datasetname": datasetname,
            "TableName": table_name,
            "LineNumber": line_number,
            "Frequency": frequency,
            "Year": "X",
            "ResultFormat": "JSON",
        }
        data, _, _ = await self._fetch(params)
        points = self._extract_points(data)
        valid = [(p["date"], p["value"]) for p in points if p.get("date") and p.get("value")]
        valid.sort(key=lambda x: x[0])
        if not valid:
            raise ValueError(f"No valid BEA observations for {source_key}")
        latest_date_str, latest_value = valid[-1]
        return MacroFetchResult(
            observation_ts=datetime.fromisoformat(f"{latest_date_str}T00:00:00+00:00").astimezone(
                UTC
            ),
            value=D(str(latest_value)),
            source_ref=source_key,
            source_granularity="1mo" if frequency == "M" else "1q",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        if self.secrets.auth_state({"BEA_API_KEY"}) == "missing":
            return "auth_missing", None
        try:
            params = {
                "UserID": self._api_key(),
                "method": "GETDATASETLIST",
                "ResultFormat": "JSON",
            }
            await self._fetch(params)
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            params = {
                "UserID": self._api_key(),
                "method": "GETDATASETLIST",
                "ResultFormat": "JSON",
            }
            await self._fetch(params)
            return {
                "source": "bea",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "present",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "bea",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": self.secrets.auth_state({"BEA_API_KEY"}),
                "error": str(exc)[:200],
            }
