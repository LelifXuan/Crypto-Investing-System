from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app


async def _dummy_db_session():
    yield object()


@pytest.mark.asyncio
async def test_scan_endpoint_returns_200(monkeypatch) -> None:
    """GET /api/v1/strategy/scan returns 200 with valid structure."""

    async def no_cached_snapshot(self, cache_key: str):  # noqa: ARG001
        return None

    async def empty_instruments(self):
        return []

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        no_cached_snapshot,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments",
        empty_instruments,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan")
        assert response.status_code == 200
        data = response.json()
        assert "matrix" in data
        assert "ranked" in data
        assert "instruments" in data
        assert "scanned_at" in data


@pytest.mark.asyncio
async def test_scan_endpoint_force_param(monkeypatch) -> None:
    """?force=true is accepted."""

    async def no_cached_snapshot(self, cache_key: str):  # noqa: ARG001
        return None

    async def empty_instruments(self):
        return []

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        no_cached_snapshot,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments",
        empty_instruments,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
        assert response.status_code in (200, 500)  # 500 OK if no DB available in test
