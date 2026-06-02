"""Acceptance tests for T05: load lower_tf_snapshot from repository.

The audit found that ``lower_tf_missing`` was inferred from the aggregate
``data_quality_score < 60`` heuristic, which conflated the higher timeframe
bundle health with the lower timeframe's own availability. The snapshot
builder now reads the lower timeframe's ``strategy_bundle`` page snapshot
cache directly and computes a real alignment verdict.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.cache_registry import strategy_bundle_cache_key
from app.services.strategy_signal.snapshot_builder import StrategySnapshotBuilder


def _make_cached(payload: dict, cache_state: str = "fresh"):
    return SimpleNamespace(
        payload_json=payload,
        snapshot_at=datetime(2026, 6, 1, tzinfo=UTC),
        data_ts=datetime(2026, 6, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        expires_at=datetime(2026, 6, 2, tzinfo=UTC),
        source_version="v3",
        cost_ms=10,
        cache_state=cache_state,
        status="ready",
    )


def test_load_lower_tf_snapshot_returns_none_when_cache_miss() -> None:
    repo = SimpleNamespace()

    class _Repo:
        async def get_page_snapshot_cache(self, cache_key: str):
            return None

    repo = _Repo()
    builder = StrategySnapshotBuilder(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        builder._load_lower_tf_snapshot(  # noqa: SLF001
            instrument="btc-usdt-perp", lower_tf="4h"
        )
    )
    assert out is None


def test_load_lower_tf_snapshot_returns_payload_when_cache_hit() -> None:
    cached = _make_cached(
        {
            "decision": {
                "strategy_state": "LONG_BIAS",
                "strategy_state_label": "偏多观察",
                "strategy_bias": "long",
                "long_score": 70.0,
                "short_score": 40.0,
                "mtf_trend_bullish": 65.0,
                "mtf_trend_bearish": 35.0,
                "direction_confidence": 0.6,
                "next_trigger": "等待 1H 突破",
            }
        }
    )

    class _Repo:
        def __init__(self):
            self.last_key: str | None = None

        async def get_page_snapshot_cache(self, cache_key: str):
            self.last_key = cache_key
            return cached

    repo = _Repo()
    builder = StrategySnapshotBuilder(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        builder._load_lower_tf_snapshot(  # noqa: SLF001
            instrument="btc-usdt-perp", lower_tf="4h"
        )
    )

    assert out is not None
    assert out["strategy_state"] == "LONG_BIAS"
    assert out["strategy_bias"] == "long"
    assert out["long_score"] == 70.0
    assert out["short_score"] == 40.0
    assert out["cache_state"] == "fresh"
    assert repo.last_key == strategy_bundle_cache_key("btc-usdt-perp", "4h")


def test_load_lower_tf_snapshot_handles_non_dict_payload() -> None:
    cached = _make_cached(["not", "a", "dict"])
    repo = SimpleNamespace(
        get_page_snapshot_cache=lambda cache_key: _async_return(cached)
    )
    builder = StrategySnapshotBuilder(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        builder._load_lower_tf_snapshot(  # noqa: SLF001
            instrument="btc-usdt-perp", lower_tf="4h"
        )
    )
    assert out is None


def test_load_lower_tf_snapshot_handles_exception() -> None:
    class _Repo:
        async def get_page_snapshot_cache(self, cache_key: str):
            raise RuntimeError("db down")

    repo = _Repo()
    builder = StrategySnapshotBuilder(repository=repo)  # type: ignore[arg-type]
    out = asyncio.run(
        builder._load_lower_tf_snapshot(  # noqa: SLF001
            instrument="btc-usdt-perp", lower_tf="4h"
        )
    )
    assert out is None


def test_alignment_aligned_bullish() -> None:
    out = StrategySnapshotBuilder._compute_lower_tf_alignment(  # noqa: SLF001
        higher_direction={"bullish": 70, "bearish": 30},
        lower_payload={
            "long_score": 70.0,
            "short_score": 40.0,
            "strategy_state": "LONG_BIAS",
        },
        higher_timeframe="1d",
        lower_timeframe="4h",
    )
    assert out["status"] == "aligned"
    assert out["higher_label"] == "bullish"
    assert out["lower_label"] == "bullish"
    assert out["required_timeframe"] == "4h"


def test_alignment_aligned_bearish() -> None:
    out = StrategySnapshotBuilder._compute_lower_tf_alignment(  # noqa: SLF001
        higher_direction={"bullish": 30, "bearish": 70},
        lower_payload={
            "long_score": 35.0,
            "short_score": 70.0,
            "strategy_state": "SHORT_BIAS",
        },
        higher_timeframe="1d",
        lower_timeframe="4h",
    )
    assert out["status"] == "aligned"
    assert out["higher_label"] == "bearish"
    assert out["lower_label"] == "bearish"


def test_alignment_conflict() -> None:
    out = StrategySnapshotBuilder._compute_lower_tf_alignment(  # noqa: SLF001
        higher_direction={"bullish": 70, "bearish": 30},
        lower_payload={
            "long_score": 30.0,
            "short_score": 70.0,
            "strategy_state": "SHORT_BIAS",
        },
        higher_timeframe="1d",
        lower_timeframe="4h",
    )
    assert out["status"] == "conflict"
    assert out["higher_label"] == "bullish"
    assert out["lower_label"] == "bearish"


def test_alignment_neutral_higher() -> None:
    out = StrategySnapshotBuilder._compute_lower_tf_alignment(  # noqa: SLF001
        higher_direction={"bullish": 50, "bearish": 50},
        lower_payload={"long_score": 70.0, "short_score": 40.0},
        higher_timeframe="1d",
        lower_timeframe="4h",
    )
    assert out["status"] == "neutral"
    assert out["higher_label"] == "neutral"
    assert out["lower_label"] == "bullish"


def test_alignment_neutral_lower() -> None:
    out = StrategySnapshotBuilder._compute_lower_tf_alignment(  # noqa: SLF001
        higher_direction={"bullish": 70, "bearish": 30},
        lower_payload={"long_score": 50.0, "short_score": 50.0},
        higher_timeframe="1d",
        lower_timeframe="4h",
    )
    assert out["status"] == "neutral"


def _async_return(value):
    async def _coro():
        return value

    return _coro()
