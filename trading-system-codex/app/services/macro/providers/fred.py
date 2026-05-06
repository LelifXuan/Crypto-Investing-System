from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

import httpx

from app.core.config import settings
from app.core.decimal_utils import D
from app.services.macro.providers.base import MacroFetchResult


class FredMacroProvider:
    provider_key = "fred"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "raw_series"

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
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
                source_ref=source_key,
                source_granularity="1d",
            )
        raise ValueError(f"no fred observation for {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        return "healthy", None
