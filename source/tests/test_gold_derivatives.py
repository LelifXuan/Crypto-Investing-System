"""Tests for gold derivatives data service."""
import json
import tempfile
from pathlib import Path

import pytest


class TestAggregatedOICache:
    def test_read_empty_cache_returns_none(self):
        from app.services.gold_derivatives import AggregatedOICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = AggregatedOICache(cache_dir=Path(tmp))
            result = cache.read_all()
            assert result == []

    def test_write_and_read_snapshot(self):
        from app.services.gold_derivatives import AggregatedOICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = AggregatedOICache(cache_dir=Path(tmp))
            snap = OISnapshot(
                timestamp="2026-07-22T10:00:00",
                oi_contracts_total=__import__("decimal").Decimal("1500000"),
            )
            cache.write(snap)
            result = cache.read_all()
            assert len(result) == 1
            assert result[-1].oi_contracts_total == __import__("decimal").Decimal("1500000")

    def test_oi_change_4w_with_sufficient_data(self):
        from decimal import Decimal
        from app.services.gold_derivatives import AggregatedOICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = AggregatedOICache(cache_dir=Path(tmp))
            cache.write(OISnapshot(timestamp="2026-06-24T10:00:00", oi_contracts_total=Decimal("1000000")))
            cache.write(OISnapshot(timestamp="2026-07-01T10:00:00", oi_contracts_total=Decimal("1100000")))
            cache.write(OISnapshot(timestamp="2026-07-08T10:00:00", oi_contracts_total=Decimal("1200000")))
            cache.write(OISnapshot(timestamp="2026-07-15T10:00:00", oi_contracts_total=Decimal("1300000")))
            cache.write(OISnapshot(timestamp="2026-07-22T10:00:00", oi_contracts_total=Decimal("1500000")))
            change = cache.oi_change_4w(Decimal("1500000"))
            assert change == pytest.approx(0.5, abs=0.01)

    def test_prune_keeps_only_recent(self):
        from decimal import Decimal
        from app.services.gold_derivatives import AggregatedOICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = AggregatedOICache(cache_dir=Path(tmp), max_snapshots=3)
            cache.write(OISnapshot(timestamp="2026-06-01T10:00:00", oi_contracts_total=Decimal("900000")))
            cache.write(OISnapshot(timestamp="2026-07-01T10:00:00", oi_contracts_total=Decimal("1000000")))
            cache.write(OISnapshot(timestamp="2026-07-08T10:00:00", oi_contracts_total=Decimal("1100000")))
            cache.write(OISnapshot(timestamp="2026-07-15T10:00:00", oi_contracts_total=Decimal("1200000")))
            cache.write(OISnapshot(timestamp="2026-07-22T10:00:00", oi_contracts_total=Decimal("1500000")))
            result = cache.read_all()
            assert result[-1].oi_contracts_total == Decimal("1500000")
            assert len(result) <= 3


class TestGoldDerivativesService:
    @pytest.mark.asyncio
    async def test_build_snapshot_returns_expected_keys(self):
        """Snapshot should return known keys even when all perp venues are unreachable."""
        from app.services.gold_derivatives import GoldDerivativesService
        svc = GoldDerivativesService()
        result = await svc.build_snapshot()
        assert "oi_change_4w" in result
        assert "funding_rate" in result
        assert "cot_net_spec_percentile" in result
        assert "open_interest" in result
        assert "derivatives_note" in result
