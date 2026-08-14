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


def test_scan_cold_cache_returns_live_matrix_from_cache_only_scan(monkeypatch):
    """Cold load (no cache, force=false) must run one cache-only scan and
    return the real matrix instead of blocking 60+ seconds — and must
    enqueue a prewarm so fresher cells land in the background.
    """
    import time

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def fake_instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp", code="btc-usdt-perp")]

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    prewarm_calls: list[dict] = []

    async def fake_enqueue(payload):  # noqa: ANN001
        prewarm_calls.append({"current_page": payload.current_page})
        from app.schemas.market import PrecomputeHintResponse
        return PrecomputeHintResponse(
            status="accepted",
            accepted=1,
            queued=1,
            deduped=0,
            queued_keys=["strategy_unified:btc-usdt-perp:1d"],
        )

    # Patch the same instance path used by other strategy tests
    # (app.api.v1.endpoints.strategy.precompute_service.enqueue_hint).
    # Patching the CLASS instead (PrecomputeService.enqueue_hint) can be
    # shadowed by a leftover instance attribute when another test file in
    # the same pytest run patched the instance path first.
    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.precompute_service.enqueue_hint",
        fake_enqueue,
    )

    from app.services.strategy_unified.opportunity_scanner import ScanItem, ScanResult

    async def fake_scan_all(self, instrument_ids, instrument_codes, *, force=False):  # noqa: ARG001
        assert force is False, "cold-load branch must call scan_all with force=False"
        return ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            instruments=list(instrument_ids),
            timeframes=["1w", "1d", "4h"],
            matrix=[
                ScanItem(
                    instrument_id="btc-usdt-perp",
                    instrument_code="btc-usdt-perp",
                    timeframe="1d",
                    direction="WAIT",
                    direction_label="等待",
                    confidence=74.0,
                    score=0.0,
                    summary="",
                    risk_reward=0.0,
                    leverage_hint="spot",
                    position_cap="standard",
                    primary_driver="",
                    conflicts=[],
                    cache_state="fresh",
                    data_quality=70.0,
                )
            ],
            ranked=[],
            cache_meta={
                "fresh_until": datetime.now(UTC).isoformat(),
                "source": "live",
                "instruments_scanned": len(instrument_ids),
                "opportunities_found": 0,
                "cells_ready": 1,
                "cells_pending": 0,
            },
        )

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=fake_instruments,
        upsert_cache=no_upsert,
        scan_all=fake_scan_all,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        start = time.monotonic()
        response = client.get("/api/v1/strategy/scan")
        elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 5.0, f"cold load returned in {elapsed:.2f}s — expected < 5s"
    body = response.json()
    assert body["cache_meta"]["source"] == "live", (
        f"cold-load scan must return a real matrix, got {body['cache_meta'].get('source')!r}"
    )
    assert body["instruments"] == ["btc-usdt-perp"]
    assert len(body["matrix"]) == 1
    assert len(prewarm_calls) >= 1, "expected prewarm to be enqueued"


def test_scan_falls_back_to_warming_when_cold_scan_fails(monkeypatch):
    """If the cache-only scan itself fails on a cold cache, the endpoint
    must fall back to the warming short-circuit (fast HTTP 200), not 5xx.
    """
    import time

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def fake_instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp", code="btc-usdt-perp")]

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    async def boom_scan(self, instrument_ids, instrument_codes, *, force=False):  # noqa: ARG001
        raise RuntimeError("cache-only scan failed")

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=fake_instruments,
        upsert_cache=no_upsert,
        scan_all=boom_scan,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        start = time.monotonic()
        response = client.get("/api/v1/strategy/scan")
        elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 5.0
    body = response.json()
    assert body["cache_meta"]["source"] == "warming", (
        f"expected warming fallback, got {body['cache_meta'].get('source')!r}"
    )


def test_scan_force_passes_force_flag_to_scanner(monkeypatch):
    """?force=true must reach OpportunityScanner.scan_all as force=True —
    the pre-2026-08-07 endpoint passed force=force to a signature that
    did not accept it, which TypeError'd into cache_meta.source='error'."""

    async def no_cache(self, cache_key):  # noqa: ARG001
        return None

    async def fake_instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp", code="btc-usdt-perp")]

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    seen_force: list[bool] = []

    from app.services.strategy_unified.opportunity_scanner import ScanResult

    async def fake_scan_all(self, instrument_ids, instrument_codes, *, force=False):  # noqa: ARG001
        seen_force.append(force)
        return ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            instruments=list(instrument_ids),
            timeframes=["1d"],
            matrix=[],
            ranked=[],
            cache_meta={"fresh_until": datetime.now(UTC).isoformat(), "source": "live"},
        )

    app = _build_app(
        monkeypatch,
        cache_lookup=no_cache,
        list_instruments=fake_instruments,
        upsert_cache=no_upsert,
        scan_all=fake_scan_all,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan?force=true")

    assert response.status_code == 200
    body = response.json()
    assert body["cache_meta"]["source"] == "live", (
        f"force scan must succeed; got source={body['cache_meta'].get('source')!r} "
        f"message={body['cache_meta'].get('message')!r}"
    )
    assert seen_force == [True], f"expected scan_all(force=True), got {seen_force}"


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

    async def fake_scan_all(self, instrument_ids, instrument_codes, *, force=False):  # noqa: ARG001
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


def test_scan_expired_warming_cache_falls_through_to_scan(monkeypatch):
    """Bounded warming (2026-08-07): a warming cache row is only
    authoritative inside its short-circuit window. Once expires_at has
    passed, the endpoint must NOT keep returning the empty warming
    payload forever — it must fall through and produce a real matrix.

    Pre-fix behaviour: cache_status() deliberately maps any warming row
    to 'warming' forever, so the scan endpoint kept serving the empty
    warming payload and the frontend polled an empty matrix indefinitely.
    """

    from datetime import timedelta, timezone

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

    async def expired_warming_cache(self, cache_key):  # noqa: ARG001
        return SimpleNamespace(
            cache_key=cache_key,
            payload_json=warming_payload,
            cache_state="warming",
            status="warming",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),  # window closed
        )

    async def fake_instruments(self):
        return [SimpleNamespace(instrument_id="btc-usdt-perp", code="btc-usdt-perp")]

    async def no_upsert(self, **kwargs):  # noqa: ARG001
        return None

    from app.services.strategy_unified.opportunity_scanner import ScanItem, ScanResult

    async def fake_scan_all(self, instrument_ids, instrument_codes, *, force=False):  # noqa: ARG001
        assert force is False
        return ScanResult(
            scanned_at=datetime.now(UTC).isoformat(),
            instruments=list(instrument_ids),
            timeframes=["1d"],
            matrix=[
                ScanItem(
                    instrument_id="btc-usdt-perp",
                    instrument_code="btc-usdt-perp",
                    timeframe="1d",
                    direction="LONG",
                    direction_label="做多",
                    confidence=80.0,
                    score=82.0,
                    summary="趋势确认",
                    risk_reward=3.0,
                    leverage_hint="3x",
                    position_cap="standard",
                    primary_driver="price_structure",
                    conflicts=[],
                    cache_state="fresh",
                    data_quality=75.0,
                )
            ],
            ranked=[],
            cache_meta={
                "fresh_until": datetime.now(UTC).isoformat(),
                "source": "live",
                "instruments_scanned": 1,
                "opportunities_found": 1,
                "cells_ready": 1,
                "cells_pending": 0,
            },
        )

    app = _build_app(
        monkeypatch,
        cache_lookup=expired_warming_cache,
        list_instruments=fake_instruments,
        upsert_cache=no_upsert,
        scan_all=fake_scan_all,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/strategy/scan")
    assert response.status_code == 200
    body = response.json()
    assert body["cache_meta"]["source"] == "live", (
        f"expired warming cache must fall through to a real scan; "
        f"got source={body['cache_meta'].get('source')!r}"
    )
    assert len(body["matrix"]) == 1
    assert body["matrix"][0]["direction"] == "LONG"