from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.services.precompute import precompute_service


@pytest.fixture()
async def precompute_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "precompute.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    async with db_manager.session() as session:
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="GATEIO",
                symbol="BTC_USDT",
                asset_class="PERP",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
                },
            )
        )
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_page_snapshot_cache_repo_roundtrip(precompute_db) -> None:
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        now = datetime.now(UTC)
        created = await repository.upsert_page_snapshot_cache(
            cache_key="analysis:btc-usdt-perp:1d:default",
            page_type="analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            payload_json={"hello": "world"},
            status="ready",
            snapshot_at=now,
            expires_at=now,
            source_updated_at=now,
            meta_json={"view_window": "default"},
        )
        fetched = await repository.get_page_snapshot_cache(created.cache_key)

    assert fetched is not None
    assert fetched.page_type == "analysis"
    assert fetched.payload_json["hello"] == "world"


@pytest.mark.asyncio
async def test_precompute_hint_analysis_expands_related_tasks(precompute_db) -> None:
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="test",
            priority=3,
        )
    )

    assert response.status in {"accepted", "deduped"}
    assert response.queue_depth >= 0
    assert (
        any(key.startswith("analysis:btc-usdt-perp:1d:500:") for key in response.queued_keys)
        or response.status == "deduped"
    )


@pytest.mark.asyncio
async def test_precompute_task_status_reports_queued_task(precompute_db) -> None:
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="manual_refresh_click",
            priority=2,
        )
    )

    task_key = (
        response.queued_keys[0] if response.queued_keys else "analysis:btc-usdt-perp:1d:420:v2"
    )
    status = await precompute_service.task_status(task_key)

    assert status.status in {"queued", "running", "missing"}
    if status.status != "missing":
        assert status.cache_key
        assert status.task_type


@pytest.mark.asyncio
async def test_precompute_task_status_endpoint(precompute_db) -> None:
    response = await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            view_window="default",
            reason="manual_refresh_click",
            priority=2,
        )
    )
    task_key = (
        response.queued_keys[0] if response.queued_keys else "analysis:btc-usdt-perp:1d:420:v2"
    )

    with TestClient(create_app(enable_lifespan=False)) as client:
        task_response = client.get(f"/api/v1/precompute/tasks/{task_key}")

    assert task_response.status_code == 200
    payload = task_response.json()
    assert payload["status"] in {"queued", "running", "missing"}


@pytest.mark.asyncio
async def test_bundle_endpoints_return_missing_state_without_blocking(precompute_db) -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        analysis_response = client.get(
            "/api/v1/analysis/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "view_window": "default",
            },
        )
        structure_response = client.get(
            "/api/v1/structure/tab/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "include_geometry": "true",
                "candles_limit": 180,
            },
        )

    assert analysis_response.status_code == 200
    assert structure_response.status_code == 200
    assert analysis_response.json()["status"] == "missing"
    assert analysis_response.json()["cache_state"] == "missing"
    assert structure_response.json()["cache_state"] == "missing"
