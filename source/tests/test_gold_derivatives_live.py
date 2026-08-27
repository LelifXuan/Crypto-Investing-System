"""Tests for the gold-derivatives multi-source aggregator.

Covers:

* Decimal-safe coercion helpers (``_to_decimal``).
* Weighted funding aggregation (USD notional).
* OI summation across PAXG + XAUT perps.
* Aggregated OI cache round-trip + 4-week comparison.
* ``GoldDerivativesService.build_snapshot`` returns the four-field contract
  even when all venues are unreachable.
* Gate.io contract quantities and Bitget ticker payloads are normalized.
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
    _fetch_bitget,
    _fetch_gateio,
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


@pytest.mark.asyncio
async def test_refresh_failure_preserves_last_known_good(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.gold_derivatives as module

    stale = {
        "oi_change_4w": "0.1",
        "funding_rate": "0.0002",
        "cot_net_spec_percentile": "0.5",
        "open_interest": "42",
        "derivatives_note": "数据可用",
        "_venues": [],
    }
    failed = {**stale, "open_interest": None, "funding_rate": None}
    svc = GoldDerivativesService()

    async def fail_refresh(_self: GoldDerivativesService) -> dict:
        return failed

    writes: list[dict] = []
    monkeypatch.setattr(GoldDerivativesService, "_build_snapshot_uncached", fail_refresh)
    monkeypatch.setattr(module, "_read_snapshot_disk_allow_stale", lambda: stale.copy())
    monkeypatch.setattr(module, "_write_snapshot_disk", writes.append)

    result = await svc.refresh_all(force=True)
    assert result["open_interest"] == "42"
    assert "保留磁盘缓存" in result["derivatives_note"]
    assert writes == []


@pytest.mark.asyncio
async def test_single_provider_cannot_publish_funding_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = GoldDerivativesService()

    async def one_provider(_self: GoldDerivativesService) -> list[GoldPerpRow]:
        return [
            GoldPerpRow(
                provider="gateio",
                symbol="XAUT_USDT",
                funding_rate=Decimal("0.001"),
                oi_contracts=Decimal("2"),
                oi_usd=Decimal("5000"),
            )
        ]

    monkeypatch.setattr(GoldDerivativesService, "fetch_all_perps", one_provider)
    monkeypatch.setattr(svc.oi_cache, "write", lambda _snapshot: None)
    result = await svc._build_snapshot_uncached()
    assert result["funding_rate"] is None
    assert "可用信源不足 2 个" in result["derivatives_note"]


# ─── Live-provider normalization ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_gateio_contract_oi_is_normalized_to_token_quantity() -> None:
    class Client:
        async def get(self, _path: str):
            class Response:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict:
                    return {
                        "mark_price": "2500",
                        "funding_rate": "0.0001",
                        "position_size": "12000",
                        "quanto_multiplier": "0.001",
                        "funding_next_apply": 1_800_000_000,
                    }

            return Response()

    row = await _fetch_gateio(Client(), "XAUT_USDT")  # type: ignore[arg-type]
    assert row.oi_contracts == Decimal("12")
    assert row.oi_usd == Decimal("30000")


@pytest.mark.asyncio
async def test_bitget_ticker_fields_are_decimal_safe() -> None:
    class Client:
        async def get(self, _path: str, *, params: dict):
            assert params["productType"] == "USDT-FUTURES"

            class Response:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict:
                    return {
                        "code": "00000",
                        "requestTime": 1_800_000_000_000,
                        "data": [
                            {
                                "markPrice": "2500.25",
                                "fundingRate": "-0.00003",
                                "holdingAmount": "42.125",
                            }
                        ],
                    }

            return Response()

    row = await _fetch_bitget(Client(), "PAXGUSDT")  # type: ignore[arg-type]
    assert row.funding_rate == Decimal("-0.00003")
    assert row.oi_contracts == Decimal("42.125")
    assert row.oi_usd == Decimal("105323.03125")


def test_both_paxg_and_xaut_present_in_venue_table() -> None:
    """Regression guard: the venue tuple must list PAXG + XAUT across
    every venue. Removing either token from
    either venue breaks the cross-token breadth the user requested."""
    src = Path(__file__).resolve().parents[1] / "app" / "services" / "gold_derivatives.py"
    text = src.read_text(encoding="utf-8")
    assert "PAXGUSDT" in text
    assert "XAUTUSDT" in text
    assert "PAXG_USDT" in text
    assert "XAUT_USDT" in text
    assert '("gateio", "PAXG_USDT")' in text
    assert '("bitget", "XAUTUSDT")' in text
    assert "PAXG-USDT-SWAP" not in text
    assert "XAUT-USDT-SWAP" not in text
