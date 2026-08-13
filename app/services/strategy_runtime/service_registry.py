"""Service registry: assembles the P5 runtime components.

Creates and wires together:
- SingleFlightBuildCoordinator (one build per key)
- CachePolicy (soft/hard TTL)
- IndicatorExecutor (bounded thread pool for Decimal math)
- _SimpleMetrics (in-process counters)
"""

from __future__ import annotations

import logging

from app.core.config import settings

from .cache_adapter import PageSnapshotCacheAdapter
from .cache_policy import CachePolicy
from .hot_path import StrategyHotPathService
from .indicator_executor import IndicatorExecutor
from .singleflight import SingleFlightBuildCoordinator, _SimpleMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Process-wide singletons (initialized on first access)
# ---------------------------------------------------------------------------

_metrics: _SimpleMetrics | None = None
_coordinator: SingleFlightBuildCoordinator | None = None
_indicator_executor: IndicatorExecutor | None = None
_cache_policy: CachePolicy | None = None


def get_metrics() -> _SimpleMetrics:
    global _metrics
    if _metrics is None:
        _metrics = _SimpleMetrics()
    return _metrics


def get_coordinator() -> SingleFlightBuildCoordinator:
    global _coordinator
    if _coordinator is None:
        # Bound inflight builds to prevent SQLite write contention.
        # Use precompute concurrency as a sane default; override via settings if needed.
        max_inflight = getattr(settings, "strategy_max_inflight_builds", None) or 2
        _coordinator = SingleFlightBuildCoordinator(
            max_inflight=max_inflight,
            metrics=get_metrics(),
        )
    return _coordinator


def get_indicator_executor() -> IndicatorExecutor:
    global _indicator_executor
    if _indicator_executor is None:
        _indicator_executor = IndicatorExecutor(
            max_workers=2,
            queue_limit=4,
            metrics=get_metrics(),
        )
    return _indicator_executor


def get_cache_policy() -> CachePolicy:
    global _cache_policy
    if _cache_policy is None:
        _cache_policy = CachePolicy(
            soft_ttl_seconds=settings.page_snapshot_analysis_ttl_seconds,
            hard_ttl_seconds=settings.page_snapshot_analysis_ttl_seconds * 3,
        )
        _cache_policy.validate()
    return _cache_policy


_hot_path_service: StrategyHotPathService | None = None


def get_hot_path_service() -> StrategyHotPathService:
    """Factory for the cache-only hot-path service (singleton)."""
    global _hot_path_service
    if _hot_path_service is None:
        _hot_path_service = StrategyHotPathService(
            coordinator=get_coordinator(),
            policy=get_cache_policy(),
            metrics=get_metrics(),
        )
    return _hot_path_service


def get_metrics_snapshot() -> dict:
    """Return current metrics snapshot for diagnostics."""
    return get_metrics().snapshot()


def get_cache_adapter(*, repository: object) -> PageSnapshotCacheAdapter:
    """Create a per-request cache adapter bound to a repository."""
    return PageSnapshotCacheAdapter(policy=get_cache_policy(), repository=repository)
