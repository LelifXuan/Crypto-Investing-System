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
