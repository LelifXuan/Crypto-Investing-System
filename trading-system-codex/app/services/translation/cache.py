from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.ids import new_id
from app.db.models.market import MarketEventTranslationMap, TranslationJob, TranslationTextCache
from app.repositories.market_repository import MarketRepository


@dataclass(slots=True)
class SegmentCacheResult:
    status: str
    translated_text: str | None = None


class TranslationCacheStore:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_segment(
        self,
        *,
        provider: str,
        source_language: str,
        target_language: str,
        normalized_text: str,
        normalized_hash: str,
    ) -> SegmentCacheResult | None:
        entry = await self.repository.get_translation_text_cache(
            provider=provider,
            source_language=source_language,
            target_language=target_language,
            normalized_text_hash=normalized_hash,
        )
        if entry is None:
            return None
        entry.hit_count += 1
        await self.repository.upsert_translation_text_cache(entry)
        if entry.status == "translated" and entry.translated_text:
            return SegmentCacheResult(status="translated", translated_text=entry.translated_text)
        if entry.status == "error" and entry.retry_after and entry.retry_after > datetime.now(UTC):
            return SegmentCacheResult(status="error", translated_text=None)
        return SegmentCacheResult(status=entry.status, translated_text=entry.translated_text)

    async def store_segment(
        self,
        *,
        provider: str,
        source_language: str,
        target_language: str,
        normalized_text: str,
        normalized_hash: str,
        translated_text: str | None,
        status: str,
        error_message: str | None = None,
    ) -> None:
        await self.repository.upsert_translation_text_cache(
            TranslationTextCache(
                cache_id=new_id("ttc"),
                provider=provider,
                source_language=source_language,
                target_language=target_language,
                normalized_text_hash=normalized_hash,
                normalized_text=normalized_text,
                translated_text=translated_text,
                status=status,
                error_message=error_message,
                retry_after=(
                    datetime.now(UTC)
                    + timedelta(seconds=settings.market_events_translation_retry_delay_seconds)
                    if status == "error"
                    else None
                ),
                hit_count=0,
            )
        )

    async def mark_event_field(
        self,
        *,
        event_id: str,
        field_name: str,
        provider: str,
        source_language: str,
        target_language: str,
        normalized_hash: str,
        status: str,
        translated_text: str | None,
        error_message: str | None = None,
    ) -> None:
        await self.repository.upsert_market_event_translation_map(
            MarketEventTranslationMap(
                event_id=event_id,
                field_name=field_name,
                provider=provider,
                source_language=source_language,
                target_language=target_language,
                normalized_text_hash=normalized_hash,
                status=status,
                translated_text=translated_text,
                error_message=error_message,
            )
        )

    async def upsert_job(
        self,
        *,
        dedupe_key: str,
        provider: str,
        source_language: str,
        target_language: str,
        segment_count: int,
        status: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> TranslationJob:
        return await self.repository.upsert_translation_job(
            TranslationJob(
                job_id=new_id("trj"),
                dedupe_key=dedupe_key,
                provider=provider,
                source_language=source_language,
                target_language=target_language,
                segment_count=segment_count,
                status=status,
                error_message=error_message,
                scheduled_at=datetime.now(UTC),
                started_at=started_at,
                finished_at=finished_at,
            )
        )
