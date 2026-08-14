"""Tests for the strategy-unified read-path's degraded-cache handling.

2026-07-25: When the page_snapshot_cache row says cache_state='fresh' but
the cached payload itself is status='degraded' (cache row was written
during a cold prewarm, or older rebuild races), the read-path must
NOT return that stale-degraded content as if it were ready. The
frontend relies on a clean handoff: either get a fully-populated payload
(no banner), or get a degraded payload with refresh_limitations so the
banner can explain that data is being rebuilt.

This file pins that contract: a fresh-by-row-state, degraded-by-content
cache row must be demoted to "stale" on read and fall through to the
cold-read payload that enqueues a rebuild.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.main import create_app
from app.schemas.market import PrecomputeHintResponse


async def _dummy_db_session():
    yield object()


def _stub_snapshot(*, cache_state: str, payload_status: str):
    """Build a PageSnapshotCache-shaped stub. Tests only need what the
    read-path uses: cache_key/expires_at/payload_json/cache_state/status.
    """
    now = datetime.now(UTC)
    return SimpleNamespace(
        cache_key="strategy_unified:btc-usdt-perp:v3",
        page_type="strategy_unified",
        instrument_id="btc-usdt-perp",
        timeframe=None,
        payload_json={
            "instrument_id": "btc-usdt-perp",
            "status": payload_status,
            "degraded": payload_status == "degraded",
            "degraded_components": ["strategy_unified_cache_missing"],
            "refresh_state": "cache_only",
            "refresh_limitations": [
                "force=true requested six-timeframe strategy refresh before synthesis."
            ],
            "prewarm_status": "idle",
            "unified_state": {
                "code": "DATA_DEGRADED",
                "label": "数据质量不足",
                "permission": "observe",
                "risk_level": "high",
                "current_price": None,
            },
            "horizon_views": {},
            "horizon_governance": {},
            "market_operation": {"chain": {}, "summary": ""},
            "timeframe_stack": [],
            "trade_decision": {},
            "evidence_trace": [],
            "narrative": {},
        },
        status="ready",
        cache_state=cache_state,
        snapshot_at=now,
        expires_at=now + timedelta(hours=1),
        data_ts=now,
    )


def test_stale_degraded_cache_row_is_demoted_and_does_not_serve_content(monkeypatch) -> None:
    """Cache row: cache_state='fresh' + payload.status='degraded' must NOT
    be served as ready content. Endpoint must fall through to the cold-read
    branch (which enqueues a rebuild) and return payload with
    refresh_limitations appropriate for the cold-read path — distinct from
    whatever text was baked into the cached payload."""
    enqueued: list[tuple[str, str]] = []
    build_calls: list[tuple[str, bool]] = []

    async def fake_build(self, instrument_id="btc-usdt-perp", *, force=False):
        build_calls.append((instrument_id, force))
        return _stub_snapshot(cache_state="fresh", payload_status="ready").payload_json

    async def fake_enqueue(payload):
        enqueued.append((payload.reason, payload.priority))
        return PrecomputeHintResponse(status="accepted", accepted=1, queued=1)

    async def fake_get_snapshot(self, cache_key):
        return _stub_snapshot(cache_state="fresh", payload_status="degraded")

    async def fail_upsert_snapshot(self, **kwargs):
        # The cold-read path on /strategy/unified must NOT write to the
        # page_snapshot_cache (only the force=true rebuild path writes).
        raise AssertionError(
            "cold-read path must not write page_snapshot_cache; only rebuild does"
        )

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        fake_get_snapshot,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fail_upsert_snapshot,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fake_build,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.precompute_service.enqueue_hint",
        fake_enqueue,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp"},
        )

    assert response.status_code == 200
    payload = response.json()

    # The cold-read path enqueues a rebuild hint.
    assert enqueued, "cold-read fallback must enqueue a precompute hint"
    assert enqueued[0][0] == "strategy_unified_cold_read"

    # The cold-read path must NOT synchronously build (the rebuild is async).
    assert build_calls == [], "cold-read fallback must not call build_unified_strategy"

    # The returned payload must NOT be the cached "force=true requested..." text.
    # The cold-read branch emits "Unified strategy snapshot is missing;
    # background prewarm has been queued."
    refresh_limitations = payload.get("refresh_limitations") or []
    assert any(
        "background prewarm" in txt for txt in refresh_limitations
    ), f"expected cold-read refresh_limitations to mention background prewarm; got {refresh_limitations!r}"

    # The cached stale-degraded payload's refresh_limitations text must not leak.
    assert not any(
        "force=true requested" in txt for txt in refresh_limitations
    ), (
        f"stale-degraded cached refresh_limitations must not leak into the response; "
        f"got {refresh_limitations!r}"
    )

    # The cold-read payload's status is "degraded" but it carries
    # refresh_state="missing" + prewarm_status="enqueued" — the signals the
    # frontend banner needs to display the meaningful state.
    assert payload["status"] == "degraded"
    assert payload["refresh_state"] in {"missing", "enqueued"}
    assert payload["prewarm_status"] in {"enqueued", "idle", "disabled"}


def test_fresh_ready_cache_row_is_served_as_is(monkeypatch) -> None:
    """Regression guard: cache_state='fresh' + payload.status='ready' must
    still be returned by the read-path without falling through to the cold
    branch. We must not over-eagerly demote genuinely fresh content."""
    enqueued: list[tuple[str, str]] = []

    async def fail_enqueue(payload):
        enqueued.append(("unexpected", "0"))
        raise AssertionError(
            "fresh+ready cache must not trigger a cold-read fallback"
        )

    async def fake_get_snapshot(self, cache_key):
        return _stub_snapshot(cache_state="fresh", payload_status="ready")

    async def fail_build(self, instrument_id="btc-usdt-perp", *, force=False):
        raise AssertionError("fresh+ready cache must not call build_unified_strategy")

    async def fake_guard_cached(repository, instrument_id, payload):
        return payload, False

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        fake_get_snapshot,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.unified_service.UnifiedStrategyService.build_unified_strategy",
        fail_build,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy._guard_cached_strategy",
        fake_guard_cached,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.strategy.precompute_service.enqueue_hint",
        fail_enqueue,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    # prewarm_status pinned to "ready" because the row state is fresh
    assert payload["prewarm_status"] == "ready"
