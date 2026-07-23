from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.repositories.market_repository import MarketRepository
from app.services.cache_registry import (
    bundle_status_message,
    cache_status,
    dataset_cache_status,
)

UTC = timezone.utc


@dataclass(slots=True)
class CacheEnvelope:
    status: str
    payload: dict
    snapshot_at: datetime | None
    data_ts: datetime | None
    expires_at: datetime | None
    source_version: str
    source_updated_at: datetime | None
    cost_ms: int | None
    status_message: str


class PageCacheService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def read_page_bundle(self, cache_key: str) -> CacheEnvelope:
        cache = await self.repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        return CacheEnvelope(
            status=status,
            payload=payload,
            snapshot_at=cache.snapshot_at if cache else None,
            data_ts=cache.data_ts if cache else None,
            expires_at=cache.expires_at if cache else None,
            source_version=(cache.source_version if cache else "v2"),
            source_updated_at=cache.source_updated_at if cache else None,
            cost_ms=cache.cost_ms if cache else None,
            status_message=bundle_status_message(status),
        )

    async def read_dataset(self, cache_key: str) -> CacheEnvelope:
        cache = await self.repository.get_computed_dataset_cache(cache_key)
        status = dataset_cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        return CacheEnvelope(
            status=status,
            payload=payload,
            snapshot_at=cache.calculated_at if cache else None,
            data_ts=cache.source_data_ts if cache else None,
            expires_at=cache.expires_at if cache else None,
            source_version=(cache.source_version if cache else "v2"),
            source_updated_at=cache.source_data_ts if cache else None,
            cost_ms=cache.cost_ms if cache else None,
            status_message=bundle_status_message(status),
        )

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
