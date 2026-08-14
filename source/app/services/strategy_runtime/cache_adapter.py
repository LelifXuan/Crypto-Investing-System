"""Adapter: project's PageSnapshotCache -> CanonicalCacheRepository protocol.

Bridges the existing SQLite-backed cache to the StrategyHotPathService
without modifying the underlying repository or schema.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services.cache_registry import expires_at_for_page

from .cache_policy import CachePolicy, CanonicalCacheEntry

logger = logging.getLogger(__name__)


class PageSnapshotCacheAdapter:
    """Adapts the project's repository + CachePolicy to StrategyCacheRepository.

    Reads from PageSnapshotCache table, converts rows to CanonicalCacheEntry.
    Writes publish new entries back atomically.

    The adapter is constructed per-request with a repository (DB session),
    then passed to StrategyHotPathService.serve() as the cache.
    """

    def __init__(self, *, policy: CachePolicy, repository: Any) -> None:
        self._policy = policy
        self._repository = repository

    async def get(self, instrument: str) -> CanonicalCacheEntry | None:
        """Read and classify a cached strategy response.

        Returns None on any error (missing table, DB unavailable, etc.)
        so the hot path can fall through to the background build path.
        """
        cache_key = self._cache_key(instrument)
        try:
            cache = await self._repository.get_page_snapshot_cache(cache_key)
        except Exception:
            # DB may not be initialized (tests) or table may not exist.
            # Treat as cache miss so the hot path can schedule a build.
            return None
        if cache is None or not cache.payload_json:
            return None

        now = datetime.now(timezone.utc)
        created_at = self._parse_ts(getattr(cache, "source_updated_at", None)) or now
        soft_expires, hard_expires = self._policy.compute_expiry(created_at)

        return CanonicalCacheEntry(
            payload=dict(cache.payload_json),
            created_at=created_at,
            soft_expires_at=soft_expires,
            hard_expires_at=hard_expires,
            last_success_at=created_at,
            build_key=instrument,
        )

    async def publish_atomic(
        self,
        instrument: str,
        entry: CanonicalCacheEntry,
    ) -> None:
        """Publish a new strategy response to cache (atomic upsert)."""
        cache_key = self._cache_key(instrument)
        try:
            await self._repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="strategy_unified",
                payload_json=dict(entry.payload),
                status="ready",
                cache_state="fresh",
                instrument_id=instrument,
                source_updated_at=entry.created_at,
                source_version="strategy_runtime_v1",
            )
        except Exception:
            logger.exception("strategy cache publish failed", extra={"instrument": instrument})

    @staticmethod
    def _cache_key(instrument: str) -> str:
        from app.services.cache_registry import strategy_unified_cache_key
        return strategy_unified_cache_key(instrument)

    @staticmethod
    def _parse_ts(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return None
