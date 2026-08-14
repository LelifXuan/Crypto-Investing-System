"""Strategy runtime services: build identity, single-flight, cache policy, executor."""

from .build_key import BuildKey, build_strategy_key
from .cache_policy import CachePolicy, CacheState, CanonicalCacheEntry, force_observe_projection, warming_payload
from .hot_path import StrategyHotPathService, StrategyCacheRepository, StrategyServeResult
from .indicator_executor import IndicatorExecutor
from .precompute_planner import PrecomputePlanner, PrecomputeCandidate, PlannedBuild, build_candidate_from_cache_state
from .singleflight import SingleFlightBuildCoordinator, BuildJob, BuildJobState, BuildQueueFullError, _SimpleMetrics

__all__ = [
    "BuildKey",
    "build_strategy_key",
    "CachePolicy",
    "CacheState",
    "CanonicalCacheEntry",
    "force_observe_projection",
    "warming_payload",
    "IndicatorExecutor",
    "SingleFlightBuildCoordinator",
    "BuildJob",
    "BuildJobState",
    "BuildQueueFullError",
    "_SimpleMetrics",
    "StrategyHotPathService",
    "StrategyCacheRepository",
    "StrategyServeResult",
    "PrecomputePlanner",
    "PrecomputeCandidate",
    "PlannedBuild",
    "build_candidate_from_cache_state",
]
