"""Fix B (2026-07-25) — verify seed_defaults expands to all instruments.

Previously, monitor YAML entries with `scope_type: instrument` and no
explicit `instrument_id` defaulted to a single hard-coded instrument
(btc-usdt-perp). After Fix B, the same entries fan out across all
configured instruments, so the strategy page's multi-instrument scan
gets real indicator_features for every (instrument, timeframe) pair.

These tests verify the fan-out behavior end-to-end against a clean
in-memory DB with 3 instruments.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.db import db_manager
from app.db.models.market import IndicatorMonitoringPolicy
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService


async def _setup_db_with_instruments(monkeypatch, tmp_path, instrument_ids):
    """Create a fresh DB with the given instruments seeded.

    Returns a tuple of (session_factory, repo_factory). Caller is
    responsible for cleanup.
    """
    db_path = tmp_path / "seed.db"
    from app.core import config as cfg
    monkeypatch.setattr(
        cfg.settings,
        "database_url",
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
    )
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()

    async with db_manager.session() as session:
        from app.db.models.instrument import Instrument
        for iid in instrument_ids:
            session.add(Instrument(
                instrument_id=iid,
                venue="GATEIO",
                symbol=iid.upper(),
                asset_class="PERP",
                base_ccy=iid.split("-")[0].upper(),
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size="0.1",
                lot_size="0.001",
                contract_multiplier="1",
                margin_model="ISOLATED",
                metadata_json={"seeded": True},
            ))
        await session.commit()

    return db_path


@pytest.mark.asyncio
async def test_seed_defaults_expands_policy_to_each_instrument(
    monkeypatch, tmp_path
) -> None:
    """Each technical candle YAML entry without explicit instrument_id
    should expand to a per-instrument policy row, not the legacy single
    btc-usdt-perp default.
    """
    # Clear lru_cache on load_refresh_policies so the test sees the
    # current YAML contents (not whatever another test cached).
    from app.monitoring import loader as _loader
    _loader.load_refresh_policies.cache_clear()

    instruments = ["btc-usdt-perp", "eth-usdt-perp", "sol-usdt-perp"]
    await _setup_db_with_instruments(monkeypatch, tmp_path, instruments)
    try:
        async with db_manager.session() as session:
            service = IndicatorMonitoringService(MarketRepository(session))
            await service.seed_defaults(default_instrument_id="btc-usdt-perp")
            repo = MarketRepository(session)
            policies = await repo.list_monitoring_policies(enabled_only=True)

        # Find ema_20 policies (originally only 1m + the new 4h/1d).
        # Each timeframe is expanded across all 3 instruments. So
        # we expect (original_timeframe_count + 2 new) * 3 policies.
        ema_policies = [p for p in policies if p.indicator_key == "ema_20"]

        # ema_20 has timeframes 1m, 4h, 1d (3). 3 instruments = 9 rows.
        # The original YAML had only 1m; we added 4h + 1d.
        assert len(ema_policies) == 9, (
            f"expected 9 ema_20 policies (3 timeframes × 3 instruments), "
            f"got {len(ema_policies)}"
        )

        # Verify ema_20 includes BOTH 4h and 1d (the new timeframes)
        ema_20_timeframes = {p.timeframe for p in ema_policies}
        assert "4h" in ema_20_timeframes, "ema_20 must have 4h entry"
        assert "1d" in ema_20_timeframes, "ema_20 must have 1d entry"

        # Each instrument must have all ema_20 timeframes
        per_instrument = {}
        for p in ema_policies:
            per_instrument.setdefault(p.instrument_id, set()).add(p.timeframe)
        for iid in instruments:
            assert iid in per_instrument, (
                f"no ema_20 policy for instrument {iid}"
            )
        # Each instrument should have 1m, 4h, 1d — the union of
        # original and new timeframes for ema_20.
        expected_timeframes = {"1m", "4h", "1d"}
        for iid in instruments:
            assert per_instrument[iid] == expected_timeframes, (
                f"ema_20 timeframes for {iid}: {per_instrument[iid]} "
                f"(expected {expected_timeframes})"
            )

        # btc-only assignment would mean per_instrument only has
        # 'btc-usdt-perp' key. Verify eth/sol also have entries.
        for iid in instruments:
            assert any(
                p.instrument_id == iid
                for p in ema_policies
            ), f"missing ema_20 for {iid}"
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_seed_defaults_creates_global_policies_without_instrument_scope(
    monkeypatch, tmp_path
) -> None:
    """Non-instrument-scoped policies (macro/onchain) must remain
    global (no per-instrument fan-out)."""
    from app.monitoring import loader as _loader
    _loader.load_refresh_policies.cache_clear()

    instruments = ["btc-usdt-perp", "eth-usdt-perp"]
    await _setup_db_with_instruments(monkeypatch, tmp_path, instruments)
    try:
        async with db_manager.session() as session:
            service = IndicatorMonitoringService(MarketRepository(session))
            await service.seed_defaults()
            repo = MarketRepository(session)
            policies = await repo.list_monitoring_policies(enabled_only=True)

        # Macro policies (e.g. us_dff) must have instrument_id=None
        macro_policies = [
            p for p in policies
            if p.indicator_key == "us_dff" or p.indicator_key == "vix"
        ]
        assert macro_policies, "expected macro policies to be seeded"
        for p in macro_policies:
            assert p.instrument_id is None, (
                f"macro policy {p.indicator_key} should be global, "
                f"got instrument_id={p.instrument_id!r}"
            )
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_seed_defaults_idempotent_when_no_instruments(
    monkeypatch, tmp_path
) -> None:
    """When the DB has zero instruments (cold-start before bootstrap),
    seed_defaults should still create at least one row per candle
    policy — using the default_instrument_id fallback."""
    from app.monitoring import loader as _loader
    _loader.load_refresh_policies.cache_clear()

    db_path = tmp_path / "seed_empty.db"
    from app.core import config as cfg
    monkeypatch.setattr(
        cfg.settings,
        "database_url",
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
    )
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        async with db_manager.session() as session:
            service = IndicatorMonitoringService(MarketRepository(session))
            await service.seed_defaults(
                default_instrument_id="btc-usdt-perp"
            )
            repo = MarketRepository(session)
            policies = await repo.list_monitoring_policies(enabled_only=True)

        # Even with no instruments, ema_20 should be created once
        # (using default fallback).
        ema_policies = [p for p in policies if p.indicator_key == "ema_20"]
        assert ema_policies, "ema_20 policy should exist even with 0 instruments"
        # Every ema_20 policy uses btc-usdt-perp as the fallback.
        assert all(p.instrument_id == "btc-usdt-perp" for p in ema_policies)
    finally:
        await db_manager.disconnect()
