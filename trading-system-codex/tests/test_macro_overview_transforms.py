"""Integration tests for ``MacroOverviewService`` transform application.

Verifies that the 4 transform-affected keys get their values recomputed
from a multi-point FRED/BLS history window and that provider failures
fall back to the original observation without crashing the overview.

The api_map configures:
- cpi_mom / core_cpi_mom    -> transform: mom_pct  (primary source: BLS)
- pce_yoy  / core_pce_yoy   -> transform: yoy_pct  (primary source: FRED)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import IndicatorObservation
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro.providers.base import MacroFetchPoint
from app.services.macro_overview import (
    TRANSFORM_AFFECTED_KEYS,
    MacroOverviewService,
)


def _make_observation(
    *,
    indicator_key: str,
    value_num: Decimal | None,
    source_ref: str,
    source_provider: str,
    signal_state: str = "ok",
) -> IndicatorObservation:
    return IndicatorObservation(
        observation_id=f"obs-{indicator_key}-test",
        dedupe_key=f"obs-{indicator_key}-test",
        indicator_key=indicator_key,
        category="macro",
        country_code="US",
        timeframe="1mo",
        observation_ts=datetime(2026, 4, 1, tzinfo=UTC),
        effective_start_ts=datetime(2026, 4, 1, tzinfo=UTC),
        value_num=value_num,
        signal_state=signal_state,
        source_provider=source_provider,
        source_ref=source_ref,
        source_granularity="1mo",
        run_id="test",
    )


@pytest.fixture()
async def macro_db(tmp_path, monkeypatch):
    db_path = tmp_path / "macro_overview.db"
    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield
    finally:
        await db_manager.disconnect()


def _series(latest_value: str, monthly_increment: str, count: int) -> list[MacroFetchPoint]:
    """Build ``count`` ascending monthly points ending at ``latest_value``
    with a constant ``monthly_increment`` step between consecutive points."""
    base = float(latest_value) - monthly_increment_increments(monthly_increment, count)
    points: list[MacroFetchPoint] = []
    year, month = 2025, 5
    for i in range(count):
        value = base + (i + 1) * float(monthly_increment)
        points.append(
            MacroFetchPoint(
                observation_ts=datetime(year, month, 1, tzinfo=UTC),
                value=Decimal(str(round(value, 3))),
                status="ok",
            )
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return points


def monthly_increment_increments(increment: str, count: int) -> float:
    """Given a step size, return the cumulative step from point 1 to point ``count``."""
    return float(increment) * (count - 1)


def _patch_provider_history(
    monkeypatch, history: list[MacroFetchPoint], provider_name: str
) -> None:
    """Patch a provider's ``fetch_history`` at the class level so the
    service's freshly-constructed MacroProviderRegistry picks it up."""
    import importlib

    module = importlib.import_module(f"app.services.macro.providers.{provider_name}")
    class_name = "BlsMacroProvider" if provider_name == "bls" else "FredMacroProvider"
    provider_class = getattr(module, class_name)

    async def fake_fetch_history(*args, **kwargs):
        return history

    monkeypatch.setattr(provider_class, "fetch_history", fake_fetch_history)


@pytest.mark.asyncio
async def test_cpi_mom_applies_mom_transform(macro_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="cpi_mom",
                value_num=Decimal("332.407"),
                source_ref="bls:CUSR0000SA0",
                source_provider="bls",
            )
        )
        await session.commit()

    # 14 monthly points ending at 333.0, step +1.0 → mom = 1.0/332.0 = ~0.3%
    history = _series(latest_value="333.0", monthly_increment="1.0", count=14)
    _patch_provider_history(monkeypatch, history, "bls")

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        )

    inflation = next(
        layer for layer in overview.layers if layer.layer_key == "inflation"
    )
    cpi_mom = next(
        item for item in inflation.indicators if item.indicator_key == "cpi_mom"
    )
    assert cpi_mom.transform_applied == "mom_pct"
    assert cpi_mom.unit == "%"
    assert cpi_mom.value_num is not None
    # 14th point is 333.0, 13th point is 332.0 → 1.0/332.0 = 0.301%
    assert 0.2 <= float(cpi_mom.value_num) <= 0.4


@pytest.mark.asyncio
async def test_pce_yoy_applies_yoy_transform(macro_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="pce_yoy",
                value_num=Decimal("130.902"),
                source_ref="fred:PCEPI",
                source_provider="fred",
            )
        )
        await session.commit()

    # 14 monthly points: 12 months ago = 100, latest = 103 → yoy = 3.0%
    points: list[MacroFetchPoint] = []
    year, month = 2025, 5
    for _i in range(13):
        points.append(
            MacroFetchPoint(
                observation_ts=datetime(year, month, 1, tzinfo=UTC),
                value=Decimal("100"),
                status="ok",
            )
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    points.append(
        MacroFetchPoint(
            observation_ts=datetime(2026, 5, 1, tzinfo=UTC),
            value=Decimal("103"),
            status="ok",
        )
    )
    _patch_provider_history(monkeypatch, points, "fred")

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        )

    inflation = next(
        layer for layer in overview.layers if layer.layer_key == "inflation"
    )
    pce_yoy = next(
        item for item in inflation.indicators if item.indicator_key == "pce_yoy"
    )
    assert pce_yoy.transform_applied == "yoy_pct"
    assert pce_yoy.unit == "%"
    assert pce_yoy.value_num is not None
    assert abs(float(pce_yoy.value_num) - 3.0) < 0.01


@pytest.mark.asyncio
async def test_transform_failure_falls_back_to_original_value(
    macro_db, monkeypatch
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        original_value = Decimal("332.407")
        session.add(
            _make_observation(
                indicator_key="cpi_mom",
                value_num=original_value,
                source_ref="bls:CUSR0000SA0",
                source_provider="bls",
            )
        )
        await session.commit()

    import importlib
    module = importlib.import_module("app.services.macro.providers.bls")

    async def raising_history(*_args, **_kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(module.BlsMacroProvider, "fetch_history", raising_history)

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        )

    inflation = next(
        layer for layer in overview.layers if layer.layer_key == "inflation"
    )
    cpi_mom = next(
        item for item in inflation.indicators if item.indicator_key == "cpi_mom"
    )
    # no transform applied, original value preserved
    assert cpi_mom.transform_applied is None
    assert cpi_mom.value_num == original_value


@pytest.mark.asyncio
async def test_transform_does_not_affect_unrelated_indicators(
    macro_db, monkeypatch
) -> None:
    """Sanity check: even when BLS fetch_history is mocked, indicators
    not in TRANSFORM_AFFECTED_KEYS keep their original behaviour."""
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="us_dff",
                value_num=Decimal("4.25"),
                source_ref="fred:DFF",
                source_provider="fred",
            )
        )
        await session.commit()

    points = _series(latest_value="333.0", monthly_increment="1.0", count=14)
    _patch_provider_history(monkeypatch, points, "bls")

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        )

    rates = next(
        layer for layer in overview.layers if layer.layer_key == "rates_policy"
    )
    effr_aliases = [
        item for item in rates.indicators
        if item.indicator_key in {"effr", "us_dff"}
    ]
    assert effr_aliases, "expected effr or us_dff in rates_policy layer"
    item = effr_aliases[0]
    # Indicator key resolved via _find_observation + aliases; transform must not
    # have been applied to non-affected rows.
    assert item.transform_applied is None
    if item.indicator_key == "us_dff":
        assert item.value_num == Decimal("4.25")


@pytest.mark.asyncio
async def test_unemployment_rate_row_missing_uses_placeholder(
    macro_db, monkeypatch
) -> None:
    """When the DB has no observation for unemployment_rate, the
    service surfaces an unavailable_placeholder instead of fabricating
    a value (0 or otherwise)."""
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        await session.commit()

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        )

    growth = next(
        layer for layer in overview.layers if layer.layer_key == "growth_labor"
    )
    items = [item for item in growth.indicators if item.indicator_key == "unemployment_rate"]
    assert items, "unemployment_rate should still be in the growth_labor layer"
    item = items[0]
    assert item.value_num is None
    assert item.status in {"missing", "unavailable_placeholder"}


def test_transform_affected_keys_constant() -> None:
    """Lock the whitelist so future drift is intentional."""
    assert TRANSFORM_AFFECTED_KEYS == frozenset(
        {
            "cpi_mom",
            "core_cpi_mom",
            "pce_yoy",
            "core_pce_yoy",
            "average_hourly_earnings_yoy",
        }
    )
