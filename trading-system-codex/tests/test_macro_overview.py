from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import MacroEventCalendar
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro_overview import MacroOverviewService, _unit_for_indicator

BAD_TEXT_TOKENS = ("????", "\ufffd", "\u951f", "\u934b", "\u7039", "\u93c6")
LONG_DECIMAL_RE = re.compile(r"\d+\.\d{3,}")


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


def test_macro_overview_units_for_key_macro_indicators() -> None:
    assert _unit_for_indicator("average_hourly_earnings_yoy") == "%"
    assert _unit_for_indicator("reverse_repo") == "USD billion"
    assert _unit_for_indicator("reverse_repo", "USD million") == "USD billion"
    assert _unit_for_indicator("m2") == "USD billion"


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
    assert overview.operation_bias in {"bullish", "bearish", "neutral", "observe"}
    assert any(layer.layer_key == "rates_policy" for layer in overview.layers)
    assert any(
        item.indicator_key in {"effr", "us_dff"}
        for layer in overview.layers
        for item in layer.indicators
    )
    assert all(item.status_reason for layer in overview.layers for item in layer.indicators)
    assert all(
        token not in item.label + item.insight
        for layer in overview.layers
        for item in layer.indicators
        for token in BAD_TEXT_TOKENS
    )
    assert all(
        not LONG_DECIMAL_RE.search(item.insight)
        for layer in overview.layers
        for item in layer.indicators
    )
    assert all(
        "当前值" not in item.insight and "已纳入宏观总分" not in item.insight
        for layer in overview.layers
        for item in layer.indicators
    )
    labels = {item.indicator_key: item.label for layer in overview.layers for item in layer.indicators}
    assert labels["effr"] == "美国有效联邦基金利率"
    assert labels["us10y_yield"] == "美国10年期国债收益率"


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
    assert overview.operation_bias == "observe"
