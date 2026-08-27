from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.services.btc_derivatives.sources.http import SourceHttpClient
from app.services.btc_derivatives.sources.registry import EndpointSpec, ProviderSpec
from app.services.volatility_research.estimators import safe_decimal

UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class DvolCandle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class DeribitDvolClient:
    """Public DVOL history adapter; it is research-only and never backfills silently."""

    provider = ProviderSpec(
        key="deribit_dvol",
        label="Deribit DVOL",
        base_url="https://www.deribit.com",
        capabilities=("implied_volatility",),
        endpoints=(),
    )

    def __init__(self, http: SourceHttpClient | None = None) -> None:
        self.http = http or SourceHttpClient()

    async def fetch(
        self, *, start_ms: int, end_ms: int, resolution: str = "3600"
    ) -> list[DvolCandle]:
        endpoint = EndpointSpec(
            name="btc_dvol_history",
            capability="implied_volatility",
            method="GET",
            path="/api/v2/public/get_volatility_index_data",
            ttl_seconds=60,
            params={
                "currency": "BTC",
                "start_timestamp": str(start_ms),
                "end_timestamp": str(end_ms),
                "resolution": resolution,
            },
        )
        payload, latency_ms, _ = await self.http.request(
            self.provider, endpoint, decimal_json=True
        )
        rows = ((payload or {}).get("result") or {}).get("data") or []
        output: list[DvolCandle] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 5:
                continue
            values = [safe_decimal(value) for value in row[1:5]]
            if any(value is None for value in values):
                continue
            output.append(
                DvolCandle(
                    timestamp=datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC),
                    open=values[0],
                    high=values[1],
                    low=values[2],
                    close=values[3],
                )
            )
        self.http.record_success(self.provider.key, latency_ms)
        return output
