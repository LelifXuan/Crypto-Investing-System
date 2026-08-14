from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.market import ComputedDatasetCache
from app.services.monitoring_decision_review import (
    DECISION_BRIEF_DATASET_TYPE,
    count_decision_briefs_for_instrument,
    list_recent_decision_briefs,
)


async def _make_session() -> tuple[AsyncSession, async_sessionmaker, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_factory(), session_factory, engine


def _make_cache(
    *,
    instrument_id: str,
    timeframe: str,
    snapshot_id: str,
    calculated_at: datetime,
    consistency: str = "aligned",
    payload: dict[str, Any] | None = None,
) -> ComputedDatasetCache:
    decision_brief = payload or {
        "version": "monitoring_decision_brief_v1",
        "source_alignment": {"consistency": consistency},
        "rows": [
            {"key": "market_situation", "title": "市场情况"},
            {"key": "key_risk", "title": "关键失效"},
        ],
    }
    return ComputedDatasetCache(
        cache_key=(
            "monitoring_decision_brief:"
            f"{instrument_id}:{timeframe}:{snapshot_id}:decision_brief_v1"
        ),
        dataset_type=DECISION_BRIEF_DATASET_TYPE,
        instrument_id=instrument_id,
        timeframe=timeframe,
        source_data_ts=calculated_at,
        payload_json=decision_brief,
        cache_state="fresh",
        source_version="decision_brief_v1",
        calculated_at=calculated_at,
        expires_at=calculated_at,
        cost_ms=0,
        meta_json={"consistency": consistency},
    )


@pytest.mark.asyncio
async def test_review_returns_recent_briefs_in_descending_order() -> None:
    session, _, engine = await _make_session()
    try:
        session.add(
            _make_cache(
                instrument_id="btc-usdt-perp",
                timeframe="1d",
                snapshot_id="20260601T000000000000Z",
                calculated_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
                consistency="aligned",
            )
        )
        session.add(
            _make_cache(
                instrument_id="btc-usdt-perp",
                timeframe="1d",
                snapshot_id="20260602T120000000000Z",
                calculated_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
                consistency="conflict",
            )
        )
        session.add(
            _make_cache(
                instrument_id="btc-usdt-perp",
                timeframe="1d",
                snapshot_id="20260602T060000000000Z",
                calculated_at=datetime(2026, 6, 2, 6, 0, tzinfo=UTC),
                consistency="degraded",
            )
        )
        await session.commit()

        briefs = await list_recent_decision_briefs(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            limit=10,
        )
        assert len(briefs) == 3
        # Newest first.
        assert briefs[0]["calculated_at"] > briefs[1]["calculated_at"]
        assert briefs[1]["calculated_at"] > briefs[2]["calculated_at"]
        assert briefs[0]["consistency"] == "conflict"
        assert briefs[1]["consistency"] == "degraded"
        assert briefs[2]["consistency"] == "aligned"
        for entry in briefs:
            assert entry["decision_brief"]["version"] == "monitoring_decision_brief_v1"
            assert len(entry["decision_brief"]["rows"]) == 2
            row_keys = {row["key"] for row in entry["decision_brief"]["rows"]}
            assert row_keys == {"market_situation", "key_risk"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_review_handles_missing_cache() -> None:
    session, _, engine = await _make_session()
    try:
        briefs = await list_recent_decision_briefs(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
        )
        assert briefs == []
        count = await count_decision_briefs_for_instrument(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
        )
        assert count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_review_respects_limit_and_filters_by_instrument() -> None:
    session, _, engine = await _make_session()
    try:
        for idx in range(5):
            session.add(
                _make_cache(
                    instrument_id="btc-usdt-perp",
                    timeframe="1d",
                    snapshot_id=f"snap-btc-{idx:02d}",
                    calculated_at=datetime(2026, 6, 1, idx, tzinfo=UTC),
                )
            )
        for idx in range(3):
            session.add(
                _make_cache(
                    instrument_id="eth-usdt-perp",
                    timeframe="1d",
                    snapshot_id=f"snap-eth-{idx:02d}",
                    calculated_at=datetime(2026, 6, 1, idx, tzinfo=UTC),
                )
            )
        await session.commit()

        btc_briefs = await list_recent_decision_briefs(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            limit=2,
        )
        assert len(btc_briefs) == 2
        assert btc_briefs[0]["calculated_at"] > btc_briefs[1]["calculated_at"]
        btc_count = await count_decision_briefs_for_instrument(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
        )
        assert btc_count == 5
        eth_count = await count_decision_briefs_for_instrument(
            session,
            instrument_id="eth-usdt-perp",
            timeframe="1d",
        )
        assert eth_count == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_review_serializes_decision_brief_to_json() -> None:
    session, _, engine = await _make_session()
    try:
        snapshot = _make_cache(
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            snapshot_id="20260601T000000000000Z",
            calculated_at=datetime(2026, 6, 1, tzinfo=UTC),
            consistency="degraded",
            payload={
                "version": "monitoring_decision_brief_v1",
                "source_alignment": {
                    "consistency": "degraded",
                    "primary_sources": ["analysis_bundle"],
                    "missing_sources": ["alerts_bundle", "strategy_bundle"],
                },
                "rows": [
                    {"key": "market_situation", "tone": "warning", "summary": "降级"},
                    {"key": "key_risk", "tone": "warning", "summary": "数据缺口"},
                ],
            },
        )
        session.add(snapshot)
        await session.commit()

        briefs = await list_recent_decision_briefs(
            session,
            instrument_id="btc-usdt-perp",
            timeframe="1d",
        )
        assert len(briefs) == 1
        entry = briefs[0]
        assert entry["consistency"] == "degraded"
        assert entry["decision_brief"]["source_alignment"]["missing_sources"] == [
            "alerts_bundle",
            "strategy_bundle",
        ]
        assert entry["instrument_id"] == "btc-usdt-perp"
        assert entry["timeframe"] == "1d"
        assert entry["source_version"] == "decision_brief_v1"
    finally:
        await engine.dispose()
