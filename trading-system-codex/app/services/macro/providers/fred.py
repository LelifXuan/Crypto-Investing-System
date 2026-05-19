from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

import httpx

from app.core.config import settings
from app.core.decimal_utils import D
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader

UTC = timezone.utc


class FredMacroProvider:
    provider_key = "fred"
    official_url = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, secrets: SecretLoader | None = None) -> None:
        self.secrets = secrets or SecretLoader()

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "raw_series"

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        api_key = self.secrets.get("FRED_API_KEY")
        if api_key:
            try:
                return await self._fetch_official_json(source_key, api_key)
            except (httpx.HTTPError, ValueError):
                # FRED CSV is kept as a public fallback for local/offline-friendly runs.
                return await self._fetch_public_csv(source_key)
        return await self._fetch_public_csv(source_key)

    async def _fetch_official_json(self, source_key: str, api_key: str) -> MacroFetchResult:
        params = {
            "series_id": source_key,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 20,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.official_url, params=params)
            response.raise_for_status()
        observations = response.json().get("observations") or []
        for row in observations:
            value = row.get("value")
            date_value = row.get("date")
            if not value or value == "." or not date_value:
                continue
            return MacroFetchResult(
                observation_ts=datetime.fromisoformat(f"{date_value}T00:00:00+00:00").astimezone(
                    UTC
                ),
                value=D(value),
                source_ref=f"fred:{source_key}",
                source_granularity="1d",
            )
        raise ValueError(f"no fred observation for {source_key}")

    async def _fetch_public_csv(self, source_key: str) -> MacroFetchResult:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(settings.fred_public_csv_url, params={"id": source_key})
            response.raise_for_status()
        rows = list(csv.DictReader(StringIO(response.text)))
        if not rows:
            raise ValueError(f"no fred rows for {source_key}")
        date_field = next(
            (
                key
                for key in rows[0].keys()
                if str(key).strip().lower() in {"date", "observation_date"}
            ),
            None,
        )
        if date_field is None:
            raise ValueError(f"no date column for {source_key}")
        value_field = (
            source_key
            if source_key in rows[0]
            else next(
                (
                    key
                    for key in rows[0].keys()
                    if str(key).strip().lower() == str(source_key).strip().lower()
                ),
                None,
            )
        )
        if value_field is None:
            raise ValueError(f"no value column for {source_key}")
        for row in reversed(rows):
            value = row.get(value_field)
            date_value = row.get(date_field)
            if not value or value == "." or not date_value:
                continue
            return MacroFetchResult(
                observation_ts=datetime.fromisoformat(f"{date_value}T00:00:00+00:00").astimezone(
                    UTC
                ),
                value=D(value),
                source_ref=f"fred_public_csv:{source_key}",
                source_granularity="1d",
            )
        raise ValueError(f"no fred observation for {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        if self.secrets.auth_state(["FRED_API_KEY"]) == "missing":
            return "auth_missing", None
        return "healthy", None
