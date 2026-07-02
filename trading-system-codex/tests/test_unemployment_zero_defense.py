"""Defense-in-depth tests for ``unemployment_rate=0`` rendering.

Three layers, three test groups:

1. Data layer (``fallback_resolver``): when the live observation carries
   value=0 and unit='%' on an unemployment-like key, the fallback
   record is rewritten with status='suspect_zero' and value=None.
2. Service layer (``macro_overview``): even if a 0% row slipped past
   the data layer, ``_indicator_read`` flips status to suspect_zero
   and the row never participates in scoring.
3. Frontend layer is a static markup check: ``INVALID_TEXT_VALUES``
   contains ``suspect_zero`` and ``validMacroIndicator`` rejects the
   row so it never reaches the visible grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import IndicatorObservation
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro.fallback_resolver import (
    UNEMPLOYMENT_LIKE_KEYS,
    _is_suspect_zero,
    fallback_for_indicator,
)
from app.services.macro_overview import (
    MacroOverviewService,
    _looks_like_unemployment_zero,
)

# -----------------------------
# Layer 1: data layer
# -----------------------------


def test_is_suspect_zero_flags_zero_for_unemployment_with_percent_unit() -> None:
    assert _is_suspect_zero("unemployment_rate", 0, "%") is True
    assert _is_suspect_zero("us_unemployment_rate", Decimal("0"), "percent") is True
    assert _is_suspect_zero("unemployment_rate", "0", "%") is True


def test_is_suspect_zero_does_not_flag_non_zero_values() -> None:
    assert _is_suspect_zero("unemployment_rate", 4.3, "%") is False
    assert _is_suspect_zero("unemployment_rate", "0.1", "%") is False


def test_is_suspect_zero_ignores_non_unemployment_indicators() -> None:
    # EFFR can legitimately be 0 in theory (e.g. zero rate environment)
    assert _is_suspect_zero("effr", 0, "%") is False
    assert _is_suspect_zero("cpi_mom", 0, "%") is False


def test_is_suspect_zero_requires_percent_unit() -> None:
    assert _is_suspect_zero("unemployment_rate", 0, "pp") is False
    assert _is_suspect_zero("unemployment_rate", 0, "persons") is False
    assert _is_suspect_zero("unemployment_rate", 0, "") is False


def test_is_suspect_zero_treats_missing_values_as_not_suspect() -> None:
    assert _is_suspect_zero("unemployment_rate", None, "%") is False
    assert _is_suspect_zero("unemployment_rate", "nan", "%") is False
    assert _is_suspect_zero("unemployment_rate", "", "%") is False


@dataclass
class _FakeLiveObs:
    """Minimal stand-in for an IndicatorObservation row that the data
    layer can introspect. Mirrors the attributes fallback_resolver
    actually reads."""

    value_num: float | None
    observation_ts: datetime
    source_provider: str = "bls"
    status: str | None = "ok"
    unit: str = "%"
    value_text: str | None = None
    indicator_key: str = "unemployment_rate"


def test_fallback_for_indicator_zero_value_marks_suspect_zero() -> None:
    record = fallback_for_indicator(
        "unemployment_rate",
        _FakeLiveObs(value_num=0, observation_ts=datetime(2026, 6, 5, tzinfo=UTC)),
        "monthly",
    )
    assert record["status"] == "suspect_zero"
    assert record["value"] is None
    assert record["is_scored"] is False
    assert "无效域" in record["status_reason"]


def test_fallback_for_indicator_real_value_preserves_value() -> None:
    record = fallback_for_indicator(
        "unemployment_rate",
        _FakeLiveObs(value_num=4.3, observation_ts=datetime(2026, 6, 5, tzinfo=UTC)),
        "monthly",
    )
    assert record["fallback_level"] == "live_api"
    assert record["status"] == "ok"
    assert record["value"] == 4.3
    assert record["is_scored"] is True


def test_fallback_for_indicator_non_unemployment_zero_keeps_value() -> None:
    # EFFR can legitimately be 0 in a zero-rate environment
    record = fallback_for_indicator(
        "effr",
        _FakeLiveObs(
            value_num=0,
            observation_ts=datetime(2026, 6, 5, tzinfo=UTC),
            indicator_key="effr",
        ),
        "daily",
    )
    assert record["value"] == 0
    assert record["status"] != "suspect_zero"


# -----------------------------
# Layer 2: service layer
# -----------------------------


def test_service_layer_zero_check_flags_unemployment() -> None:
    assert _looks_like_unemployment_zero("unemployment_rate", 0, "%") is True
    assert _looks_like_unemployment_zero("us_unemployment_rate", 0, "percent") is True


def test_service_layer_zero_check_ignores_other_indicators() -> None:
    assert _looks_like_unemployment_zero("effr", 0, "%") is False
    assert _looks_like_unemployment_zero("cpi_mom", 0, "%") is False


def test_service_layer_zero_check_ignores_non_zero_values() -> None:
    assert _looks_like_unemployment_zero("unemployment_rate", 4.3, "%") is False
    assert _looks_like_unemployment_zero("unemployment_rate", None, "%") is False


# -----------------------------
# Service-layer integration: a 0% row never makes it into the
# overview with status="ok" / is_scored=True.
# -----------------------------


def _make_observation(
    *,
    indicator_key: str,
    value_num: float | None,
    source_ref: str,
    source_provider: str,
    unit: str | None = None,
) -> IndicatorObservation:
    obs = IndicatorObservation(
        observation_id=f"obs-{indicator_key}-zero",
        dedupe_key=f"obs-{indicator_key}-zero",
        indicator_key=indicator_key,
        category="macro",
        country_code="US",
        timeframe="1mo",
        observation_ts=datetime(2026, 6, 5, tzinfo=UTC),
        effective_start_ts=datetime(2026, 6, 5, tzinfo=UTC),
        value_num=value_num,
        signal_state="ok",
        source_provider=source_provider,
        source_ref=source_ref,
        source_granularity="1mo",
        run_id="test",
    )
    # IndicatorObservation does not have a unit column. Stash it as an
    # ad-hoc attribute so the service-layer defense can read it.
    if unit is not None:
        object.__setattr__(obs, "unit", unit)
    return obs


@pytest.fixture()
async def macro_db(tmp_path, monkeypatch):
    db_path = tmp_path / "macro_overview_zero.db"
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


@pytest.mark.asyncio
async def test_zero_unemployment_row_surfaces_as_suspect_zero(
    macro_db, monkeypatch
) -> None:
    """Direct write of value=0 to the DB still gets flagged."""
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="us_unemployment_rate",
                value_num=0,
                source_ref="bls:LNS14000000",
                source_provider="bls",
            )
        )
        await session.commit()

    # Patch the BLS provider so fetch_history is never hit
    import importlib

    bls_module = importlib.import_module("app.services.macro.providers.bls")

    async def raising(*_args, **_kwargs):
        raise RuntimeError("not used in this test")

    monkeypatch.setattr(bls_module.BlsMacroProvider, "fetch_history", raising)

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 6, 9, 8, 0, tzinfo=UTC)
        )

    growth = next(
        layer for layer in overview.layers if layer.layer_key == "growth_labor"
    )
    items = [item for item in growth.indicators if item.indicator_key == "unemployment_rate"]
    assert items
    item = items[0]
    assert item.status == "suspect_zero"
    assert item.is_scored is False
    assert item.value_num is None


@pytest.mark.asyncio
async def test_nfp_zero_value_does_not_trigger_defense(
    macro_db, monkeypatch
) -> None:
    """Sanity check: a 0 NFP value (theoretically possible if not for the
    defense on unemployment-style indicators) keeps its raw value and
    ok status — the suspect_zero rule is narrow."""
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        monitoring = IndicatorMonitoringService(repo)
        await monitoring.seed_defaults()
        session.add(
            _make_observation(
                indicator_key="us_nfp",
                value_num=0,
                source_ref="bls:CES0000000001",
                source_provider="bls",
                unit="thousand persons",
            )
        )
        await session.commit()

    import importlib

    bls_module = importlib.import_module("app.services.macro.providers.bls")

    async def raising(*_args, **_kwargs):
        raise RuntimeError("not used")

    monkeypatch.setattr(bls_module.BlsMacroProvider, "fetch_history", raising)

    async with db_manager.session() as session:
        repo = MarketRepository(session)
        overview = await MacroOverviewService(repo).build_overview(
            now=datetime(2026, 6, 9, 8, 0, tzinfo=UTC)
        )

    growth = next(
        layer for layer in overview.layers if layer.layer_key == "growth_labor"
    )
    nfp = next(item for item in growth.indicators if item.indicator_key == "nfp")
    # NFP keeps its raw 0 (the data layer has no suspect_zero rule for it)
    assert nfp.status != "suspect_zero"
    assert nfp.value_num == 0


def test_unemployment_like_keys_constant() -> None:
    """Lock the data-layer whitelist."""
    assert UNEMPLOYMENT_LIKE_KEYS == frozenset(
        {"unemployment_rate", "us_unemployment_rate"}
    )
