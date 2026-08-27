from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.instrument import Instrument
from app.db.models.market import (
    VolatilityFeatureObservation,
    VolatilityResearchSnapshot,
)
from app.repositories.market_repository import MarketRepository

UTC = timezone.utc


def _snapshot(snapshot_id: str = "vol-test") -> VolatilityResearchSnapshot:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    return VolatilityResearchSnapshot(
        snapshot_id=snapshot_id,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        event_time=now,
        available_at=now,
        calculated_at=now,
        formula_version="btc-native-vol-research-v1",
        integration_status="shadow",
        price_volatility_json={"status": "ready"},
        options_expectations_json={"status": "data_insufficient"},
        tail_pricing_json={"status": "data_insufficient"},
        leverage_crowding_json={"status": "data_insufficient"},
        liquidation_pressure_json={"status": "data_insufficient"},
        basis_funding_structure_json={"status": "data_insufficient"},
        quality_json={"no_canonical_effect": True},
        timestamp_contract_json={"valid": True},
    )


def _observation(snapshot_id: str = "vol-test") -> VolatilityFeatureObservation:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    return VolatilityFeatureObservation(
        observation_id="vf-test",
        snapshot_id=snapshot_id,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        feature_key="rv_close_short",
        parameter_set_id="params-test",
        value_num=Decimal("0.512345678901234567"),
        unit="annualized_decimal",
        event_time=now,
        available_at=now,
        calculated_at=now,
        formula_version="btc-native-vol-research-v1",
        source="fixture",
        quality_status="ok",
        parameters_json={"window": 14},
    )


@pytest.mark.asyncio
async def test_repository_appends_decimal_snapshot_and_is_idempotent(tmp_path) -> None:
    database = tmp_path / "volatility-research.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="gateio",
                symbol="BTC_USDT",
                asset_class="crypto",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.0001"),
                contract_multiplier=Decimal(1),
                margin_model="linear",
                metadata_json={},
            )
        )
        await session.commit()

        repository = MarketRepository(session)
        original = await repository.append_volatility_research_snapshot(
            _snapshot(), [_observation()]
        )
        await session.commit()
        duplicate = _snapshot()
        duplicate.integration_status = "accepted"
        returned = await repository.append_volatility_research_snapshot(duplicate, [])
        await session.commit()

        assert returned.snapshot_id == original.snapshot_id
        assert returned.integration_status == "shadow"
        count = await session.scalar(select(func.count(VolatilityResearchSnapshot.snapshot_id)))
        feature_count = await session.scalar(
            select(func.count(VolatilityFeatureObservation.observation_id))
        )
        assert count == 1
        assert feature_count == 1
        rows = await repository.list_volatility_feature_observations("vol-test")
        assert rows[0].value_num == Decimal("0.512345678901234567")
    await engine.dispose()
