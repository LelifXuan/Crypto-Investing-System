"""Unpersisted live quotes must satisfy the existing HTTP response contract."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import market_prices
from app.db.models.market import MarkPrice
from app.schemas.market import MarkPriceRead


@pytest.mark.parametrize("stored_id", [None, 37])
def test_read_only_live_mark_serializes_without_changing_quote(monkeypatch, stored_id):
    quote = MarkPrice(
        mark_id=stored_id,
        instrument_id="btc-usdt-perp",
        mark_price=Decimal("62401.125"),
        source="fixture:quote",
        ts_event=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    calls = []

    async def best_mark(self, **kwargs):
        calls.append(kwargs)
        return quote

    monkeypatch.setattr(market_prices.MarketService, "get_best_mark", best_mark)
    app = FastAPI()

    @app.get("/quote", response_model=MarkPriceRead | None)
    async def endpoint():
        return await market_prices.get_latest_mark(
            instrument_id="btc-usdt-perp",
            prefer_live=True,
            persist_live=False,
            session=None,
            _=None,
        )

    with TestClient(app) as client:
        response = client.get("/quote")
    assert response.status_code == 200
    data = response.json()
    assert data["mark_id"] == (stored_id if stored_id is not None else 0)
    assert Decimal(data["mark_price"]) == Decimal("62401.125")
    assert data["source"] == "fixture:quote"
    assert calls == [{"instrument_id": "btc-usdt-perp", "prefer_live": True, "persist_live": False}]
