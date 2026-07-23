"""Read-only review helpers for persisted monitoring decision_brief snapshots.

Snapshots are written by :class:`MonitoringDashboardService` into the
``ComputedDatasetCache`` table with ``dataset_type=monitoring_decision_brief``.
This module provides the read path that backs the
``/monitoring/decision-brief/history`` endpoint and the future
"当时判断 vs 后续价格"复盘 surface.

The module is intentionally side-effect free: no I/O outside the database,
no network, no cache writes. Callers must hold an open
:class:`AsyncSession` via FastAPI dependency injection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframes import (
    normalize_instrument_id,
    normalize_timeframe_for_cache,
)
from app.db.models.market import ComputedDatasetCache

DECISION_BRIEF_DATASET_TYPE = "monitoring_decision_brief"


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=None).isoformat()
    return value.isoformat()


def _serialise_cache(cache: ComputedDatasetCache) -> dict[str, Any]:
    payload = cache.payload_json if isinstance(cache.payload_json, dict) else {}
    meta = cache.meta_json if isinstance(cache.meta_json, dict) else {}
    return {
        "cache_key": cache.cache_key,
        "dataset_type": cache.dataset_type,
        "instrument_id": cache.instrument_id,
        "timeframe": cache.timeframe,
        "calculated_at": _to_iso(cache.calculated_at),
        "expires_at": _to_iso(cache.expires_at),
        "source_data_ts": _to_iso(cache.source_data_ts),
        "source_version": cache.source_version,
        "consistency": meta.get("consistency"),
        "decision_brief": payload,
    }


async def list_recent_decision_briefs(
    session: AsyncSession,
    *,
    instrument_id: str,
    timeframe: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most recent persisted decision_brief snapshots for review.

    Results are sorted by ``calculated_at`` descending. The function tolerates
    a missing or empty cache by returning an empty list - callers can then
    render an explanatory empty state instead of fabricating a decision.
    """

    normalized_instrument = normalize_instrument_id(instrument_id)
    normalized_timeframe = normalize_timeframe_for_cache(timeframe)
    statement = (
        select(ComputedDatasetCache)
        .where(
            ComputedDatasetCache.dataset_type == DECISION_BRIEF_DATASET_TYPE,
            ComputedDatasetCache.instrument_id == normalized_instrument,
            ComputedDatasetCache.timeframe == normalized_timeframe,
        )
        .order_by(desc(ComputedDatasetCache.calculated_at))
        .limit(max(1, min(int(limit or 1), 100)))
    )
    rows = (await session.execute(statement)).scalars().all()
    return [_serialise_cache(row) for row in rows]


async def count_decision_briefs_for_instrument(
    session: AsyncSession,
    *,
    instrument_id: str,
    timeframe: str,
) -> int:
    normalized_instrument = normalize_instrument_id(instrument_id)
    normalized_timeframe = normalize_timeframe_for_cache(timeframe)
    statement = (
        select(ComputedDatasetCache.dataset_cache_id)
        .where(
            ComputedDatasetCache.dataset_type == DECISION_BRIEF_DATASET_TYPE,
            ComputedDatasetCache.instrument_id == normalized_instrument,
            ComputedDatasetCache.timeframe == normalized_timeframe,
        )
    )
    result = await session.execute(statement)
    return len(list(result.scalars().all()))
