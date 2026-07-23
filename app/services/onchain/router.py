from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.onchain.providers import DefiLlamaProvider


@dataclass(frozen=True)
class OnchainProviderState:
    provider: str
    enabled: bool
    status: str
    auth_required: bool
    reason: str | None = None


class OnchainProviderRouter:
    def __init__(self) -> None:
        self.defillama = DefiLlamaProvider()

    def provider_state(self, provider: str) -> OnchainProviderState:
        provider = provider.lower()
        if provider == "defillama":
            return OnchainProviderState(provider, True, "enabled", False)
        if provider == "etherscan":
            enabled = bool(getattr(settings, "etherscan_api_key", ""))
            return OnchainProviderState(
                provider,
                enabled,
                "enabled" if enabled else "disabled",
                True,
                None if enabled else "ETHERSCAN_API_KEY missing",
            )
        if provider == "dune":
            enabled = bool(getattr(settings, "dune_api_key", ""))
            return OnchainProviderState(
                provider,
                enabled,
                "enabled" if enabled else "disabled",
                True,
                None if enabled else "DUNE_API_KEY missing",
            )
        if provider == "debank":
            enabled = bool(getattr(settings, "debank_access_key", ""))
            return OnchainProviderState(
                provider,
                enabled,
                "enabled" if enabled else "disabled",
                True,
                None if enabled else "DEBANK_ACCESS_KEY missing",
            )
        return OnchainProviderState(provider, False, "disabled", False, "provider unsupported")

    async def fetch_metric(self, indicator_key: str) -> dict[str, Any]:
        if indicator_key in DefiLlamaProvider.metric_keys():
            snapshot = await self.defillama.fetch_snapshot()
            return {
                "provider": "defillama",
                "status": snapshot.status,
                "value": snapshot.indicators.get(indicator_key),
                "indicators": snapshot.indicators,
                "missing_fields": snapshot.missing_fields,
            }
        return {
            "provider": "unavailable",
            "status": "degraded",
            "value": None,
            "missing_fields": [indicator_key],
        }
