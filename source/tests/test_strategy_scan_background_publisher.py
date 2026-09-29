"""The worker publishes scan projections without rebuilding on page reads."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.cache_registry import strategy_scan_cache_key
from app.workers.precompute_worker import PrecomputeWorker


@pytest.mark.asyncio
async def test_background_publisher_updates_scan_when_input_changes(monkeypatch):
    now = datetime.now(UTC)
    old = now - timedelta(minutes=5)
    scan = SimpleNamespace(
        payload_json={"cache_meta": {"input_snapshot_at": old.isoformat()}},
        cache_state="fresh",
        status="ready",
        expires_at=now + timedelta(hours=1),
        snapshot_at=old,
    )
    unified = SimpleNamespace(
        payload_json={},
        cache_state="fresh",
        status="ready",
        expires_at=now + timedelta(hours=1),
        snapshot_at=now,
    )
    published = []

    @asynccontextmanager
    async def session():
        yield object()

    async def get_cache(self, cache_key):  # noqa: ARG001
        return scan if cache_key == strategy_scan_cache_key() else unified

    async def instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp", base_ccy="BTC")]

    async def upsert(self, **kwargs):  # noqa: ARG001
        published.append(kwargs)

    monkeypatch.setattr("app.workers.precompute_worker.db_manager.session", session)
    monkeypatch.setattr("app.workers.precompute_worker.db_manager.writer_session", session)
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache", get_cache
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments", instruments
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache", upsert
    )

    await PrecomputeWorker()._refresh_scan_cache()

    assert len(published) == 1
    assert published[0]["cache_key"] == strategy_scan_cache_key()
    assert published[0]["payload_json"]["cache_meta"]["source"] == "background_publisher"
    assert published[0]["payload_json"]["cache_meta"]["input_snapshot_at"] == now.isoformat()
    assert len(published[0]["payload_json"]["matrix"]) == 3


@pytest.mark.asyncio
async def test_background_publisher_skips_unchanged_fresh_scan(monkeypatch):
    now = datetime.now(UTC)
    scan = SimpleNamespace(
        payload_json={"cache_meta": {"input_snapshot_at": now.isoformat()}},
        cache_state="fresh",
        status="ready",
        expires_at=now + timedelta(hours=1),
        snapshot_at=now,
    )

    @asynccontextmanager
    async def session():
        yield object()

    async def get_cache(self, cache_key):  # noqa: ARG001
        return scan

    async def instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp")]

    async def forbidden_upsert(self, **kwargs):  # noqa: ARG001
        raise AssertionError("unchanged input republished")

    monkeypatch.setattr("app.workers.precompute_worker.db_manager.session", session)
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache", get_cache
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments", instruments
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        forbidden_upsert,
    )

    await PrecomputeWorker()._refresh_scan_cache()
