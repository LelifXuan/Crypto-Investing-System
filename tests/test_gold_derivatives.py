"""Tests for gold derivatives data service."""
import json
import tempfile
from pathlib import Path

import pytest


class TestOICache:
    def test_read_empty_cache_returns_none(self):
        from app.services.gold_derivatives import OICache
        with tempfile.TemporaryDirectory() as tmp:
            cache = OICache(cache_dir=Path(tmp))
            result = cache.read_latest()
            assert result is None

    def test_write_and_read_snapshot(self):
        from app.services.gold_derivatives import OICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = OICache(cache_dir=Path(tmp))
            snap = OISnapshot(timestamp="2026-07-22T10:00:00", oi_value=1_500_000.0)
            cache.write(snap)
            result = cache.read_latest()
            assert result is not None
            assert result.oi_value == 1_500_000.0

    def test_oi_change_4w_with_sufficient_data(self):
        from app.services.gold_derivatives import OICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = OICache(cache_dir=Path(tmp))
            cache.write(OISnapshot(timestamp="2026-06-24T10:00:00", oi_value=1_000_000.0))
            cache.write(OISnapshot(timestamp="2026-07-01T10:00:00", oi_value=1_100_000.0))
            cache.write(OISnapshot(timestamp="2026-07-08T10:00:00", oi_value=1_200_000.0))
            cache.write(OISnapshot(timestamp="2026-07-15T10:00:00", oi_value=1_300_000.0))
            cache.write(OISnapshot(timestamp="2026-07-22T10:00:00", oi_value=1_500_000.0))
            change = cache.oi_change_4w()
            assert change == pytest.approx(0.5, abs=0.01)

    def test_prune_keeps_only_recent(self):
        from app.services.gold_derivatives import OICache, OISnapshot
        with tempfile.TemporaryDirectory() as tmp:
            cache = OICache(cache_dir=Path(tmp), max_snapshots=3)
            cache.write(OISnapshot(timestamp="2026-06-01T10:00:00", oi_value=900_000.0))
            cache.write(OISnapshot(timestamp="2026-07-01T10:00:00", oi_value=1_000_000.0))
            cache.write(OISnapshot(timestamp="2026-07-08T10:00:00", oi_value=1_100_000.0))
            cache.write(OISnapshot(timestamp="2026-07-15T10:00:00", oi_value=1_200_000.0))
            cache.write(OISnapshot(timestamp="2026-07-22T10:00:00", oi_value=1_500_000.0))
            result = cache.read_latest()
            assert result.oi_value == 1_500_000.0
            snapshots = cache._read_all()
            assert len(snapshots) <= 3


class TestGoldDerivativesService:
    @pytest.mark.asyncio
    async def test_build_snapshot_returns_expected_keys(self):
        """Snapshot should return known keys even when Gate.io is unreachable."""
        from app.services.gold_derivatives import GoldDerivativesService
        svc = GoldDerivativesService()
        result = await svc.build_snapshot()
        assert "oi_change_4w" in result
        assert "funding_rate" in result
        assert "cot_net_spec_percentile" in result
        assert "derivatives_note" in result
