"""Regression tests for GET /api/v1/strategy/bundle poisoned-row 500.

Root cause (2026-09-23): ``StrategySnapshotBuilder._persist_strategy_cache``
wrote the raw feature *snapshot* under ``{"decision": snapshot}`` using the
same ``strategy_bundle:*`` cache key owned by
``StrategySignalService.refresh_bundle``. 46/66 rows therefore carried a
decision without ``strategy_state``; ``GET /bundle`` served the poisoned
row verbatim and FastAPI raised ResponseValidationError (15 errors) → 500
whenever the poisoned row was fresher than the last good decision row.

Guards:
- the builder now writes under ``strategy_snapshot:*`` (key split);
- the endpoint rebuilds when the cached row is not a decision.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session, get_db_writer_session
from app.main import create_app
from app.services.cache_registry import (
    strategy_bundle_cache_key,
    strategy_snapshot_cache_key,
)


async def _dummy_db_session():
    yield object()


def _poisoned_bundle_row():
    """A row shaped like the pre-fix builder write: snapshot under decision."""

    class _Cache:
        cache_state = "fresh"
        status = "ready"
        snapshot_at = datetime.now(timezone.utc)
        data_ts = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc)
        source_updated_at = datetime.now(timezone.utc)
        source_version = "v3"
        payload_json = {
            "decision": {
                "instrument_id": "eth-usdt-perp",
                "current_price": "2780.35",
                "indicators": {"ema_20": 2704.7},
            }
        }

    return _Cache()


def _good_bundle_row():
    class _Cache:
        cache_state = "fresh"
        status = "ready"
        snapshot_at = datetime.now(timezone.utc)
        data_ts = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc)
        source_updated_at = datetime.now(timezone.utc)
        source_version = "v3"
        payload_json = {
            "instrument_id": "eth-usdt-perp",
            "timeframe": "4h",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "current_price": "2780.35",
            "decision": {
                "strategy_state": "SHORT_BIAS",
                "strategy_state_label": "偏空观察",
                "strategy_permission": "observe_only",
                "strategy_permission_label": "仅观察",
                "strategy_bias": "short",
                "strategy_bias_label": "偏空",
                "long_score": 33.0,
                "short_score": 60.0,
                "neutral_score": 40.0,
                "dominant_direction": "short",
                "direction_confidence": 80.0,
                "confidence_score": 80.0,
                "execution_score": 35.0,
                "risk_score": 55.0,
                "data_quality_score": 89.0,
                "long_plan": {"direction": "long"},
                "short_plan": {"direction": "short"},
                "primary_strategy": {"direction": "short"},
            },
        }

    return _Cache()


@pytest.mark.asyncio
async def test_bundle_endpoint_rebuilds_poisoned_row(monkeypatch) -> None:
    """A snapshot-shaped row must trigger a rebuild, not a 500."""

    async def poisoned_cache(self, cache_key: str):  # noqa: ARG001
        return _poisoned_bundle_row()

    async def fake_refresh(self, instrument_id: str, timeframe: str, **kwargs):  # noqa: ARG001
        row = _good_bundle_row()
        payload = dict(row.payload_json)
        payload.update(
            {
                "status": "ready",
                "cache_state": "fresh",
                "status_message": "策略信号已就绪",
                "refresh_enqueued": False,
            }
        )
        return payload

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        poisoned_cache,
    )
    monkeypatch.setattr(
        "app.services.strategy_signal.service.StrategySignalService.refresh_bundle",
        fake_refresh,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    app.dependency_overrides[get_db_writer_session] = _dummy_db_session
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/strategy/bundle?instrument_id=eth-usdt-perp&timeframe=4h"
        )
        assert response.status_code == 200, response.text[:500]
        assert response.json()["decision"]["strategy_state"] == "SHORT_BIAS"


@pytest.mark.asyncio
async def test_bundle_endpoint_serves_good_row_without_rebuild(monkeypatch) -> None:
    """A valid decision row must be served directly (no rebuild)."""
    calls: list[str] = []

    async def good_cache(self, cache_key: str):  # noqa: ARG001
        return _good_bundle_row()

    async def counting_refresh(self, instrument_id: str, timeframe: str, **kwargs):  # noqa: ARG001
        calls.append(f"{instrument_id}:{timeframe}")
        raise AssertionError("rebuild must not run for a valid row")

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        good_cache,
    )
    monkeypatch.setattr(
        "app.services.strategy_signal.service.StrategySignalService.refresh_bundle",
        counting_refresh,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    app.dependency_overrides[get_db_writer_session] = _dummy_db_session
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/strategy/bundle?instrument_id=eth-usdt-perp&timeframe=4h"
        )
        assert response.status_code == 200, response.text[:500]
        assert response.json()["decision"]["strategy_state"] == "SHORT_BIAS"
    assert calls == []


def test_snapshot_key_is_namespaced_apart_from_bundle_key():
    """The builder write key must never equal the decision bundle key."""
    assert strategy_snapshot_cache_key("eth-usdt-perp", "4h") != strategy_bundle_cache_key(
        "eth-usdt-perp", "4h"
    )
    assert strategy_snapshot_cache_key("eth-usdt-perp", "4h").startswith(
        "strategy_snapshot:"
    )


def test_builder_persists_under_snapshot_key():
    """_persist_strategy_cache must address the snapshot key."""
    import inspect

    from app.services.strategy_signal.snapshot_builder import StrategySnapshotBuilder

    source = inspect.getsource(StrategySnapshotBuilder._persist_strategy_cache)
    assert "strategy_snapshot_cache_key" in source
    assert "strategy_bundle_cache_key(instrument_id, timeframe)" not in source


@pytest.mark.asyncio
async def test_scan_live_rebuilds_when_inputs_newer(monkeypatch) -> None:
    """Live-scan (2026-09-23): a cached scan row older than its unified
    inputs must be rebuilt inline instead of served stale — otherwise the
    ranked cards contradict the drawers (OKB 1d 94.6 @ 04:47 vs dissolved
    direction @ 05:14)."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    class _ScanRow:
        cache_state = "fresh"
        status = "ready"
        snapshot_at = now - timedelta(hours=1)
        expires_at = now + timedelta(hours=1)
        payload_json = {
            "matrix": [],
            "ranked": [],
            "scanned_at": (now - timedelta(hours=1)).isoformat(),
            "cache_meta": {"source": "cache"},
        }

    class _UnifiedRow:
        cache_state = "fresh"
        snapshot_at = now

    async def fake_cache(self, cache_key: str):  # noqa: ARG001
        if cache_key.startswith("strategy_scan:"):
            return _ScanRow()
        if cache_key.startswith("strategy_unified:"):
            return _UnifiedRow()
        return None

    rebuilt: list[str] = []

    async def fake_scan_all(self, instrument_ids, instrument_codes, **kwargs):  # noqa: ARG001
        rebuilt.append("scan_all")

        from app.services.strategy_unified.opportunity_scanner import ScanResult

        return ScanResult(
            scanned_at=now.isoformat(),
            instruments=list(instrument_ids),
            timeframes=["1w", "1d", "4h"],
            matrix=[],
            ranked=[],
            cache_meta={"source": "live"},
        )

    async def fake_instruments(self):
        class _Inst:
            instrument_id = "btc-usdt-perp"
            base_ccy = "BTC"
            symbol = "BTC_USDT"

        return [_Inst()]

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    async def noop_hint(self, payload):  # noqa: ARG001
        from app.schemas.market import PrecomputeHintResponse

        return PrecomputeHintResponse(status="accepted", queue_depth=0)

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        fake_cache,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments",
        fake_instruments,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_all",
        fake_scan_all,
    )
    monkeypatch.setattr(
        "app.services.precompute.precompute_service.enqueue_hint", noop_hint
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    app.dependency_overrides[get_db_writer_session] = _dummy_db_session
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
        assert response.status_code == 200, response.text[:500]
        assert response.json()["cache_meta"]["source"] == "live"
    assert rebuilt == ["scan_all"]


@pytest.mark.asyncio
async def test_scan_serves_cache_when_inputs_not_newer(monkeypatch) -> None:
    """Same setup but the scan row is newest → serve cache, no rebuild."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    class _ScanRow:
        cache_state = "fresh"
        status = "ready"
        snapshot_at = now
        expires_at = now + timedelta(hours=1)
        payload_json = {
            "matrix": [],
            "ranked": [],
            "scanned_at": now.isoformat(),
            "cache_meta": {"source": "cache"},
        }

    class _UnifiedRow:
        cache_state = "fresh"
        snapshot_at = now - timedelta(hours=1)

    async def fake_cache(self, cache_key: str):  # noqa: ARG001
        if cache_key.startswith("strategy_scan:"):
            return _ScanRow()
        if cache_key.startswith("strategy_unified:"):
            return _UnifiedRow()
        return None

    async def exploding_scan_all(self, *args, **kwargs):  # noqa: ARG001
        raise AssertionError("rebuild must not run when scan row is newest")

    async def fake_instruments(self):
        return []

    async def fake_upsert(self, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.get_page_snapshot_cache",
        fake_cache,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.list_instruments",
        fake_instruments,
    )
    monkeypatch.setattr(
        "app.repositories.market_repository.MarketRepository.upsert_page_snapshot_cache",
        fake_upsert,
    )
    monkeypatch.setattr(
        "app.services.strategy_unified.opportunity_scanner.OpportunityScanner.scan_all",
        exploding_scan_all,
    )

    app = create_app(enable_lifespan=False)
    app.dependency_overrides[get_db_session] = _dummy_db_session
    app.dependency_overrides[get_db_writer_session] = _dummy_db_session
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy/scan")
        assert response.status_code == 200, response.text[:500]
        assert response.json()["cache_meta"]["source"] == "cache"


def test_strategy_index_polls_live_scan():
    """The page must re-read the scan while mounted (60 s cadence) so the
    ranked cards converge without a manual 50 s force."""
    index = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app/static/pages/strategy/index.js"
    ).read_text(encoding="utf-8")
    assert "LIVE_REFRESH_MS" in index
    assert "visibilitychange" in index
    assert "scanned_at" in index
