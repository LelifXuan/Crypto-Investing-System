"""Tests for ``app.services.onchain.policy_adapter``.

The adapter turns DefiLlama public snapshots into ``IndicatorObservation``
rows. Tests use httpx's dummy transport so no real network call ever leaves
the test process.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.repositories.market_repository import MarketRepository
from app.services.onchain.policy_adapter import (
    CORE_KEYS,
    DefiLlamaPolicyAdapter,
    collect_via_router,
    ensure_defillama_definitions,
    persist_drafts,
)
from app.services.onchain.providers.defillama import DefiLlamaSnapshot


def _live_snapshot() -> DefiLlamaSnapshot:
    return DefiLlamaSnapshot(
        status="live",
        indicators={
            "defi_total_tvl": 50_000_000_000.0,
            "stablecoin_total_mcap": 180_000_000_000.0,
            "dex_volume_24h": 4_000_000_000.0,
            "protocol_fees_24h": 8_000_000.0,
        },
        missing_fields=[],
    )


def _degraded_snapshot() -> DefiLlamaSnapshot:
    return DefiLlamaSnapshot(
        status="data_insufficient",
        indicators={"defi_total_tvl": 1.0},
        missing_fields=[
            "defi_total_tvl",
            "stablecoin_total_mcap",
            "dex_volume_24h",
            "protocol_fees_24h",
        ],
    )


class _StubProvider:
    def __init__(self, snapshot: DefiLlamaSnapshot) -> None:
        self.snapshot = snapshot

    async def fetch_snapshot(self, **_) -> DefiLlamaSnapshot:
        return self.snapshot


@pytest.mark.asyncio
async def test_defillama_policy_adapter_collects_live_snapshot() -> None:
    adapter = DefiLlamaPolicyAdapter(provider=_StubProvider(_live_snapshot()))
    outcome = await adapter.collect(now=datetime(2026, 7, 2, tzinfo=UTC))
    assert outcome.meta["status"] == "live"
    assert outcome.meta["missing_keys"] == []
    assert len(outcome.drafts) == len(CORE_KEYS)
    fresh = [d for d in outcome.drafts if d.signal_state == "fresh"]
    assert len(fresh) == len(CORE_KEYS)
    assert all(d.value_num is not None for d in fresh)


@pytest.mark.asyncio
async def test_defillama_policy_adapter_marks_missing_when_degraded() -> None:
    adapter = DefiLlamaPolicyAdapter(provider=_StubProvider(_degraded_snapshot()))
    outcome = await adapter.collect(now=datetime(2026, 7, 2, tzinfo=UTC))
    assert outcome.meta["status"] == "degraded"
    missing = [d for d in outcome.drafts if d.signal_state == "missing"]
    assert len(missing) == len(CORE_KEYS)
    assert all(d.value_num is None for d in missing)
    assert all(d.value_json["source"] == "defillama" for d in missing)


@pytest.mark.asyncio
async def test_collect_via_router_returns_drafts_with_source_marker() -> None:
    class _Router:
        async def fetch_metric(self, indicator_key: str) -> dict:
            return {
                "provider": "defillama",
                "status": "live",
                "value": 12.0 if indicator_key == "defi_total_tvl" else 7.0,
                "indicators": {indicator_key: 12.0 if indicator_key == "defi_total_tvl" else 7.0},
                "missing_fields": [],
            }

    outcome = await collect_via_router(_Router())
    assert outcome.meta["status"] == "live"
    for draft in outcome.drafts:
        assert draft.value_json["source"] == "defillama"
        assert draft.value_json["status"] == "live"
        expected = Decimal("12.0") if draft.indicator_key == "defi_total_tvl" else Decimal("7.0")
        assert draft.value_num == expected


@pytest.mark.asyncio
async def test_collect_via_router_propagates_missing_keys() -> None:
    class _Router:
        async def fetch_metric(self, indicator_key: str) -> dict:
            return {
                "provider": "defillama",
                "status": "degraded",
                "value": None,
                "indicators": {},
                "missing_fields": [indicator_key, "network:ConnectError"],
            }

    outcome = await collect_via_router(_Router())
    assert outcome.meta["status"] == "degraded"
    assert set(outcome.meta["missing_keys"]) >= set(CORE_KEYS)
    for draft in outcome.drafts:
        assert draft.value_num is None
        assert draft.value_json["source"] == "defillama"
        assert draft.value_json["missing"] is True


@pytest.fixture()
async def monitoring_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "policy_adapter.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_persist_drafts_writes_to_repository(monitoring_db) -> None:
    class _Router:
        async def fetch_metric(self, indicator_key: str) -> dict:
            return {
                "provider": "defillama",
                "status": "live",
                "value": 1.0,
                "indicators": {indicator_key: 1.0},
                "missing_fields": [],
            }

    async with db_manager.session() as session:
        repository = MarketRepository(session)
        await ensure_defillama_definitions(repository)
        outcome = await collect_via_router(_Router())
        written = await persist_drafts(repository, outcome.drafts)
        assert written == len(CORE_KEYS)
        observations = await repository.list_indicator_observations(category="onchain", limit=50)
        assert len(observations) >= len(CORE_KEYS)
        assert any((o.value_json or {}).get("source") == "defillama" for o in observations)


@pytest.mark.asyncio
async def test_ensure_defillama_definitions_is_idempotent(monitoring_db) -> None:
    async with db_manager.session() as session:
        repository = MarketRepository(session)
        first = await ensure_defillama_definitions(repository)
        second = await ensure_defillama_definitions(repository)
        assert first == len(CORE_KEYS)
        assert second == len(CORE_KEYS)
        definitions = await repository.list_indicator_definitions(category="onchain")
        keys = {d.indicator_key for d in definitions}
        assert set(CORE_KEYS).issubset(keys)