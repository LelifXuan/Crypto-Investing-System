from __future__ import annotations

import pytest

from app.cache.market_cache import market_cache


@pytest.mark.asyncio
async def test_market_cache_roundtrip() -> None:
    await market_cache.set_mark("btc-usdt-perp", {"instrument_id": "btc-usdt-perp", "price": "100", "source": "test", "ts_event": "2026-04-05T00:00:00+00:00"})
    cached = await market_cache.get_mark("btc-usdt-perp")
    assert cached is not None
    assert cached["price"] == "100"
