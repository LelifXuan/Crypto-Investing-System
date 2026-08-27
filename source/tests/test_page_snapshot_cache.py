from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.db.models.market import PageSnapshotCache, StrategyDecision
from app.repositories.market_repository import MarketRepository
from app.services.cache_registry import CACHE_SOURCE_VERSION, cache_status


@pytest.fixture()
async def cache_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "cache.db"
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
                    "gateio": {
                        "product_type": "futures",
                        "contract": "BTC_USDT",
                        "settle": "usdt",
                    }
                },
            )
        )
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_page_snapshot_cache_tracks_source_version_and_cache_state(cache_db) -> None:
    now = datetime.now(UTC)
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        created = await repository.upsert_page_snapshot_cache(
            cache_key="analysis:btc-usdt-perp:1h:720:v2",
            page_type="analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1h",
            payload_json={"ok": True},
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=now,
            expires_at=now + timedelta(seconds=60),
            source_updated_at=now,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=42,
        )

    assert created.source_version == CACHE_SOURCE_VERSION
    assert created.cache_state == "fresh"
    assert created.cost_ms == 42
    assert cache_status(created) == "fresh"


@pytest.mark.asyncio
async def test_page_snapshot_cache_upsert_updates_unique_key_atomically(cache_db) -> None:
    now = datetime.now(UTC)
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        for sequence in (1, 2):
            await repository.upsert_page_snapshot_cache(
                cache_key="macro_overview:v3",
                page_type="macro",
                payload_json={"sequence": sequence},
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
            )

        count = await session.scalar(
            select(func.count(PageSnapshotCache.cache_id)).where(
                PageSnapshotCache.cache_key == "macro_overview:v3"
            )
        )
        cached = await repository.get_page_snapshot_cache("macro_overview:v3")

    assert count == 1
    assert cached is not None
    assert cached.payload_json == {"sequence": 2}


@pytest.mark.asyncio
async def test_strategy_decision_insert_is_append_only_and_idempotent(cache_db) -> None:
    now = datetime.now(UTC)

    def decision(payload_sequence: int) -> StrategyDecision:
        return StrategyDecision(
            decision_id="strategy:active:stable-id",
            instrument_id="btc-usdt-perp",
            timeframe="4h",
            decision_ts=now,
            current_price=Decimal("65000.25"),
            action="OBSERVE",
            direction="NONE",
            confidence_score=Decimal("50.0000"),
            model_version="test-v1",
            config_version="test-v1",
            input_hash="stable-hash",
            evidence_json=[],
            conflict_json=[],
            action_plan_json={},
            payload_json={"sequence": payload_sequence},
        )

    async with db_manager.session() as session:
        repository = MarketRepository(session)
        first = await repository.add_strategy_decision(decision(1))
        duplicate = await repository.add_strategy_decision(decision(2))
        count = await session.scalar(
            select(func.count(StrategyDecision.id)).where(
                StrategyDecision.decision_id == "strategy:active:stable-id"
            )
        )

    assert count == 1
    assert first.id == duplicate.id
    assert duplicate.payload_json == {"sequence": 1}


@pytest.mark.asyncio
async def test_computed_dataset_cache_roundtrip(cache_db) -> None:
    now = datetime.now(UTC)
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        await repository.upsert_computed_dataset_cache(
            cache_key="indicator_series:btc-usdt-perp:1h:core:123:v2",
            dataset_type="indicator_series_core",
            instrument_id="btc-usdt-perp",
            timeframe="1h",
            source_data_ts=now,
            payload_json={"ema_20": [1, 2, 3]},
            cache_state="fresh",
            source_version=CACHE_SOURCE_VERSION,
            calculated_at=now,
            expires_at=now + timedelta(seconds=120),
        )
        fetched = await repository.get_computed_dataset_cache(
            "indicator_series:btc-usdt-perp:1h:core:123:v2"
        )

    assert fetched is not None
    assert fetched.dataset_type == "indicator_series_core"
    assert fetched.payload_json["ema_20"] == [1, 2, 3]
