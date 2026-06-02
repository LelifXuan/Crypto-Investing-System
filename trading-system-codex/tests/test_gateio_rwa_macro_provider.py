from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.macro.providers.gateio_rwa import (
    RWA_CANDIDATES,
    GateioRwaMacroProvider,
)


def test_oil_candidates_use_gateio_futures_api_contracts() -> None:
    assert RWA_CANDIDATES["wti_oil"][0] == {
        "market": "futures",
        "symbol": "CL_USDT",
        "settle": "usdt",
    }
    assert RWA_CANDIDATES["brent_oil"][0] == {
        "market": "futures",
        "symbol": "BZ_USDT",
        "settle": "usdt",
    }


def test_tradfi_index_candidates_use_gateio_futures_api_contracts() -> None:
    assert RWA_CANDIDATES["qqq"][0] == {
        "market": "futures",
        "symbol": "NAS100_USDT",
        "settle": "usdt",
    }
    assert RWA_CANDIDATES["spy"][0] == {
        "market": "futures",
        "symbol": "SPX500_USDT",
        "settle": "usdt",
    }
    assert RWA_CANDIDATES["NAS100_USDT"][0]["symbol"] == "NAS100_USDT"
    assert RWA_CANDIDATES["SPX500_USDT"][0]["symbol"] == "SPX500_USDT"


@pytest.mark.asyncio
async def test_gateio_rwa_futures_ticker_uses_mark_price(monkeypatch) -> None:
    provider = GateioRwaMacroProvider()
    calls = []

    async def fake_fetch(candidate):
        calls.append(candidate)
        return [
            {
                "contract": candidate["symbol"],
                "last": "97.91",
                "mark_price": "98.12",
                "volume_24h_quote": "120000",
            }
        ], 3, False

    monkeypatch.setattr(provider, "_fetch_ticker", fake_fetch)

    result = await provider.fetch_latest("wti_oil")

    assert calls == [
        {"market": "futures", "symbol": "CL_USDT", "settle": "usdt"},
        {"market": "futures", "symbol": "CL_USDT", "settle": "usdt"},
    ]
    assert result.value == Decimal("98.12")
    assert result.source_ref == "gateio_rwa:futures:CL_USDT"


@pytest.mark.asyncio
async def test_gateio_rwa_tradfi_index_uses_mark_price(monkeypatch) -> None:
    provider = GateioRwaMacroProvider()

    async def fake_fetch(candidate):
        return [
            {
                "contract": candidate["symbol"],
                "last": "7500",
                "index_price": "7498",
                "mark_price": "7517.65",
                "volume_24h_quote": "250000",
            }
        ], 2, False

    monkeypatch.setattr(provider, "_fetch_ticker", fake_fetch)

    result = await provider.fetch_latest("spy")

    assert result.value == Decimal("7517.65")
    assert result.source_ref == "gateio_rwa:futures:SPX500_USDT"
