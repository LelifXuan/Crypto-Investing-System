from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.computed_dataset_cache import ComputedDatasetCacheService


def test_secondary_indicator_series_uses_canonical_adx_keys() -> None:
    service = ComputedDatasetCacheService(repository=None)  # type: ignore[arg-type]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for index in range(80):
        close = Decimal("100") + Decimal(index) / Decimal("10")
        candles.append(
            {
                "ts_open": (start + timedelta(hours=index)).isoformat(),
                "open": close - Decimal("0.5"),
                "high": close + Decimal("1.2"),
                "low": close - Decimal("1.1"),
                "close": close,
                "volume": Decimal("1000") + Decimal(index),
            }
        )

    payload = service._build_indicator_series(candles, "secondary")

    expected = {
        "adx_14",
        "plus_di",
        "minus_di",
        "obv",
        "obv_change_5",
        "obv_slope",
        "vwap_50",
        "vwap_100",
        "vwap_spread_pct",
        "vwap_slope_10",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "cci_20",
    }
    assert expected <= set(payload)
    assert len(payload["plus_di"]) == len(candles)
    assert len(payload["minus_di"]) == len(candles)
    assert len(payload["obv_slope"]) == len(candles)
    assert len(payload["vwap_50"]) == len(candles)
    assert len(payload["vwap_100"]) == len(candles)
    assert any(item is not None for item in payload["obv_slope"][6:])
    assert any(item is not None for item in payload["vwap_50"][50:])
