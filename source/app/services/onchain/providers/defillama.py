from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class DefiLlamaSnapshot:
    status: str
    indicators: dict[str, float | None]
    missing_fields: list[str]
    source_provider: str = "defillama"


class DefiLlamaProvider:
    """No-key DefiLlama provider for low-frequency crypto fundamentals."""

    base_url = "https://api.llama.fi"
    stablecoins_url = "https://stablecoins.llama.fi"

    @staticmethod
    def metric_keys() -> set[str]:
        return {
            "defi_total_tvl",
            "stablecoin_total_mcap",
            "dex_volume_24h",
            "protocol_fees_24h",
        }

    async def fetch_snapshot(self, *, client: httpx.AsyncClient | None = None) -> DefiLlamaSnapshot:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=10)
        try:
            chains = await self._json(client, f"{self.base_url}/v2/chains")
            stablecoins = await self._json(client, f"{self.stablecoins_url}/stablecoins")
            overview = await self._json(client, f"{self.base_url}/overview/dexs")
            fees = await self._json(client, f"{self.base_url}/overview/fees")
        except (httpx.HTTPError, ValueError) as exc:
            return DefiLlamaSnapshot(
                status="degraded",
                indicators={},
                missing_fields=[f"network:{type(exc).__name__}"],
            )
        finally:
            if owns_client:
                await client.aclose()

        indicators = {
            "defi_total_tvl": self._total_tvl(chains),
            "stablecoin_total_mcap": self._stablecoin_mcap(stablecoins),
            "dex_volume_24h": self._number(overview, "total24h"),
            "protocol_fees_24h": self._number(fees, "total24h"),
        }
        missing = [key for key, value in indicators.items() if value is None]
        return DefiLlamaSnapshot(
            status="live" if len(missing) < len(indicators) else "data_insufficient",
            indicators=indicators,
            missing_fields=missing,
        )

    @staticmethod
    async def _json(client: httpx.AsyncClient, url: str) -> Any:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _total_tvl(payload: Any) -> float | None:
        if not isinstance(payload, list):
            return None
        total = 0.0
        found = False
        for item in payload:
            value = DefiLlamaProvider._number(item, "tvl")
            if value is not None:
                total += value
                found = True
        return total if found else None

    @staticmethod
    def _stablecoin_mcap(payload: Any) -> float | None:
        if not isinstance(payload, dict):
            return None
        chains = payload.get("chains") or []
        if isinstance(chains, list) and chains:
            total = 0.0
            found = False
            for item in chains:
                value = DefiLlamaProvider._number(item, "totalCirculatingUSD")
                if value is not None:
                    total += value
                    found = True
            return total if found else None
        return DefiLlamaProvider._number(payload, "totalCirculatingUSD")

    @staticmethod
    def _number(payload: Any, key: str) -> float | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("peggedUSD") or value.get("value")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
