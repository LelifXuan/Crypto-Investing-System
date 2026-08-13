"""P5-3B: Proactive prewarm with priority scheduling and TTL jitter."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PrecomputeCandidate:
    instrument_id: str
    page: str
    timeframe: str
    candidates: tuple[str, ...]
    last_access_at: datetime | None
    cache_created_at: datetime | None
    source_changed: bool
    is_core_instrument: bool
    current_page_active: bool
    retry_not_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class PlannedBuild:
    candidate: PrecomputeCandidate
    priority: int
    reason: str


class PrecomputePlanner:
    """Priority planner with source invalidation, hotness and TTL jitter."""

    PRIORITY_CURRENT_PAGE = 0
    PRIORITY_SOURCE_CHANGED = 1
    PRIORITY_RECENTLY_ACCESSED = 2
    PRIORITY_CORE_INSTRUMENT = 3
    PRIORITY_SOFT_TTL_ELAPSED = 4
    PRIORITY_CACHE_MISSING = 5

    def __init__(
        self,
        *,
        soft_ttl_seconds: int,
        hard_ttl_seconds: int,
        hot_window_seconds: int = 1800,
        jitter_ratio: float = 0.10,
    ) -> None:
        if soft_ttl_seconds <= 0:
            raise ValueError("soft_ttl_seconds must be positive")
        if hard_ttl_seconds <= soft_ttl_seconds:
            raise ValueError("hard_ttl_seconds must exceed soft_ttl_seconds")
        if not 0 <= jitter_ratio <= 0.5:
            raise ValueError("jitter_ratio must be between 0 and 0.5")
        self._soft_ttl = soft_ttl_seconds
        self._hard_ttl = hard_ttl_seconds
        self._hot_window = hot_window_seconds
        self._jitter_ratio = jitter_ratio

    def plan(
        self,
        candidates: Sequence[PrecomputeCandidate],
        *,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[PlannedBuild]:
        current = now or datetime.now(timezone.utc)
        planned = [
            item
            for candidate in candidates
            if (item := self._score(candidate, current)) is not None
        ]
        planned.sort(key=lambda item: (item.priority, item.candidate.instrument_id))
        return planned[:limit]

    def _score(
        self,
        candidate: PrecomputeCandidate,
        now: datetime,
    ) -> PlannedBuild | None:
        if candidate.retry_not_before is not None and now < candidate.retry_not_before:
            return None
        if candidate.current_page_active:
            return PlannedBuild(candidate, self.PRIORITY_CURRENT_PAGE, "current_page_active")
        if candidate.source_changed:
            return PlannedBuild(candidate, self.PRIORITY_SOURCE_CHANGED, "source_watermark_changed")
        if candidate.last_access_at is not None:
            age = (now - candidate.last_access_at).total_seconds()
            if age <= self._hot_window:
                return PlannedBuild(candidate, self.PRIORITY_RECENTLY_ACCESSED, "recently_accessed")
        if candidate.is_core_instrument:
            return PlannedBuild(candidate, self.PRIORITY_CORE_INSTRUMENT, "core_instrument")
        if candidate.cache_created_at is None:
            return PlannedBuild(candidate, self.PRIORITY_CACHE_MISSING, "cache_missing")
        jitter = self._soft_ttl * self._jitter_ratio
        threshold = self._soft_ttl + random.uniform(-jitter, jitter)
        cache_age = (now - candidate.cache_created_at).total_seconds()
        if cache_age >= threshold:
            return PlannedBuild(candidate, self.PRIORITY_SOFT_TTL_ELAPSED, "soft_ttl_elapsed")
        return None


def build_candidate_from_cache_state(
    *,
    instrument_id: str,
    page: str,
    timeframe: str,
    candidates: Sequence[str],
    cache_entry: Any,
    last_access_at: datetime | None,
    source_changed: bool = False,
    is_core_instrument: bool = False,
    current_page_active: bool = False,
) -> PrecomputeCandidate:
    created_at = None
    if cache_entry is not None:
        created_at = getattr(cache_entry, "source_updated_at", None)
        if created_at is None:
            created_at = getattr(cache_entry, "calculated_at", None)
    return PrecomputeCandidate(
        instrument_id=instrument_id,
        page=page,
        timeframe=timeframe,
        candidates=tuple(candidates),
        last_access_at=last_access_at,
        cache_created_at=created_at,
        source_changed=source_changed,
        is_core_instrument=is_core_instrument,
        current_page_active=current_page_active,
    )
