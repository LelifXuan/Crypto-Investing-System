"""Resilience tests for GET /api/v1/strategy/scan.

Cold-load bug (2026-07-24):
  /strategy/scan blocked 60+ seconds on first call (frontend timeout
  was 60s), then either timed out as "扫描失败" or only returned data
  after the user had given up. Per-cell exceptions were caught, but
  the endpoint itself had no try/except — so any error in cache lookup,
  instrument listing, or cache write became a 5xx. There was also no
  warming short-circuit, so cold loads always hit the slow path.

These tests pin the contract:
  - any uncaught exception degrades to HTTP 200 with empty matrix + cache_meta.source="error"
  - cold load (no cache, force=false) returns warming response within 1s
  - cache write failures don't fail the response
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app


async def _dummy_db_session():
    yield object()


def _build_app(monkeypatch, *, cache_lookup, list_instruments, upsert_cache, scan_all=None):
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        cache_lookup,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments",
        list_instruments,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        upsert_cache,
    )
    if scan_all is not None:
        monkeypatch.setattr(
            "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_all",
            scan_all,
        )
    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    return app


# ---------------------------------------------------------------------------
# Degraded-result contract
# ---------------------------------------------------------------------------


def test_scan_returns_degraded_result_when_scanner_raises(monkeypatch):
    """An uncaught exception inside OpportunityScanner.scan_all() must
    produce HTTP 200 with an empty matrix + cache_meta.source='error',
    NOT an HTTP 500."""

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def no_instruments(self):
        return []

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    async def boom(self, *args, **kwargs):  # noqa: ARG001
        raise RuntimeError("simulated scanner crash")

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=no_instruments,
        upsert_cache=no_upsert,
        scan_all=boom,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
    assert response.status_code == 200, (
        f"scan must not 5xx on scanner crash, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    assert body["matrix"] == []
    assert body["ranked"] == []
    assert body["cache_meta"]["source"] in {"error", "warming"}
    assert body["cache_meta"]["opportunities_found"] == 0


def test_scan_returns_warming_when_cache_empty(monkeypatch):
    """Cold load (no cache, force=false) must return a warming response
    quickly and enqueue prewarm, instead of blocking 60+ seconds.
    """
    import time

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def no_instruments(self):
        return []

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    prewarm_calls: list[dict] = []

    async def fake_enqueue(self, payload):  # noqa: ARG001
        prewarm_calls.append({"current_page": payload.current_page})
        from app.schemas.market import PrecomputeHintResponse
        return PrecomputeHintResponse(
            status="accepted",
            accepted=1,
            queued=1,
            deduped=0,
            queued_keys=["strategy_unified:btc-usdt-perp:1d"],
        )

    monkeypatch.setattr(
        "app.services.precompute.PrecomputeService.enqueue_hint",
        fake_enqueue,
    )

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=no_instruments,
        upsert_cache=no_upsert,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        start = time.monotonic()
        response = client.get("/api/v1/strategy/scan")
        elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 5.0, f"cold load returned in {elapsed:.2f}s — expected < 5s"
    body = response.json()
    assert body["cache_meta"]["source"] == "warming", (
        f"expected warming source, got {body['cache_meta'].get('source')!r}"
    )
    assert len(prewarm_calls) >= 1, "expected prewarm to be enqueued"


def test_scan_does_not_fail_on_cache_write_error(monkeypatch):
    """If upsert_page_snapshot_cache() raises, the endpoint must still
    return HTTP 200 with the fresh result."""

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def fake_instruments(self):
        return [
            SimpleNamespace(
                instrument_id="btc-usdt-perp",
                code="btc-usdt-perp",
            )
        ]

    async def boom_upsert(self, **kwargs):  # noqa: ARG001
        raise RuntimeError("simulated cache write failure")

    from app.services.strategy_unified.opportunity_scanner import ScanResult

    async def fake_scan_all(self, instrument_ids, instrument_codes):  # noqa: ARG001
        return ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            instruments=instrument_ids,
            timeframes=["1d"],
            matrix=[],
            ranked=[],
            cache_meta={"fresh_until": datetime.now(UTC).isoformat(), "source": "live"},
        )

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=fake_instruments,
        upsert_cache=boom_upsert,
        scan_all=fake_scan_all,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
    assert response.status_code == 200, (
        f"scan must not 5xx on cache write error, got {response.status_code}"
    )


def test_scan_handles_instruments_list_error(monkeypatch):
    """If repository.list_instruments() raises, the endpoint must
    still return HTTP 200 with cache_meta.source='error'."""

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def boom_instruments(self):
        raise RuntimeError("DB locked")

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=boom_instruments,
        upsert_cache=no_upsert,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan?force=true")
    assert response.status_code == 200
    body = response.json()
    assert body["matrix"] == []
    assert body["cache_meta"]["source"] in {"error", "warming"}


# ---------------------------------------------------------------------------
# 2026-07-24 v2: warming cache must NOT be overwritten as 'cache' on hit.
# If the cache row has cache_meta.source='warming', the endpoint must
# preserve that signal so the frontend's poll loop keeps the warming
# banner up.
# ---------------------------------------------------------------------------


def test_scan_preserves_warming_source_on_cache_hit(monkeypatch):
    """When the cache row was written by the warming short-circuit,
    its payload has cache_meta.source='warming'. On cache hit, the
    endpoint must return that payload WITHOUT overwriting the source
    to 'cache' — otherwise the frontend interprets the empty matrix
    as 'no opportunities' and the warming banner never appears."""

    from datetime import datetime, timezone

    warming_payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "instruments": [],
        "timeframes": ["1w", "1d", "4h"],
        "matrix": [],
        "ranked": [],
        "cache_meta": {
            "fresh_until": datetime.now(timezone.utc).isoformat(),
            "source": "warming",
            "instruments_scanned": 0,
            "opportunities_found": 0,
            "message": "首次访问，正在后台预热数据缓存，预计 5-10 秒后自动出结果。",
        },
    }

    async def warming_cache(self, cache_key):  # noqa: ARG001
        return SimpleNamespace(
            cache_key=cache_key,
            payload_json=warming_payload,
            cache_state="warming",
            status="warming",
            expires_at=None,  # expired — we want to hit the cache-hit branch
        )

    async def no_instruments(self):
        return []

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    app = _build_app(
        monkeypatch,
        cache_lookup=warming_cache,
        list_instruments=no_instruments,
        upsert_cache=no_upsert,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.status_code == 200
    body = response.json()
    assert body["cache_meta"]["source"] == "warming", (
        f"warming cache hit must preserve 'warming' source; "
        f"endpoint returned {body['cache_meta']}"
    )
    assert body["matrix"] == []


def test_scan_real_cache_hit_overwrites_source_to_cache(monkeypatch):
    """Conversely, a non-warming cache hit MUST overwrite the source
    to 'cache' so the frontend knows it's serving a real cached result
    (not a warming short-circuit)."""

    from datetime import datetime, timezone

    real_payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "instruments": ["btc-usdt-perp"],
        "timeframes": ["1d"],
        "matrix": [],
        "ranked": [],
        "cache_meta": {
            "fresh_until": datetime.now(timezone.utc).isoformat(),
            "source": "live",  # backend cache source
            "instruments_scanned": 1,
            "opportunities_found": 0,
        },
    }

    async def real_cache(self, cache_key):  # noqa: ARG001
        return SimpleNamespace(
            cache_key=cache_key,
            payload_json=real_payload,
            cache_state="fresh",
            status="ready",
            expires_at=None,
        )

    async def no_instruments(self):
        return []

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    app = _build_app(
        monkeypatch,
        cache_lookup=real_cache,
        list_instruments=no_instruments,
        upsert_cache=no_upsert,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.status_code == 200
    body = response.json()
    assert body["cache_meta"]["source"] == "cache", (
        f"real cache hit must overwrite to 'cache'; got {body['cache_meta']['source']!r}"
    )