"""The scan read path must stay fast and independent of browser navigation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.cache_registry import strategy_scan_cache_key
from app.services.strategy_unified.opportunity_scanner import ScanResult


def _app(
    monkeypatch, *, cache=None, instruments=None, scan_all=None, scan_published=None, upsert=None
):
    @asynccontextmanager
    async def session():
        yield object()

    async def get_cache(self, cache_key):  # noqa: ARG001
        return cache

    async def list_instruments(self):
        return instruments or []

    async def save(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr("app.api.v1.endpoints.strategy.db_manager.session", session)
    monkeypatch.setattr("app.api.v1.endpoints.strategy.db_manager.writer_session", session)
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache", get_cache
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments", list_instruments
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        upsert or save,
    )
    if scan_all:
        monkeypatch.setattr(
            "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_all",
            scan_all,
        )
    if scan_published:
        monkeypatch.setattr(
            "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_published",
            scan_published,
        )
    return create_app(enable_lifespan=False)


def _cached_row(*, stale=False):
    now = datetime.now(UTC)
    return SimpleNamespace(
        payload_json={
            "scanned_at": now.isoformat(),
            "instruments": ["btc-usdt-perp"],
            "timeframes": ["1d"],
            "matrix": [
                {
                    "instrument_id": "btc-usdt-perp",
                    "timeframe": "1d",
                    "direction": "LONG",
                    "cache_state": "fresh",
                    "qualified": True,
                }
            ],
            "ranked": [{"instrument_id": "btc-usdt-perp"}],
            "cache_meta": {"input_snapshot_at": now.isoformat()},
        },
        cache_state="fresh",
        status="ready",
        snapshot_at=now,
        data_ts=now,
        expires_at=now - timedelta(seconds=1) if stale else now + timedelta(hours=1),
    )


def test_cold_read_returns_warming_without_computing_or_enqueuing(monkeypatch):
    async def forbidden_scan(self, *args, **kwargs):  # noqa: ARG001
        raise AssertionError("GET started a scan")

    async def forbidden_enqueue(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("GET enqueued work")

    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.precompute_service.enqueue_hint", forbidden_enqueue
    )
    app = _app(monkeypatch, scan_all=forbidden_scan)
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.status_code == 200
    assert response.json()["cache_meta"]["source"] == "warming"


def test_cached_read_is_read_only(monkeypatch):
    async def forbidden_scan(self, *args, **kwargs):  # noqa: ARG001
        raise AssertionError("GET started a scan")

    async def forbidden_write(self, **kwargs):  # noqa: ARG001
        raise AssertionError("GET wrote a scan")

    app = _app(
        monkeypatch, cache=_cached_row(), scan_all=forbidden_scan, upsert=forbidden_write
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.status_code == 200
    assert response.json()["cache_meta"]["source"] == "cache"


def test_stale_read_keeps_last_known_good_but_disables_signal(monkeypatch):
    app = _app(monkeypatch, cache=_cached_row(stale=True))
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
    body = response.json()
    assert body["cache_meta"]["source"] == "stale_revalidating"
    assert body["matrix"][0]["cache_state"] == "stale"
    assert body["matrix"][0]["qualified"] is False
    assert body["ranked"] == []


def test_newer_unified_snapshot_does_not_recompute_on_get(monkeypatch):
    scan = _cached_row()
    scan.payload_json["cache_meta"]["input_snapshot_at"] = (
        datetime.now(UTC) - timedelta(hours=1)
    ).isoformat()
    app = _app(
        monkeypatch,
        cache=scan,
        instruments=[SimpleNamespace(instrument_id="btc-usdt-perp")],
    )

    async def cache_by_key(self, cache_key):  # noqa: ARG001
        if cache_key == strategy_scan_cache_key():
            return scan
        return SimpleNamespace(snapshot_at=datetime.now(UTC))

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        cache_by_key,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.json()["cache_meta"]["source"] == "stale_revalidating"


def test_forced_scan_reprojects_published_strategies(monkeypatch):
    called = []

    async def scan(self, instrument_ids, instrument_codes):  # noqa: ARG001
        called.append(True)
        return ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            instruments=instrument_ids,
            timeframes=["1d"],
            matrix=[],
            ranked=[],
            cache_meta={"source": "published_snapshots"},
        )

    async def forbidden_live_scan(self, *args, **kwargs):  # noqa: ARG001
        raise AssertionError("forced scan rebuilt unpublished strategies")

    app = _app(monkeypatch, scan_all=forbidden_live_scan, scan_published=scan)
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
    assert response.status_code == 200
    assert response.json()["cache_meta"]["source"] == "published_snapshots"
    assert called == [True]


def test_forced_scan_degrades_on_error(monkeypatch):
    async def scan(self, *args, **kwargs):  # noqa: ARG001
        raise RuntimeError("scanner failed")

    app = _app(monkeypatch, scan_published=scan)
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
    assert response.status_code == 200
    assert response.json()["cache_meta"]["source"] == "error"
