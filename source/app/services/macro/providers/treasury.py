from __future__ import annotations

import time
from datetime import datetime, timezone

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc


class TreasuryMacroProvider:
    provider_key = "treasury_fiscaldata"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in (
            "raw_series",
            "release_series",
        )

    async def _fetch(self, endpoint: str, params: dict):
        cache_key = f"treasury:{endpoint}"
        if self.cache:
            cached = self.cache.get("treasury_fiscaldata", cache_key, params)
            if cached is not None:
                return cached, 0, True

        url = f"{self.base_url}{endpoint}"
        start = time.time()
        async with client_for_source("treasury", timeout=30) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            raise RuntimeError("Treasury rate limited")
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("treasury_fiscaldata", cache_key, params, data, 43200)

        return data, latency, False

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        if source_key == "debt_to_penny":
            data, _, _ = await self._fetch(
                "/v2/accounting/od/debt_to_penny", {"page[size]": 1, "sort": "-record_date"}
            )
            records = data.get("data", [])
            if not records:
                raise ValueError("No Treasury debt records")
            latest = records[0]
            return MacroFetchResult(
                observation_ts=datetime.fromisoformat(
                    f"{latest['record_date']}T00:00:00+00:00"
                ).astimezone(UTC),
                value=D(str(latest.get("total_prin_amt", 0))),
                source_ref=source_key,
                source_granularity="1d",
            )
        if source_key == "daily_treasury_rates":
            data, _, _ = await self._fetch(
                "/v2/accounting/od/avg_interest_rates", {"page[size]": 5, "sort": "-record_date"}
            )
            records = data.get("data", [])
            if not records:
                raise ValueError("No Treasury rate records")
            latest = records[0]
            return MacroFetchResult(
                observation_ts=datetime.fromisoformat(
                    f"{latest['record_date']}T00:00:00+00:00"
                ).astimezone(UTC),
                value=D(str(latest.get("avg_interest_rate_amt", 0))),
                source_ref=source_key,
                source_granularity="1d",
            )
        if source_key == "tga":
            data, _, _ = await self._fetch(
                "/v2/accounting/od/daily_treasury_statement",
                {"page[size]": 3, "sort": "-record_date"},
            )
            records = data.get("data", [])
            if not records:
                raise ValueError("No Treasury statement records")
            latest = records[0]
            return MacroFetchResult(
                observation_ts=datetime.fromisoformat(
                    f"{latest['record_date']}T00:00:00+00:00"
                ).astimezone(UTC),
                value=D(str(latest.get("close_bal_amt", 0))),
                source_ref=source_key,
                source_granularity="1d",
            )
        raise ValueError(f"Unknown Treasury source_key: {source_key}")

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self._fetch("/v2/accounting/od/debt_to_penny", {"page[size]": 1})
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            await self._fetch("/v2/accounting/od/debt_to_penny", {"page[size]": 1})
            return {
                "source": "treasury_fiscaldata",
                "status": "ok",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "not_required",
                "error": None,
            }
        except Exception as exc:
            return {
                "source": "treasury_fiscaldata",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "not_required",
                "error": str(exc)[:200],
            }
