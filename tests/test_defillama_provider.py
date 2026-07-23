from __future__ import annotations

import httpx
import pytest

from app.services.onchain.providers import DefiLlamaProvider
from app.services.onchain.router import OnchainProviderRouter


class DummyClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    async def get(self, url: str):
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_defillama_provider_normalizes_public_snapshot() -> None:
    provider = DefiLlamaProvider()
    snapshot = await provider.fetch_snapshot(
        client=DummyClient(
            [
                [{"name": "Ethereum", "tvl": 100.0}, {"name": "Solana", "tvl": 50.0}],
                {"chains": [{"totalCirculatingUSD": {"peggedUSD": 120.0}}]},
                {"total24h": 30.0},
                {"total24h": 4.0},
            ]
        )
    )

    assert snapshot.status == "live"
    assert snapshot.source_provider == "defillama"
    assert snapshot.indicators["defi_total_tvl"] == 150.0
    assert snapshot.indicators["stablecoin_total_mcap"] == 120.0
    assert snapshot.indicators["dex_volume_24h"] == 30.0
    assert snapshot.indicators["protocol_fees_24h"] == 4.0
    assert snapshot.missing_fields == []


@pytest.mark.asyncio
async def test_defillama_provider_degrades_without_blocking_on_network_error() -> None:
    provider = DefiLlamaProvider()
    snapshot = await provider.fetch_snapshot(
        client=DummyClient([httpx.ConnectError("blocked")])
    )

    assert snapshot.status == "degraded"
    assert snapshot.indicators == {}
    assert snapshot.missing_fields


def test_onchain_router_marks_optional_providers_disabled_without_keys() -> None:
    router = OnchainProviderRouter()

    assert router.provider_state("defillama").status == "enabled"
    assert router.provider_state("etherscan").status in {"disabled", "enabled"}
    assert router.provider_state("dune").auth_required is True
    assert router.provider_state("debank").enabled is False
