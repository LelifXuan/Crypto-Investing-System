from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.services.btc_derivatives.sources.http import SourceHttpClient
from app.services.btc_derivatives.sources.registry import EndpointSpec, ProviderSpec
from app.services.volatility_research.estimators import safe_decimal

UTC = timezone.utc
# Verified against the public history endpoint. ``BVIV30D`` looks plausible
# but is rejected by the provider and must not be allowed as a configured key.
ALLOWED_SYMBOLS = frozenset({"BVIV", "BVRV30D"})


@dataclass(frozen=True, slots=True)
class VolmexCandle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class VolmexVolatilityClient:
    """Public Volmex history adapter with source identity preserved."""

    provider = ProviderSpec(
        key="volmex",
        label="Volmex",
        base_url="https://rest-v1.volmex.finance",
        capabilities=("implied_volatility", "realized_volatility"),
        endpoints=(),
    )

    def __init__(self, http: SourceHttpClient | None = None) -> None:
        self.http = http or SourceHttpClient()

    async def fetch(
        self,
        *,
        symbol: str,
        start_seconds: int,
        end_seconds: int,
        resolution: str = "60",
    ) -> list[VolmexCandle]:
        normalized_symbol = symbol.upper()
        if normalized_symbol not in ALLOWED_SYMBOLS:
            raise ValueError(f"unsupported Volmex research symbol: {symbol}")
        endpoint = EndpointSpec(
            name=f"volmex_{normalized_symbol.lower()}_history",
            capability="implied_volatility",
            method="GET",
            path="/v2/history",
            ttl_seconds=60,
            params={
                "symbol": normalized_symbol,
                "resolution": resolution,
                "from": str(start_seconds),
                "to": str(end_seconds),
            },
        )
        payload, latency_ms, _ = await self.http.request(
            self.provider, endpoint, decimal_json=True
        )
        timestamps = (payload or {}).get("t") or []
        series = [(payload or {}).get(key) or [] for key in ("o", "h", "l", "c")]
        output: list[VolmexCandle] = []
        for index, raw_timestamp in enumerate(timestamps):
            if any(index >= len(values) for values in series):
                continue
            values = [safe_decimal(items[index]) for items in series]
            if any(value is None for value in values):
                continue
            output.append(
                VolmexCandle(
                    timestamp=datetime.fromtimestamp(int(raw_timestamp), tz=UTC),
                    open=values[0],
                    high=values[1],
                    low=values[2],
                    close=values[3],
                )
            )
        self.http.record_success(self.provider.key, latency_ms)
        return output
