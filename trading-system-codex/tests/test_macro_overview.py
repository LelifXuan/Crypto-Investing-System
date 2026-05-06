from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import MacroEventCalendar
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro_overview import MacroOverviewService


@pytest.fixture()
async def macro_overview_db(tmp_path, monkeypatch):
    db_path = tmp_path / "macro_overview.db"
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
async def test_macro_overview_returns_six_layers(macro_overview_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()

        async def fake_fred_latest(symbol: str):
            values = {
                "DFF": Decimal("4.25"),
                "DGS2": Decimal("3.95"),
                "DGS10": Decimal("3.72"),
            }
            return datetime(2026, 4, 1, tzinfo=UTC), values[symbol]

        monkeypatch.setattr(monitoring, "_fred_latest", fake_fred_latest)
        await monitoring.sync_macro()

        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 4, 9, 8, 0, tzinfo=UTC)
        )

    assert len(overview.layers) == 6
    assert overview.policy_score <= 100
    assert overview.inflation_score <= 100
    assert overview.growth_score <= 100
    assert overview.liquidity_score <= 100
    assert overview.regime_label_cn
    assert overview.operation_bias in {"做多", "做空", "减仓", "平仓", "观望"}
    assert any(layer.layer_key == "rates_policy" for layer in overview.layers)
    assert any(
        item.indicator_key == "us_dff" for layer in overview.layers for item in layer.indicators
    )


@pytest.mark.asyncio
async def test_macro_overview_event_window_statuses(macro_overview_db) -> None:
    now = datetime(2026, 4, 9, 8, 0, tzinfo=UTC)
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        await repo.upsert_macro_event(
            MacroEventCalendar(
                event_id="event-cpi-near",
                provider_key="bls",
                event_key="us_cpi",
                country_code="US",
                title="US CPI (2026-04)",
                scheduled_at=now + timedelta(hours=12),
                actual_value_num=None,
                consensus_value_num=Decimal("2.8"),
                previous_value_num=Decimal("2.7"),
                surprise_num=None,
                importance="high",
                status="scheduled",
                source_ref=None,
                payload_json={},
            )
        )

        overview = await MacroOverviewService(repo).build_overview(now=now)

    assert overview.event_window_status == "临近发布"
    assert overview.next_event_title == "US CPI (2026-04)"
    assert overview.operation_bias == "观望"
