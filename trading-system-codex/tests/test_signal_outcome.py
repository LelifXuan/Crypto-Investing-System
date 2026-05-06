from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import SignalOutcome
from app.repositories.market_repository import MarketRepository


@pytest.fixture()
async def signal_outcome_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "signal_outcome.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_signal_outcome_round_trip(signal_outcome_db) -> None:
    signal_ts = datetime(2026, 4, 25, 8, tzinfo=UTC)
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        saved = await repo.add_signal_outcome(
            SignalOutcome(
                signal_type="structure",
                signal_ref="snap:btc:1h:bullish_alignment",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                signal_ts=signal_ts,
                entry_ref_price=Decimal("93250.5"),
                bars_1=1,
                bars_3=3,
                bars_6=6,
                bars_12=12,
                bars_24=24,
                return_1=Decimal("0.0125"),
                return_3=Decimal("0.0190"),
                return_6=Decimal("0.0260"),
                return_12=Decimal("0.0180"),
                return_24=Decimal("0.0310"),
                mfe=Decimal("0.0420"),
                mae=Decimal("-0.0110"),
                stop_hit_first=False,
                take_profit_hit_first=True,
                payload_json={"source": "test"},
            )
        )
        listed = await repo.list_signal_outcomes(instrument_id="btc-usdt-perp", timeframe="1h")

    assert saved.id is not None
    assert len(listed) == 1
    assert listed[0].signal_ref == "snap:btc:1h:bullish_alignment"
    assert listed[0].take_profit_hit_first is True
    assert listed[0].payload_json["source"] == "test"


@pytest.mark.asyncio
async def test_signal_outcome_upsert_updates_existing_row(signal_outcome_db) -> None:
    signal_ts = datetime(2026, 4, 25, 8, tzinfo=UTC)
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        await repo.add_signal_outcome(
            SignalOutcome(
                signal_type="divergence",
                signal_ref="div:rsi:btc:1h",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                signal_ts=signal_ts,
                entry_ref_price=Decimal("100"),
                return_1=Decimal("0.0100"),
                payload_json={"pass": 1},
            )
        )
        updated = await repo.add_signal_outcome(
            SignalOutcome(
                signal_type="divergence",
                signal_ref="div:rsi:btc:1h",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                signal_ts=signal_ts,
                entry_ref_price=Decimal("101"),
                return_1=Decimal("0.0200"),
                mfe=Decimal("0.0300"),
                payload_json={"pass": 2},
            )
        )
        listed = await repo.list_signal_outcomes(signal_type="divergence")

    assert len(listed) == 1
    assert updated.entry_ref_price == Decimal("101")
    assert listed[0].return_1 == Decimal("0.0200")
    assert listed[0].payload_json["pass"] == 2
