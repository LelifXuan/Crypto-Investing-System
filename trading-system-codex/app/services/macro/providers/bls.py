from __future__ import annotations

import time
from datetime import date, datetime, timezone

import httpx

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader

UTC = timezone.utc


class BlsMacroProvider:
    provider_key = "bls"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    def _api_key(self) -> str:
        return self.secrets.get("BLS_API_KEY", required=True) or ""

    async def _fetch_series_json(self, series_id: str, startyear: str, endyear: str):
        cache_params = {"series_id": series_id, "startyear": startyear, "endyear": endyear}
        if self.cache:
            cached = self.cache.get("bls", f"timeseries:{series_id}", cache_params)
            if cached is not None:
                return cached, 0, True

        payload = {
            "seriesid": [series_id],
            "startyear": startyear,
            "endyear": endyear,
            "registrationkey": self._api_key(),
        }
        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("BLS rate limited")
        if resp.status_code in (401, 403):
            raise RuntimeError("BLS auth missing")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("bls", f"timeseries:{series_id}", cache_params, data, 43200)

        return data, latency, False

    def _normalize_points(self, data: dict) -> list[dict]:
        series = data.get("Results", {}).get("series", [])
        if not series:
            return []
        points = series[0].get("data", [])
        normalized = []
        for p in points:
            iso = self._parse_ym_period(str(p.get("year", "")), str(p.get("period", "")))
            normalized.append(
                {
                    "date": iso,
                    "value": p.get("value"),
                    "period": p.get("period"),
                    "year": p.get("year"),
                }
            )
        return normalized

    @staticmethod
    def _parse_ym_period(year_str: str, period: str) -> str | None:
        try:
            year = int(year_str)
        except ValueError:
            return None
        if period.startswith("M") and len(period) == 3:
            month = int(period[1:])
            return date(year, month, 1).isoformat()
        if period.startswith("Q") and len(period) == 3:
            q = int(period[1:])
            month = 1 + (q - 1) * 3
            return date(year, month, 1).isoformat()
        if period.startswith("A"):
            return date(year, 1, 1).isoformat()
        return None

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        this_year = date.today().year
        data, _, _ = await self._fetch_series_json(source_key, str(this_year - 3), str(this_year))
        points = self._normalize_points(data)
        valid = [(p["date"], p["value"]) for p in points if p.get("date") and p.get("value")]
        valid.sort(key=lambda x: x[0])
        if not valid:
            raise ValueError(f"No valid BLS observations for {source_key}")
        latest_date_str, latest_value = valid[-1]
        return MacroFetchResult(
            observation_ts=datetime.fromisoformat(f"{latest_date_str}T00:00:00+00:00").astimezone(
                UTC
            ),
            value=D(str(latest_value)),
            source_ref=source_key,
            source_granularity="1mo",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        if self.secrets.auth_state({"BLS_API_KEY"}) == "missing":
            return "auth_missing", None
        try:
            await self._fetch_series_json(
                "LNS14000000", str(date.today().year - 1), str(date.today().year)
            )
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._fetch_series_json(
                "LNS14000000", str(date.today().year - 1), str(date.today().year)
            )
            return {
                "source": "bls",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "present",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "bls",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": self.secrets.auth_state({"BLS_API_KEY"}),
                "error": str(exc)[:200],
            }
