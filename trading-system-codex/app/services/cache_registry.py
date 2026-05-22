from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.timeframes import (
    bucket_limit,
    normalize_instrument_id,
    normalize_timeframe_for_cache,
)
from app.db.models.market import ComputedDatasetCache, PageSnapshotCache

UTC = timezone.utc
CACHE_SOURCE_VERSION = "v3"
KNOWLEDGE_CATALOG_VERSION = "v4"

STRATEGY_TTL_SECONDS = {
    "15m": 120,
    "1h": 300,
    "4h": 900,
    "1d": 3600,
    "1w": 21600,
    "30d": 43200,
    "1M": 43200,
}

STRATEGY_DEPENDENCY_MAX_STALE_SECONDS = {
    "15m": 300,
    "1h": 600,
    "4h": 1800,
    "1d": 7200,
    "1w": 43200,
    "30d": 86400,
    "1M": 86400,
}


def analysis_cache_key(
    instrument_id: str,
    timeframe: str,
    limit: int,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "analysis:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:"
        f"{bucket_limit(limit)}:{source_version}"
    )


def structure_bundle_cache_key(
    instrument_id: str,
    timeframe: str,
    include_geometry: bool,
    candles_limit: int,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "structure_bundle:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:"
        f"{include_geometry}:{bucket_limit(candles_limit)}:{source_version}"
    )


def alerts_bundle_cache_key(
    instrument_id: str,
    timeframe: str,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "alerts_bundle:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:{source_version}"
    )


def monitoring_dashboard_cache_key(
    instrument_id: str,
    timeframe: str,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "monitoring_dashboard:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:{source_version}"
    )


def strategy_bundle_cache_key(
    instrument_id: str,
    timeframe: str,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "strategy_bundle:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:{source_version}"
    )


def macro_calendar_cache_key(
    limit: int,
    status: str | None,
    event_key: str | None,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return f"macro_calendar:{status or '-'}:{limit}:{source_version}:{event_key or '-'}"


def market_events_cache_key(
    limit: int,
    translate: bool,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return f"market_events:{limit}:{str(bool(translate)).lower()}:{source_version}"


def indicator_series_cache_key(
    instrument_id: str,
    timeframe: str,
    indicator_group: str,
    source_data_ts: datetime | None,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    ts_key = int(source_data_ts.timestamp()) if source_data_ts else "na"
    return (
        "indicator_series:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:"
        f"{indicator_group}:{ts_key}:{source_version}"
    )


def microstructure_cache_key(
    instrument_id: str,
    timeframe: str,
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "microstructure:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:{source_version}"
    )


def knowledge_catalog_cache_key(version: str = KNOWLEDGE_CATALOG_VERSION) -> str:
    return f"knowledge_catalog:{version}"


def strategy_ttl_seconds_for_timeframe(timeframe: str) -> int:
    normalized = normalize_timeframe_for_cache(timeframe)
    if normalized == "30d":
        return STRATEGY_TTL_SECONDS["30d"]
    return STRATEGY_TTL_SECONDS.get(normalized, STRATEGY_TTL_SECONDS["1d"])


def strategy_dependency_max_stale_seconds_for_timeframe(timeframe: str) -> int:
    normalized = normalize_timeframe_for_cache(timeframe)
    if normalized == "30d":
        return STRATEGY_DEPENDENCY_MAX_STALE_SECONDS["30d"]
    return STRATEGY_DEPENDENCY_MAX_STALE_SECONDS.get(
        normalized,
        STRATEGY_DEPENDENCY_MAX_STALE_SECONDS["1d"],
    )


def ttl_seconds_for_page(page_type: str) -> int:
    mapping = {
        "analysis": settings.page_snapshot_analysis_ttl_seconds,
        "structure": settings.page_snapshot_structure_ttl_seconds,
        "alerts": settings.page_snapshot_alerts_ttl_seconds,
        "monitoring": settings.page_snapshot_monitoring_ttl_seconds,
        "macro": settings.page_snapshot_macro_ttl_seconds,
        "events": settings.page_snapshot_events_ttl_seconds,
        "strategy": settings.page_snapshot_analysis_ttl_seconds,
    }
    return mapping.get(page_type, settings.page_snapshot_analysis_ttl_seconds)


def dataset_ttl_seconds(dataset_type: str) -> int:
    mapping = {
        "market_bundle": 180,
        "contract_snapshot": 30,
        "contract_snapshot_core": 5,
        "contract_snapshot_stats": 60,
        "contract_snapshot_book": 5,
        "contract_snapshot_trades": 20,
        "indicator_matrix": 240,
        "indicator_series_core": 120,
        "indicator_series_secondary": 240,
        "microstructure": 30,
        "knowledge_catalog": 86400,
    }
    return mapping.get(dataset_type, 120)


def expires_at_for_page(page_type: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now + timedelta(seconds=ttl_seconds_for_page(page_type))


def expires_at_for_strategy(timeframe: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now + timedelta(seconds=strategy_ttl_seconds_for_timeframe(timeframe))


def expires_at_for_dataset(dataset_type: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now + timedelta(seconds=dataset_ttl_seconds(dataset_type))


def _normalize_expires_at(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def is_page_cache_fresh(
    cache: PageSnapshotCache | None,
    now: datetime | None = None,
) -> bool:
    if cache is None or cache.expires_at is None:
        return False
    now = now or datetime.now(UTC)
    return _normalize_expires_at(cache.expires_at) >= now


def is_dataset_cache_fresh(
    cache: ComputedDatasetCache | None,
    now: datetime | None = None,
) -> bool:
    if cache is None or cache.expires_at is None:
        return False
    now = now or datetime.now(UTC)
    return _normalize_expires_at(cache.expires_at) >= now


def cache_status(cache: PageSnapshotCache | None, now: datetime | None = None) -> str:
    if cache is None:
        return "missing"
    current_state = cache.cache_state or cache.status
    if current_state in {"updating", "refreshing"}:
        return "updating"
    if current_state in {"error", "missing", "stale"}:
        return current_state
    return "fresh" if is_page_cache_fresh(cache, now=now) else "stale"


def dataset_cache_status(
    cache: ComputedDatasetCache | None,
    now: datetime | None = None,
) -> str:
    if cache is None:
        return "missing"
    if cache.cache_state in {"error", "missing", "stale"}:
        return cache.cache_state
    return "fresh" if is_dataset_cache_fresh(cache, now=now) else "stale"


def bundle_status_message(status: str) -> str:
    mapping = {
        "fresh": "数据已就绪",
        "ready": "数据已就绪",
        "stale": "快照可用，但可能略有延迟",
        "missing": "暂无快照，已加入预计算队列",
        "updating": "后台正在准备最新数据",
        "refreshing": "后台正在刷新数据",
        "error": "预计算失败，可手动刷新",
        "low_confidence": "策略信号可用，但置信度较低",
    }
    return mapping.get(status, "状态未知")
