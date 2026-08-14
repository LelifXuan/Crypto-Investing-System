"""Cache-only request serving for strategy API.

This is the P5-3A core: the HTTP request path NEVER awaits a full strategy
build. It only reads cache, schedules single-flight background builds, and
returns a status-annotated response.

Cache state machine:
    FRESH        -> return cached payload as-is
    SOFT_STALE   -> return last-good with permission=observe; background refresh
    HARD_STALE   -> return observe/insufficient; background refresh
    MISS         -> return warming shell + job_id; background refresh
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Any, Callable, Mapping, Protocol

from .cache_policy import CachePolicy, CacheState, CanonicalCacheEntry, force_observe_projection, warming_payload
from .singleflight import BuildQueueFullError, SingleFlightBuildCoordinator, _SimpleMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache repository protocol (implemented by the project's actual cache layer)
# ---------------------------------------------------------------------------


class StrategyCacheRepository(Protocol):
    """Minimal cache interface required by the hot-path service."""

    async def get(self, instrument: str) -> CanonicalCacheEntry | None: ...

    async def publish_atomic(self, instrument: str, entry: CanonicalCacheEntry) -> None: ...


# ---------------------------------------------------------------------------
# Serve result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyServeResult:
    """Result of a strategy serve attempt."""

    cache_state: CacheState
    payload: Mapping[str, Any]
    refresh_job_id: str | None


# ---------------------------------------------------------------------------
# Hot-path service
# ---------------------------------------------------------------------------


class StrategyHotPathService:
    """Cache-only request policy. It never awaits a full strategy build.

    On fresh cache: returns immediately.
    On stale cache: returns degraded payload + triggers background build.
    On miss: returns warming shell + triggers background build.

    The cache is passed per-request (not at construction) because the
    cache adapter may hold per-request resources like DB sessions.
    """

    def __init__(
        self,
        *,
        coordinator: SingleFlightBuildCoordinator,
        policy: CachePolicy,
        metrics: _SimpleMetrics | None = None,
    ) -> None:
        policy.validate()
        self._coordinator = coordinator
        self._policy = policy
        self._metrics = metrics or _SimpleMetrics()

    async def serve(
        self,
        *,
        cache: StrategyCacheRepository,
        instrument: str,
        key_digest: str,
        builder_factory: Callable[[str], Awaitable[CanonicalCacheEntry]],
        now: datetime | None = None,
    ) -> StrategyServeResult:
        """Serve a strategy response from cache, scheduling refresh if needed.

        This method NEVER calls builder_factory directly. It only reads cache
        and schedules background builds via the single-flight coordinator.
        """
        started = time.perf_counter()
        current_time = now or datetime.now(timezone.utc)
        entry = await cache.get(instrument)

        try:
            if entry is None:
                job_id = await self._coordinator_schedule(key_digest, builder_factory)
                self._metrics.increment("strategy_cache_miss_total")
                return StrategyServeResult(
                    CacheState.MISS,
                    warming_payload(job_id=job_id, blocker="CANONICAL_CACHE_MISS"),
                    job_id,
                )

            state = entry.classify(current_time)
            age = max(0.0, (current_time - entry.created_at).total_seconds())

            if state is CacheState.FRESH:
                payload = _attach_cache_metadata(
                    entry.payload, state, age, None, entry, self._policy,
                )
                self._metrics.increment("strategy_cache_hit_total")
                return StrategyServeResult(state, payload, None)

            # Stale (soft or hard): schedule refresh and return degraded
            job_id = await self._coordinator_schedule(key_digest, builder_factory)
            if state is CacheState.SOFT_STALE:
                payload = force_observe_projection(
                    entry.payload,
                    blocker="CANONICAL_CACHE_STALE",
                    readiness="STALE",
                )
                self._metrics.increment("strategy_cache_soft_stale_total")
            else:
                payload = force_observe_projection(
                    entry.payload,
                    blocker="CANONICAL_CACHE_HARD_STALE",
                    readiness="INSUFFICIENT",
                )
                self._metrics.increment("strategy_cache_hard_stale_total")

            payload = _attach_cache_metadata(payload, state, age, job_id, entry, self._policy)
            return StrategyServeResult(state, payload, job_id)
        finally:
            self._metrics.observe(
                "strategy_request_duration_seconds",
                time.perf_counter() - started,
            )

    async def _coordinator_schedule(
        self,
        key_digest: str,
        builder_factory: Callable[[str], Awaitable[CanonicalCacheEntry]],
    ) -> str | None:
        """Schedule a background build via single-flight coordinator.

        The builder_factory is responsible for its own cache publishing
        (it has its own DB session). The coordinator only manages the
        single-flight guarantee (one build per key).
        """
        try:
            job = await self._coordinator.submit(key_digest, builder_factory)
            return job.job_id
        except BuildQueueFullError:
            logger.warning("strategy build queue full", extra={"build_key": key_digest})
            return None


def _attach_cache_metadata(
    payload: dict[str, Any],
    state: CacheState,
    age_seconds: float,
    job_id: str | None,
    entry: CanonicalCacheEntry,
    policy: CachePolicy,
) -> dict[str, Any]:
    """Attach cache metadata to a response payload.

    Skips if `cache` field already exists (e.g. warming_payload sets its own).
    """
    if payload.get("cache") is not None:
        return payload
    payload["cache"] = {
        "state": state.value,
        "age_seconds": round(age_seconds, 1),
        "soft_ttl_seconds": policy.soft_ttl_seconds,
        "hard_ttl_seconds": policy.hard_ttl_seconds,
        "refresh_job_id": job_id,
        "last_success_at": entry.last_success_at.isoformat(),
        "last_failure": None,
    }
    return payload
