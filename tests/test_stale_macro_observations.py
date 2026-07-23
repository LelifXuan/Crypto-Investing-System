"""Tests for ``scripts/stale_macro_observations.py``.

The script connects to a real SQLite database; we point it at a
temporary database via monkeypatching ``db_manager.database_url`` to
keep tests offline.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "stale_macro_observations.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("stale_macro_observations", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_observation(
    *,
    indicator_key: str,
    value_num: Decimal | None,
    observation_id: str,
    dedupe_key: str,
    status: str = "ok",
) -> "IndicatorObservation":  # noqa: F821
    from app.db.models.market import IndicatorObservation

    return IndicatorObservation(
        observation_id=observation_id,
        dedupe_key=dedupe_key,
        indicator_key=indicator_key,
        category="macro",
        country_code="US",
        timeframe="1mo",
        observation_ts=datetime(2026, 4, 1, tzinfo=UTC),
        effective_start_ts=datetime(2026, 4, 1, tzinfo=UTC),
        value_num=value_num,
        signal_state=status,
        source_provider="fred",
        source_ref="fred:test",
        source_granularity="1mo",
        run_id="test",
    )


@pytest.fixture()
async def script_db(tmp_path, monkeypatch):
    db_path = tmp_path / "stale_macro.db"
    from app.core.config import settings
    from app.core.db import db_manager

    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield db_manager
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_marks_cpi_mom_index_rows_as_stale(script_db, monkeypatch) -> None:
    from app.db.models.market import IndicatorObservation
    from app.repositories.market_repository import MarketRepository
    from app.services.indicator_monitoring import IndicatorMonitoringService

    script = _load_script()
    async with script_db.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add_all(
            [
                _make_observation(
                    indicator_key="cpi_mom",
                    value_num=Decimal("332.407"),
                    observation_id="obs-cpi-mom-stale",
                    dedupe_key="k-cpi-mom-stale",
                ),
                _make_observation(
                    indicator_key="pce_yoy",
                    value_num=Decimal("130.902"),
                    observation_id="obs-pce-yoy-stale",
                    dedupe_key="k-pce-yoy-stale",
                ),
            ]
        )
        await session.commit()

    updated = await script.mark_stale(
        dry_run=False, auto_yes=True, manage_lifecycle=False
    )
    assert updated == 2

    from sqlalchemy import select

    async with script_db.session() as session:
        rows = list((await session.execute(select(IndicatorObservation))).scalars())
    states = {r.indicator_key: (r.signal_state, r.value_text) for r in rows}
    assert states["cpi_mom"][0] == "stale_index_value"
    assert "口径异常" in (states["cpi_mom"][1] or "")
    assert states["pce_yoy"][0] == "stale_index_value"
    assert "口径异常" in (states["pce_yoy"][1] or "")


@pytest.mark.asyncio
async def test_dry_run_does_not_modify_rows(script_db) -> None:
    from sqlalchemy import select

    from app.db.models.market import IndicatorObservation
    from app.repositories.market_repository import MarketRepository
    from app.services.indicator_monitoring import IndicatorMonitoringService

    script = _load_script()
    async with script_db.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="cpi_mom",
                value_num=Decimal("332.407"),
                observation_id="obs-cpi-mom-dry",
                dedupe_key="k-cpi-mom-dry",
            )
        )
        await session.commit()

    updated = await script.mark_stale(
        dry_run=True, auto_yes=True, manage_lifecycle=False
    )
    assert updated == 0

    async with script_db.session() as session:
        rows = list((await session.execute(select(IndicatorObservation))).scalars())
    assert len(rows) == 1
    assert rows[0].signal_state == "ok"  # untouched


@pytest.mark.asyncio
async def test_does_not_touch_small_values(script_db) -> None:
    from sqlalchemy import select

    from app.db.models.market import IndicatorObservation
    from app.repositories.market_repository import MarketRepository
    from app.services.indicator_monitoring import IndicatorMonitoringService

    script = _load_script()
    async with script_db.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="cpi_mom",
                value_num=Decimal("0.3"),  # real MoM %
                observation_id="obs-cpi-mom-real",
                dedupe_key="k-cpi-mom-real",
            )
        )
        await session.commit()

    updated = await script.mark_stale(
        dry_run=False, auto_yes=True, manage_lifecycle=False
    )
    assert updated == 0

    async with script_db.session() as session:
        rows = list((await session.execute(select(IndicatorObservation))).scalars())
    assert rows[0].signal_state == "ok"


@pytest.mark.asyncio
async def test_does_not_touch_unrelated_indicators(script_db) -> None:
    from sqlalchemy import select

    from app.db.models.market import IndicatorObservation
    from app.repositories.market_repository import MarketRepository
    from app.services.indicator_monitoring import IndicatorMonitoringService

    script = _load_script()
    async with script_db.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add_all(
            [
                _make_observation(
                    indicator_key="us_dff",
                    value_num=Decimal("4.25"),
                    observation_id="obs-usdff",
                    dedupe_key="k-usdff",
                ),
                _make_observation(
                    indicator_key="real_yield_10y",
                    value_num=Decimal("2.5"),
                    observation_id="obs-real10",
                    dedupe_key="k-real10",
                ),
            ]
        )
        await session.commit()

    updated = await script.mark_stale(
        dry_run=False, auto_yes=True, manage_lifecycle=False
    )
    assert updated == 0

    async with script_db.session() as session:
        rows = list((await session.execute(select(IndicatorObservation))).scalars())
    states = {r.indicator_key: r.signal_state for r in rows}
    assert states["us_dff"] == "ok"
    assert states["real_yield_10y"] == "ok"


@pytest.mark.asyncio
async def test_no_candidates_returns_zero(script_db) -> None:
    script = _load_script()
    updated = await script.mark_stale(
        dry_run=False, auto_yes=True, manage_lifecycle=False
    )
    assert updated == 0
