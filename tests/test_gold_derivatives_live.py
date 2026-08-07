"""Tests for the gold-derivatives multi-source aggregator.

Covers:

* Decimal-safe coercion helpers (``_to_decimal``).
* Weighted funding aggregation (USD notional).
* OI summation across PAXG + XAUT perps.
* Aggregated OI cache round-trip + 4-week comparison.
* ``GoldDerivativesService.build_snapshot`` returns the four-field contract
  even when all venues are unreachable.
* Static guard: ``gateio.ws`` must not reappear in gold_derivatives.py.
"""
from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.gold_derivatives import (
    AggregatedOICache,
    GoldDerivativesService,
    GoldPerpRow,
    OISnapshot,
    _sum_oi,
    _to_decimal,
    _weighted_funding,
)

# ─── _to_decimal coercion ──────────────────────────────────────────────


def test_to_decimal_accepts_decimal_strings() -> None:
    assert _to_decimal("0.0001") == Decimal("0.0001")
    assert _to_decimal("1500000") == Decimal("1500000")


def test_to_decimal_returns_none_for_invalid_inputs() -> None:
    assert _to_decimal(None) is None
    assert _to_decimal("") is None
    assert _to_decimal("not-a-number") is None
    assert _to_decimal({}) is None


def test_to_decimal_preserves_decimal_passthrough() -> None:
    d = Decimal("0.000123456789")
    assert _to_decimal(d) == d


# ─── Weighted funding aggregation ───────────────────────────────────────


def test_weighted_funding_uniform_oi_returns_simple_mean() -> None:
    rows = [
        GoldPerpRow(
            provider="bybit",
            symbol="PAXGUSDT",
            funding_rate=Decimal("0.0001"),
            oi_usd=Decimal("1000000"),
            oi_contracts=Decimal("3000"),
        ),
        GoldPerpRow(
            provider="binance",
            symbol="PAXGUSDT",
            funding_rate=Decimal("0.0002"),
            oi_usd=Decimal("1000000"),
            oi_contracts=Decimal("3000"),
        ),
    ]
    fr = _weighted_funding(rows)
    assert fr is not None
    # Equal weights: simple mean
    assert fr == Decimal("0.00015")


def test_weighted_funding_skips_rows_without_oi_usd() -> None:
    rows = [
        GoldPerpRow(
            provider="bybit",
            symbol="PAXGUSDT",
            funding_rate=Decimal("0.0001"),
            oi_usd=None,
            oi_contracts=Decimal("3000"),
        ),
        GoldPerpRow(
            provider="binance",
            symbol="PAXGUSDT",
            funding_rate=Decimal("0.0002"),
            oi_usd=Decimal("1000000"),
            oi_contracts=Decimal("3000"),
        ),
    ]
    fr = _weighted_funding(rows)
    assert fr is not None
    # bybit row skipped (no oi_usd); only binance contributes
    assert fr == Decimal("0.0002")


def test_weighted_funding_all_invalid_returns_none() -> None:
    rows = [GoldPerpRow(provider="bybit", symbol="PAXGUSDT")]
    assert _weighted_funding(rows) is None


def test_sum_oi_adds_contracts_across_rows() -> None:
    rows = [
        GoldPerpRow(provider="bybit", symbol="PAXGUSDT", oi_contracts=Decimal("10000")),
        GoldPerpRow(provider="okx", symbol="PAXG-USDT-SWAP", oi_contracts=Decimal("8000")),
        GoldPerpRow(provider="binance", symbol="PAXGUSDT", oi_contracts=Decimal("12000")),
        GoldPerpRow(provider="bybit", symbol="XAUTUSDT"),  # no oi → skipped
    ]
    total = _sum_oi(rows)
    assert total == Decimal("30000")


# ─── Aggregated OI cache round-trip ──────────────────────────────────────


def test_aggregated_oi_cache_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = AggregatedOICache(cache_dir=Path(tmp))
        snap = OISnapshot(
            timestamp="2026-07-22T10:00:00",
            oi_contracts_total=Decimal("45000"),
        )
        cache.write(snap)
        all_snaps = cache.read_all()
        assert len(all_snaps) == 1
        assert all_snaps[0].oi_contracts_total == Decimal("45000")


def test_aggregated_oi_cache_oi_change_4w() -> None:
    """Compute oi_change against the snapshot nearest to 4 weeks ago."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = AggregatedOICache(cache_dir=Path(tmp))
        # Older baseline
        cache.write(
            OISnapshot(
                timestamp="2026-06-24T10:00:00",
                oi_contracts_total=Decimal("30000"),
            )
        )
        # Most recent (today)
        cache.write(
            OISnapshot(
                timestamp="2026-07-22T10:00:00",
                oi_contracts_total=Decimal("45000"),
            )
        )
        # ~50% growth over 28 days
        change = cache.oi_change_4w(Decimal("45000"))
        assert change is not None
        assert change == Decimal("0.5")


# ─── End-to-end snapshot shape ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_snapshot_returns_four_field_contract_even_when_offline() -> None:
    """Even with all perp endpoints unreachable, the snapshot must still
    include the four fields the workbench UI consumes. The values may be
    ``None`` (UI shows "数据积累中"); the *shape* must be stable."""
    svc = GoldDerivativesService(request_timeout=1.0)
    result = await svc.build_snapshot()
    assert "oi_change_4w" in result
    assert "funding_rate" in result
    assert "cot_net_spec_percentile" in result
    assert "open_interest" in result
    assert "derivatives_note" in result
    # Internal per-venue diagnostic only — not surfaced to the UI.
    assert "_venues" in result
    assert isinstance(result["_venues"], list)


@pytest.mark.asyncio
async def test_refresh_all_returns_same_shape_as_build_snapshot() -> None:
    svc = GoldDerivativesService(request_timeout=1.0)
    snap = await svc.build_snapshot()
    refreshed = await svc.refresh_all(force=True)
    # Both share the contract shape; values may differ because ``force``
    # re-fetches, but the keys are identical.
    assert set(snap.keys()) == set(refreshed.keys())


# ─── Static guard against the old Gate.io dependency ─────────────────────


def test_no_gateio_ws_in_gold_derivatives_source() -> None:
    """2026-08-07: the live aggregator replaces the legacy Gate.io endpoint.
    This guard ensures no future refactor accidentally re-imports or
    re-references ``api.gateio.ws`` in the gold-derivatives module.
    """
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "gold_derivatives.py"
    text = src.read_text(encoding="utf-8")
    assert "gateio.ws" not in text, (
        "gold_derivatives.py must not reference api.gateio.ws; "
        "the new aggregator uses Bybit + OKX + Binance."
    )
    # Both PAXG and XAUT must be present — the user explicitly wants
    # the cross-token breadth so a single token pausing does not
    # collapse the indicator.
    assert "PAXG" in text
    assert "XAUT" in text


def test_both_paxg_and_xaut_present_in_venue_table() -> None:
    """Regression guard: the venue tuple must list PAXG + XAUT across
    every venue (Bybit + OKX + Binance). Removing either token from
    either venue breaks the cross-token breadth the user requested."""
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "gold_derivatives.py"
    text = src.read_text(encoding="utf-8")
    assert "PAXGUSDT" in text
    assert "XAUTUSDT" in text
    assert "PAXG-USDT-SWAP" in text
    assert "XAUT-USDT-SWAP" in text