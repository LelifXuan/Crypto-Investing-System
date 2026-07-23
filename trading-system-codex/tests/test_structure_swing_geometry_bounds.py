from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.structure.common import Pivot, ScoringConfig
from app.services.structure.swing import SwingScorer

UTC = timezone.utc


class FakeCandle:
    def __init__(self, idx: int, close: float) -> None:
        self.ts_open = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=idx * 4)
        self.open = close
        self.high = close + 80
        self.low = close - 80
        self.close = close
        self.volume = 1000


def test_swing_zigzag_points_are_bound_to_real_candles() -> None:
    candles = [FakeCandle(idx, 60000 + idx * 20) for idx in range(18)]
    pivots = [
        Pivot(ts=candles[2].ts_open, price=candles[2].low, kind="low", index=2),
        Pivot(ts=candles[5].ts_open, price=candles[5].high, kind="high", index=5),
        Pivot(ts=candles[9].ts_open, price=candles[9].low, kind="low", index=9),
        Pivot(ts=candles[14].ts_open, price=candles[14].high, kind="high", index=14),
    ]

    bundle = SwingScorer(ScoringConfig()).detect("btc-usdt-perp", "4h", candles, pivots=pivots)
    zigzag = next(item for item in bundle.geometry if item.kind == "zigzag")

    for point in zigzag.points_json:
        candle = candles[point["index"]]
        assert point["candle_high"] == candle.high
        assert point["candle_low"] == candle.low
        assert candle.low <= point["price"] <= candle.high
        assert point["confirmed"] is True
    assert zigzag.meta_json["geometry_validation"] == "valid"
    assert zigzag.meta_json["invalid_point_count"] == 0


def test_swing_zigzag_rejects_price_and_timestamp_mismatches() -> None:
    candles = [FakeCandle(idx, 60000 + idx * 20) for idx in range(18)]
    pivots = [
        Pivot(ts=candles[2].ts_open, price=candles[2].low, kind="low", index=2),
        Pivot(ts=candles[5].ts_open, price=candles[5].high + 500, kind="high", index=5),
        Pivot(ts=candles[8].ts_open, price=candles[9].low, kind="low", index=9),
        Pivot(ts=candles[14].ts_open, price=candles[14].high, kind="high", index=14),
    ]

    bundle = SwingScorer(ScoringConfig()).detect("btc-usdt-perp", "4h", candles, pivots=pivots)
    zigzag = next(item for item in bundle.geometry if item.kind == "zigzag")

    assert [point["index"] for point in zigzag.points_json] == [2, 14]
    assert zigzag.meta_json["geometry_validation"] == "partial"
    assert zigzag.meta_json["invalid_point_count"] == 2
    assert {item["reason"] for item in zigzag.meta_json["validation_errors"]} == {
        "price_candle_mismatch",
        "timestamp_index_mismatch",
    }


def test_swing_zigzag_rejects_out_of_range_index() -> None:
    candles = [FakeCandle(idx, 60000 + idx * 20) for idx in range(18)]
    pivots = [
        Pivot(ts=candles[2].ts_open, price=candles[2].low, kind="low", index=2),
        Pivot(ts=candles[5].ts_open, price=candles[5].high, kind="high", index=5),
        Pivot(ts=candles[-1].ts_open, price=candles[-1].low, kind="low", index=99),
    ]

    bundle = SwingScorer(ScoringConfig()).detect("btc-usdt-perp", "4h", candles, pivots=pivots)
    zigzag = next(item for item in bundle.geometry if item.kind == "zigzag")

    assert zigzag.meta_json["invalid_point_count"] == 1
    assert zigzag.meta_json["validation_errors"][0]["reason"] == "index_out_of_range"
