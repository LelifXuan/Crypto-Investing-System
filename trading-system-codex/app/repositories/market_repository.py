from __future__ import annotations

from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, desc, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.instrument import Instrument
from app.db.models.market import (
    ComputedDatasetCache,
    IndicatorAlertEvent,
    IndicatorAlertRule,
    IndicatorDefinition,
    IndicatorMonitoringPolicy,
    IndicatorObservation,
    IndicatorRefreshPolicy,
    IndicatorRun,
    IndicatorValue,
    MacroEventCalendar,
    MacroSourceHealth,
    MarketCandle,
    MarketEvent,
    MarketEventInstrument,
    MarketEventTranslationMap,
    MarkPrice,
    PageSnapshotCache,
    SignalOutcome,
    StrategyDecision,
    StrategyDecisionOutcome,
    StrategyIterationProposal,
    StructureActiveItem,
    StructureAlert,
    StructureEvent,
    StructureGeometry,
    StructureSnapshot,
    StructureSystemJudgement,
    StructureSystemScore,
    TranslationCache,
    TranslationJob,
    TranslationTextCache,
)

UTC = timezone.utc


class MarketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _market_event_link(event: MarketEvent) -> str:
        payload = getattr(event, "payload_json", {}) or {}
        return str(payload.get("link") or "").strip()

    @classmethod
    def _market_event_dedupe_key(cls, event: MarketEvent) -> tuple[str, str, str]:
        ts = event.ts_event.isoformat() if getattr(event, "ts_event", None) else ""
        return (str(getattr(event, "title", "")).strip(), ts, cls._market_event_link(event))

    async def _find_matching_market_event(self, event: MarketEvent) -> MarketEvent | None:
        result = await self.session.execute(
            select(MarketEvent).where(
                MarketEvent.title == event.title,
                MarketEvent.ts_event == event.ts_event,
            )
        )
        candidates = list(result.scalars().all())
        event_link = self._market_event_link(event)
        if event_link:
            for candidate in candidates:
                if self._market_event_link(candidate) == event_link:
                    return candidate
        return candidates[0] if candidates else None

    async def get_instrument(self, instrument_id: str) -> Instrument | None:
        return await self.session.get(Instrument, instrument_id)

    async def list_instruments(self) -> list[Instrument]:
        result = await self.session.execute(select(Instrument).order_by(Instrument.instrument_id))
        return list(result.scalars().all())

    async def list_gateio_stream_instruments(self) -> list[Instrument]:
        result = await self.session.execute(
            select(Instrument).where(
                or_(
                    Instrument.venue.ilike("%gate%"),
                    Instrument.metadata_json.contains({"gateio": {}}),
                )
            )
        )
        return list(result.scalars().all())

    async def add_mark_price(self, mark: MarkPrice) -> MarkPrice:
        self.session.add(mark)
        await self.session.flush()
        return mark

    async def latest_mark(self, instrument_id: str) -> MarkPrice | None:
        result = await self.session.execute(
            select(MarkPrice)
            .where(MarkPrice.instrument_id == instrument_id)
            .order_by(desc(MarkPrice.ts_event))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_candle(self, candle: MarketCandle) -> MarketCandle:
        self.session.add(candle)
        await self.session.flush()
        return candle

    async def upsert_candles(self, candles: list[MarketCandle]) -> list[MarketCandle]:
        if not candles:
            return []
        deduped: dict[tuple[str, str, datetime, str], MarketCandle] = {}
        for candle in candles:
            key = (candle.instrument_id, candle.timeframe, candle.ts_open, candle.source)
            deduped[key] = candle
        unique_candles = list(deduped.values())
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name in {"sqlite", "postgresql"}:
            rows = [
                {
                    "instrument_id": candle.instrument_id,
                    "timeframe": candle.timeframe,
                    "ts_open": candle.ts_open,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "source": candle.source,
                }
                for candle in unique_candles
            ]
            insert_stmt = (
                sqlite_insert(MarketCandle)
                if dialect_name == "sqlite"
                else postgresql_insert(MarketCandle)
            )
            upsert_stmt = insert_stmt.values(rows).on_conflict_do_update(
                index_elements=["instrument_id", "timeframe", "ts_open", "source"],
                set_={
                    "open": insert_stmt.excluded.open,
                    "high": insert_stmt.excluded.high,
                    "low": insert_stmt.excluded.low,
                    "close": insert_stmt.excluded.close,
                    "volume": insert_stmt.excluded.volume,
                },
            )
            await self.session.execute(upsert_stmt)
            await self.session.flush()
            return await self._fetch_candles_by_keys(list(deduped))
        return await self._apply_candle_upserts(unique_candles)

    async def _apply_candle_upserts(self, candles: list[MarketCandle]) -> list[MarketCandle]:
        existing_map = {
            (c.instrument_id, c.timeframe, c.ts_open, c.source): c
            for c in await self._fetch_candles_by_keys(
                [(c.instrument_id, c.timeframe, c.ts_open, c.source) for c in candles]
            )
        }
        persisted: list[MarketCandle] = []
        for candle in candles:
            key = (candle.instrument_id, candle.timeframe, candle.ts_open, candle.source)
            if key in existing_map:
                existing_item = existing_map[key]
                existing_item.open = candle.open
                existing_item.high = candle.high
                existing_item.low = candle.low
                existing_item.close = candle.close
                existing_item.volume = candle.volume
                persisted.append(existing_item)
                continue
            self.session.add(candle)
            persisted.append(candle)
        await self.session.flush()
        persisted.sort(key=lambda c: c.ts_open)
        return persisted

    async def _fetch_candles_by_keys(
        self, keys: list[tuple[str, str, datetime, str]]
    ) -> list[MarketCandle]:
        if not keys:
            return []
        existing_stmt = select(MarketCandle).where(
            tuple_(
                MarketCandle.instrument_id,
                MarketCandle.timeframe,
                MarketCandle.ts_open,
                MarketCandle.source,
            ).in_(keys)
        )
        existing_result = await self.session.execute(existing_stmt)
        candles = list(existing_result.scalars().all())
        candles.sort(key=lambda c: c.ts_open)
        return candles

    async def list_candles(
        self, instrument_id: str, timeframe: str, limit: int = 200
    ) -> list[MarketCandle]:
        result = await self.session.execute(
            select(MarketCandle)
            .where(MarketCandle.instrument_id == instrument_id, MarketCandle.timeframe == timeframe)
            .order_by(desc(MarketCandle.ts_open))
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_candles_filtered(
        self,
        instrument_id: str,
        timeframe: str,
        limit: int = 200,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[MarketCandle]:
        stmt = select(MarketCandle).where(
            MarketCandle.instrument_id == instrument_id,
            MarketCandle.timeframe == timeframe,
        )
        if from_ts is not None:
            stmt = stmt.where(MarketCandle.ts_open >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(MarketCandle.ts_open <= to_ts)
        stmt = stmt.order_by(desc(MarketCandle.ts_open)).limit(limit)
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def get_page_snapshot_cache(self, cache_key: str) -> PageSnapshotCache | None:
        result = await self.session.execute(
            select(PageSnapshotCache).where(PageSnapshotCache.cache_key == cache_key)
        )
        return result.scalar_one_or_none()

    async def upsert_page_snapshot_cache(
        self,
        *,
        cache_key: str,
        page_type: str,
        payload_json: dict,
        status: str,
        cache_state: str | None = None,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        snapshot_at: datetime | None = None,
        data_ts: datetime | None = None,
        expires_at: datetime | None = None,
        source_updated_at: datetime | None = None,
        source_version: str = "v1",
        cost_ms: int | None = None,
        last_error: str | None = None,
        meta_json: dict | None = None,
    ) -> PageSnapshotCache:
        existing = await self.get_page_snapshot_cache(cache_key)
        normalized_state = cache_state or status
        if existing is None:
            model = PageSnapshotCache(
                cache_key=cache_key,
                page_type=page_type,
                instrument_id=instrument_id,
                timeframe=timeframe,
                payload_json=jsonable_encoder(payload_json),
                status=status,
                cache_state=normalized_state,
                snapshot_at=snapshot_at,
                data_ts=data_ts,
                expires_at=expires_at,
                source_updated_at=source_updated_at,
                source_version=source_version,
                cost_ms=cost_ms,
                last_error=last_error,
                meta_json=jsonable_encoder(meta_json or {}),
            )
            self.session.add(model)
            await self.session.flush()
            return model
        existing.page_type = page_type
        existing.instrument_id = instrument_id
        existing.timeframe = timeframe
        existing.payload_json = jsonable_encoder(payload_json)
        existing.status = status
        existing.cache_state = normalized_state
        existing.snapshot_at = snapshot_at
        existing.data_ts = data_ts
        existing.expires_at = expires_at
        existing.source_updated_at = source_updated_at
        existing.source_version = source_version
        existing.cost_ms = cost_ms
        existing.last_error = last_error
        existing.meta_json = jsonable_encoder(meta_json or {})
        await self.session.flush()
        return existing

    async def delete_expired_page_snapshot_cache(
        self, now: datetime | None = None, limit: int = 500
    ) -> int:
        now = now or datetime.now(timezone.utc)
        rows = await self.session.execute(
            select(PageSnapshotCache.cache_id)
            .where(
                PageSnapshotCache.expires_at.is_not(None),
                PageSnapshotCache.expires_at < now,
            )
            .order_by(PageSnapshotCache.expires_at.asc())
            .limit(limit)
        )
        cache_ids = list(rows.scalars().all())
        if not cache_ids:
            return 0
        await self.session.execute(
            delete(PageSnapshotCache).where(PageSnapshotCache.cache_id.in_(cache_ids))
        )
        await self.session.flush()
        return len(cache_ids)

    async def get_computed_dataset_cache(self, cache_key: str) -> ComputedDatasetCache | None:
        result = await self.session.execute(
            select(ComputedDatasetCache).where(ComputedDatasetCache.cache_key == cache_key)
        )
        return result.scalar_one_or_none()

    async def upsert_computed_dataset_cache(
        self,
        *,
        cache_key: str,
        dataset_type: str,
        payload_json: dict,
        cache_state: str,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        source_data_ts: datetime | None = None,
        source_hash: str | None = None,
        source_version: str = "v1",
        calculated_at: datetime | None = None,
        expires_at: datetime | None = None,
        cost_ms: int | None = None,
        error_message: str | None = None,
        meta_json: dict | None = None,
    ) -> ComputedDatasetCache:
        existing = await self.get_computed_dataset_cache(cache_key)
        if existing is None:
            model = ComputedDatasetCache(
                cache_key=cache_key,
                dataset_type=dataset_type,
                instrument_id=instrument_id,
                timeframe=timeframe,
                source_data_ts=source_data_ts,
                source_hash=source_hash,
                payload_json=jsonable_encoder(payload_json),
                cache_state=cache_state,
                source_version=source_version,
                calculated_at=calculated_at,
                expires_at=expires_at,
                cost_ms=cost_ms,
                error_message=error_message,
                meta_json=jsonable_encoder(meta_json or {}),
            )
            self.session.add(model)
            await self.session.flush()
            return model
        existing.dataset_type = dataset_type
        existing.instrument_id = instrument_id
        existing.timeframe = timeframe
        existing.source_data_ts = source_data_ts
        existing.source_hash = source_hash
        existing.payload_json = jsonable_encoder(payload_json)
        existing.cache_state = cache_state
        existing.source_version = source_version
        existing.calculated_at = calculated_at
        existing.expires_at = expires_at
        existing.cost_ms = cost_ms
        existing.error_message = error_message
        existing.meta_json = jsonable_encoder(meta_json or {})
        await self.session.flush()
        return existing

    async def delete_expired_computed_dataset_cache(
        self, now: datetime | None = None, limit: int = 500
    ) -> int:
        now = now or datetime.now(timezone.utc)
        rows = await self.session.execute(
            select(ComputedDatasetCache.dataset_cache_id)
            .where(
                ComputedDatasetCache.expires_at.is_not(None),
                ComputedDatasetCache.expires_at < now,
            )
            .order_by(ComputedDatasetCache.expires_at.asc())
            .limit(limit)
        )
        cache_ids = list(rows.scalars().all())
        if not cache_ids:
            return 0
        await self.session.execute(
            delete(ComputedDatasetCache).where(
                ComputedDatasetCache.dataset_cache_id.in_(cache_ids)
            )
        )
        await self.session.flush()
        return len(cache_ids)

    async def add_indicator_value(self, value: IndicatorValue) -> IndicatorValue:
        result = await self.session.execute(
            select(IndicatorValue).where(
                IndicatorValue.instrument_id == value.instrument_id,
                IndicatorValue.timeframe == value.timeframe,
                IndicatorValue.indicator_name == value.indicator_name,
                IndicatorValue.params_hash == value.params_hash,
                IndicatorValue.ts_value == value.ts_value,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.value_json = value.value_json
            await self.session.flush()
            return existing
        self.session.add(value)
        await self.session.flush()
        return value

    async def list_indicator_values(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_name: str | None = None,
        limit: int = 50,
    ) -> list[IndicatorValue]:
        stmt = select(IndicatorValue).where(
            IndicatorValue.instrument_id == instrument_id,
            IndicatorValue.timeframe == timeframe,
        )
        if indicator_name:
            stmt = stmt.where(IndicatorValue.indicator_name == indicator_name)
        stmt = stmt.order_by(desc(IndicatorValue.ts_value)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_indicator_refresh_policy(
        self, policy: IndicatorRefreshPolicy
    ) -> IndicatorRefreshPolicy:
        result = await self.session.execute(
            select(IndicatorRefreshPolicy).where(
                IndicatorRefreshPolicy.instrument_id == policy.instrument_id,
                IndicatorRefreshPolicy.timeframe == policy.timeframe,
                IndicatorRefreshPolicy.price_kind == policy.price_kind,
                IndicatorRefreshPolicy.source_preference == policy.source_preference,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(policy)
            await self.session.flush()
            return policy
        existing.is_enabled = policy.is_enabled
        existing.persist_candles = policy.persist_candles
        existing.fetch_limit = policy.fetch_limit
        existing.parameters_json = policy.parameters_json
        await self.session.flush()
        return existing

    async def list_indicator_refresh_policies(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        enabled_only: bool = False,
    ) -> list[IndicatorRefreshPolicy]:
        stmt = select(IndicatorRefreshPolicy)
        if instrument_id:
            stmt = stmt.where(IndicatorRefreshPolicy.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(IndicatorRefreshPolicy.timeframe == timeframe)
        if enabled_only:
            stmt = stmt.where(IndicatorRefreshPolicy.is_enabled.is_(True))
        stmt = stmt.order_by(IndicatorRefreshPolicy.instrument_id, IndicatorRefreshPolicy.timeframe)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_indicator_refresh_policy(self, policy_id: int) -> bool:
        policy = await self.session.get(IndicatorRefreshPolicy, policy_id)
        if policy is None:
            return False
        await self.session.delete(policy)
        await self.session.flush()
        return True

    async def add_market_event(self, event: MarketEvent) -> MarketEvent:
        matched = await self._find_matching_market_event(event)
        if matched is not None and matched.event_id != event.event_id:
            event.event_id = matched.event_id
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name in {"sqlite", "postgresql"}:
            row = {
                "event_id": event.event_id,
                "category": event.category,
                "title": event.title,
                "summary": event.summary,
                "source": event.source,
                "reliability": event.reliability,
                "ts_event": event.ts_event,
                "payload_json": event.payload_json,
            }
            insert_stmt = (
                sqlite_insert(MarketEvent)
                if dialect_name == "sqlite"
                else postgresql_insert(MarketEvent)
            )
            upsert_stmt = insert_stmt.values(row).on_conflict_do_update(
                index_elements=["event_id"],
                set_={
                    "category": insert_stmt.excluded.category,
                    "title": insert_stmt.excluded.title,
                    "summary": insert_stmt.excluded.summary,
                    "source": insert_stmt.excluded.source,
                    "reliability": insert_stmt.excluded.reliability,
                    "ts_event": insert_stmt.excluded.ts_event,
                    "payload_json": insert_stmt.excluded.payload_json,
                },
            )
            await self.session.execute(upsert_stmt)
            await self.session.flush()
            return await self.session.get(MarketEvent, event.event_id)
        existing = await self.session.get(MarketEvent, event.event_id)
        if existing is not None:
            existing.category = event.category
            existing.title = event.title
            existing.summary = event.summary
            existing.source = event.source
            existing.reliability = event.reliability
            existing.ts_event = event.ts_event
            existing.payload_json = event.payload_json
            await self.session.flush()
            return existing
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_translation_cache(
        self,
        *,
        provider: str,
        target_language: str,
        source_text_hash: str,
    ) -> TranslationCache | None:
        result = await self.session.execute(
            select(TranslationCache).where(
                TranslationCache.provider == provider,
                TranslationCache.target_language == target_language,
                TranslationCache.source_text_hash == source_text_hash,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_translation_cache(self, cache: TranslationCache) -> TranslationCache:
        existing = await self.get_translation_cache(
            provider=cache.provider,
            target_language=cache.target_language,
            source_text_hash=cache.source_text_hash,
        )
        if existing is None:
            self.session.add(cache)
            await self.session.flush()
            return cache
        existing.source_text = cache.source_text
        existing.translated_text = cache.translated_text
        existing.status = cache.status
        existing.error_message = cache.error_message
        existing.retry_after = cache.retry_after
        existing.hit_count = cache.hit_count
        await self.session.flush()
        return existing

    async def get_translation_text_cache(
        self,
        *,
        provider: str,
        source_language: str,
        target_language: str,
        normalized_text_hash: str,
    ) -> TranslationTextCache | None:
        result = await self.session.execute(
            select(TranslationTextCache).where(
                TranslationTextCache.provider == provider,
                TranslationTextCache.source_language == source_language,
                TranslationTextCache.target_language == target_language,
                TranslationTextCache.normalized_text_hash == normalized_text_hash,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_translation_text_cache(
        self, cache: TranslationTextCache
    ) -> TranslationTextCache:
        existing = await self.get_translation_text_cache(
            provider=cache.provider,
            source_language=cache.source_language,
            target_language=cache.target_language,
            normalized_text_hash=cache.normalized_text_hash,
        )
        if existing is None:
            self.session.add(cache)
            await self.session.flush()
            return cache
        existing.normalized_text = cache.normalized_text
        existing.translated_text = cache.translated_text
        existing.status = cache.status
        existing.error_message = cache.error_message
        existing.retry_after = cache.retry_after
        existing.hit_count = cache.hit_count
        await self.session.flush()
        return existing

    async def get_translation_job(self, dedupe_key: str) -> TranslationJob | None:
        result = await self.session.execute(
            select(TranslationJob).where(TranslationJob.dedupe_key == dedupe_key)
        )
        return result.scalar_one_or_none()

    async def upsert_translation_job(self, job: TranslationJob) -> TranslationJob:
        existing = await self.get_translation_job(job.dedupe_key)
        if existing is None:
            self.session.add(job)
            await self.session.flush()
            return job
        existing.provider = job.provider
        existing.source_language = job.source_language
        existing.target_language = job.target_language
        existing.segment_count = job.segment_count
        existing.status = job.status
        existing.error_message = job.error_message
        existing.scheduled_at = job.scheduled_at
        existing.started_at = job.started_at
        existing.finished_at = job.finished_at
        await self.session.flush()
        return existing

    async def list_translation_jobs(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[TranslationJob]:
        stmt = select(TranslationJob)
        if status is not None:
            stmt = stmt.where(TranslationJob.status == status)
        stmt = stmt.order_by(desc(TranslationJob.scheduled_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_market_event_translation_map(
        self, mapping: MarketEventTranslationMap
    ) -> MarketEventTranslationMap:
        result = await self.session.execute(
            select(MarketEventTranslationMap).where(
                MarketEventTranslationMap.event_id == mapping.event_id,
                MarketEventTranslationMap.field_name == mapping.field_name,
                MarketEventTranslationMap.provider == mapping.provider,
                MarketEventTranslationMap.target_language == mapping.target_language,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(mapping)
            await self.session.flush()
            return mapping
        existing.source_language = mapping.source_language
        existing.normalized_text_hash = mapping.normalized_text_hash
        existing.status = mapping.status
        existing.translated_text = mapping.translated_text
        existing.error_message = mapping.error_message
        await self.session.flush()
        return existing

    async def list_market_event_translation_maps(
        self,
        event_id: str,
        *,
        provider: str | None = None,
        target_language: str | None = None,
    ) -> list[MarketEventTranslationMap]:
        stmt = select(MarketEventTranslationMap).where(
            MarketEventTranslationMap.event_id == event_id
        )
        if provider is not None:
            stmt = stmt.where(MarketEventTranslationMap.provider == provider)
        if target_language is not None:
            stmt = stmt.where(MarketEventTranslationMap.target_language == target_language)
        result = await self.session.execute(stmt.order_by(MarketEventTranslationMap.field_name))
        return list(result.scalars().all())

    async def add_market_event_links(self, links: list[MarketEventInstrument]) -> None:
        if not links:
            return
        event_id = links[0].event_id
        existing_result = await self.session.execute(
            select(MarketEventInstrument.instrument_id).where(
                MarketEventInstrument.event_id == event_id
            )
        )
        existing_ids = {row[0] for row in existing_result.all()}
        pending = [link for link in links if link.instrument_id not in existing_ids]
        if not pending:
            return
        self.session.add_all(pending)
        await self.session.flush()

    async def get_market_event(self, event_id: str) -> MarketEvent | None:
        return await self.session.get(MarketEvent, event_id)

    async def list_market_events(
        self,
        limit: int = 50,
        category: str | None = None,
        instrument_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[MarketEvent]:
        stmt = select(MarketEvent)
        if instrument_id is not None:
            stmt = stmt.join(
                MarketEventInstrument, MarketEventInstrument.event_id == MarketEvent.event_id
            ).where(MarketEventInstrument.instrument_id == instrument_id)
        if category is not None:
            stmt = stmt.where(MarketEvent.category == category)
        if from_ts is not None:
            stmt = stmt.where(MarketEvent.ts_event >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(MarketEvent.ts_event <= to_ts)
        fetch_limit = max(limit * 4, limit)
        result = await self.session.execute(
            stmt.order_by(desc(MarketEvent.ts_event)).limit(fetch_limit)
        )
        items = list(result.scalars().all())
        deduped: list[MarketEvent] = []
        seen: set[tuple[str, str, str]] = set()
        for item in items:
            key = self._market_event_dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    async def list_recent_market_events(self, limit: int = 100) -> list[MarketEvent]:
        result = await self.session.execute(
            select(MarketEvent).order_by(desc(MarketEvent.ts_event)).limit(limit)
        )
        return list(result.scalars().all())

    async def list_market_event_instrument_ids(self, event_ids: list[str]) -> dict[str, list[str]]:
        if not event_ids:
            return {}
        result = await self.session.execute(
            select(MarketEventInstrument).where(MarketEventInstrument.event_id.in_(event_ids))
        )
        mapping: dict[str, list[str]] = {}
        for link in result.scalars().all():
            mapping.setdefault(link.event_id, []).append(link.instrument_id)
        return mapping

    async def upsert_indicator_definition(
        self, definition: IndicatorDefinition
    ) -> IndicatorDefinition:
        existing = await self.session.get(IndicatorDefinition, definition.indicator_key)
        if existing is None:
            self.session.add(definition)
            await self.session.flush()
            return definition
        existing.display_name = definition.display_name
        existing.category = definition.category
        existing.family = definition.family
        existing.source_provider = definition.source_provider
        existing.source_kind = definition.source_kind
        existing.calc_engine = definition.calc_engine
        existing.calc_params_json = definition.calc_params_json
        existing.supported_assets_json = definition.supported_assets_json
        existing.supported_timeframes_json = definition.supported_timeframes_json
        existing.output_fields_json = definition.output_fields_json
        existing.signal_states_json = definition.signal_states_json
        existing.default_thresholds_json = definition.default_thresholds_json
        existing.use_cases_json = definition.use_cases_json
        existing.is_enabled = definition.is_enabled
        await self.session.flush()
        return existing

    async def list_indicator_definitions(
        self,
        category: str | None = None,
        family: str | None = None,
        source_provider: str | None = None,
        enabled_only: bool = False,
    ) -> list[IndicatorDefinition]:
        stmt = select(IndicatorDefinition)
        if category:
            stmt = stmt.where(IndicatorDefinition.category == category)
        if family:
            stmt = stmt.where(IndicatorDefinition.family == family)
        if source_provider:
            stmt = stmt.where(IndicatorDefinition.source_provider == source_provider)
        if enabled_only:
            stmt = stmt.where(IndicatorDefinition.is_enabled.is_(True))
        stmt = stmt.order_by(
            IndicatorDefinition.category,
            IndicatorDefinition.family,
            IndicatorDefinition.indicator_key,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_indicator_definition(self, indicator_key: str) -> IndicatorDefinition | None:
        return await self.session.get(IndicatorDefinition, indicator_key)

    async def upsert_monitoring_policy(
        self, policy: IndicatorMonitoringPolicy
    ) -> IndicatorMonitoringPolicy:
        result = await self.session.execute(
            select(IndicatorMonitoringPolicy).where(
                IndicatorMonitoringPolicy.indicator_key == policy.indicator_key,
                IndicatorMonitoringPolicy.scope_type == policy.scope_type,
                IndicatorMonitoringPolicy.instrument_id == policy.instrument_id,
                IndicatorMonitoringPolicy.asset_code == policy.asset_code,
                IndicatorMonitoringPolicy.timeframe == policy.timeframe,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(policy)
            await self.session.flush()
            return policy
        existing.mode = policy.mode
        existing.interval_seconds = policy.interval_seconds
        existing.cron_expr = policy.cron_expr
        existing.timezone = policy.timezone
        existing.event_key = policy.event_key
        existing.calendar_source = policy.calendar_source
        existing.release_key = policy.release_key
        existing.fallback_interval_seconds = policy.fallback_interval_seconds
        existing.priority = policy.priority
        existing.is_enabled = policy.is_enabled
        if policy.next_run_at is not None:
            existing.next_run_at = policy.next_run_at
        await self.session.flush()
        return existing

    async def list_monitoring_policies(
        self,
        enabled_only: bool = False,
        due_only: bool = False,
        instrument_id: str | None = None,
        category: str | None = None,
        event_key: str | None = None,
        as_of: datetime | None = None,
    ) -> list[IndicatorMonitoringPolicy]:
        stmt = select(IndicatorMonitoringPolicy)
        if enabled_only:
            stmt = stmt.where(IndicatorMonitoringPolicy.is_enabled.is_(True))
        if due_only and as_of is not None:
            stmt = stmt.where(
                or_(
                    IndicatorMonitoringPolicy.next_run_at.is_(None),
                    IndicatorMonitoringPolicy.next_run_at <= as_of,
                )
            )
        if instrument_id:
            stmt = stmt.where(
                or_(
                    IndicatorMonitoringPolicy.instrument_id == instrument_id,
                    IndicatorMonitoringPolicy.instrument_id.is_(None),
                )
            )
        if event_key:
            stmt = stmt.where(IndicatorMonitoringPolicy.event_key == event_key)
        stmt = stmt.order_by(
            IndicatorMonitoringPolicy.priority, IndicatorMonitoringPolicy.indicator_key
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        if category is None:
            return items
        definitions = {
            item.indicator_key: item
            for item in await self.list_indicator_definitions(category=category)
        }
        return [item for item in items if item.indicator_key in definitions]

    async def update_monitoring_policy_schedule(
        self,
        policy_id: str,
        *,
        last_run_at: datetime | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        policy = await self.session.get(IndicatorMonitoringPolicy, policy_id)
        if policy is None:
            return
        policy.last_run_at = last_run_at
        policy.next_run_at = next_run_at
        await self.session.flush()

    async def add_or_update_observation(
        self, observation: IndicatorObservation
    ) -> IndicatorObservation:
        result = await self.session.execute(
            select(IndicatorObservation).where(
                IndicatorObservation.dedupe_key == observation.dedupe_key
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(observation)
            await self.session.flush()
            return observation
        existing.value_num = observation.value_num
        existing.value_text = observation.value_text
        existing.value_json = observation.value_json
        existing.baseline_num = observation.baseline_num
        existing.delta_num = observation.delta_num
        existing.zscore_num = observation.zscore_num
        existing.percentile_num = observation.percentile_num
        existing.signal_state = observation.signal_state
        existing.signal_score = observation.signal_score
        existing.source_provider = observation.source_provider
        existing.source_ref = observation.source_ref
        existing.source_granularity = observation.source_granularity
        existing.is_preliminary = observation.is_preliminary
        existing.quality_score = observation.quality_score
        existing.run_id = observation.run_id
        existing.effective_start_ts = observation.effective_start_ts
        existing.effective_end_ts = observation.effective_end_ts
        await self.session.flush()
        return existing

    async def list_indicator_observations(
        self,
        indicator_key: str | None = None,
        instrument_id: str | None = None,
        asset_code: str | None = None,
        timeframe: str | None = None,
        category: str | None = None,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
        limit: int = 100,
    ) -> list[IndicatorObservation]:
        stmt = select(IndicatorObservation)
        if indicator_key:
            stmt = stmt.where(IndicatorObservation.indicator_key == indicator_key)
        if instrument_id:
            stmt = stmt.where(IndicatorObservation.instrument_id == instrument_id)
        if asset_code:
            stmt = stmt.where(IndicatorObservation.asset_code == asset_code)
        if timeframe:
            stmt = stmt.where(IndicatorObservation.timeframe == timeframe)
        if category:
            stmt = stmt.where(IndicatorObservation.category == category)
        if start_ts:
            stmt = stmt.where(IndicatorObservation.observation_ts >= start_ts)
        if end_ts:
            stmt = stmt.where(IndicatorObservation.observation_ts <= end_ts)
        stmt = stmt.order_by(desc(IndicatorObservation.observation_ts)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_observation(
        self,
        indicator_key: str,
        instrument_id: str | None = None,
        asset_code: str | None = None,
        timeframe: str | None = None,
    ) -> IndicatorObservation | None:
        stmt = select(IndicatorObservation).where(
            IndicatorObservation.indicator_key == indicator_key
        )
        if instrument_id is not None:
            stmt = stmt.where(IndicatorObservation.instrument_id == instrument_id)
        if asset_code is not None:
            stmt = stmt.where(IndicatorObservation.asset_code == asset_code)
        if timeframe is not None:
            stmt = stmt.where(IndicatorObservation.timeframe == timeframe)
        stmt = stmt.order_by(desc(IndicatorObservation.observation_ts)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_alert_rule(self, rule: IndicatorAlertRule) -> IndicatorAlertRule:
        existing = await self.session.get(IndicatorAlertRule, rule.rule_key)
        if existing is None:
            self.session.add(rule)
            await self.session.flush()
            return rule
        existing.indicator_key = rule.indicator_key
        existing.enabled = rule.enabled
        existing.severity = rule.severity
        existing.category = rule.category
        existing.scope_type = rule.scope_type
        existing.condition_type = rule.condition_type
        existing.comparator = rule.comparator
        existing.threshold_num = rule.threshold_num
        existing.lower_threshold_num = rule.lower_threshold_num
        existing.upper_threshold_num = rule.upper_threshold_num
        existing.state_value = rule.state_value
        existing.percentile_ref_window_points = rule.percentile_ref_window_points
        existing.consecutive_points = rule.consecutive_points
        existing.dedupe_window_seconds = rule.dedupe_window_seconds
        existing.cooldown_seconds = rule.cooldown_seconds
        existing.action_channels_json = rule.action_channels_json
        existing.message_template = rule.message_template
        existing.extra_config_json = rule.extra_config_json
        await self.session.flush()
        return existing

    async def list_alert_rules(
        self,
        enabled_only: bool = False,
        category: str | None = None,
        indicator_key: str | None = None,
    ) -> list[IndicatorAlertRule]:
        stmt = select(IndicatorAlertRule)
        if enabled_only:
            stmt = stmt.where(IndicatorAlertRule.enabled.is_(True))
        if category:
            stmt = stmt.where(IndicatorAlertRule.category == category)
        if indicator_key:
            stmt = stmt.where(IndicatorAlertRule.indicator_key == indicator_key)
        stmt = stmt.order_by(IndicatorAlertRule.category, IndicatorAlertRule.rule_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_alert_event(self, event: IndicatorAlertEvent) -> IndicatorAlertEvent:
        result = await self.session.execute(
            select(IndicatorAlertEvent).where(IndicatorAlertEvent.dedupe_key == event.dedupe_key)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_alert_events(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[IndicatorAlertEvent]:
        stmt = select(IndicatorAlertEvent)
        if status:
            stmt = stmt.where(IndicatorAlertEvent.status == status)
        if severity:
            stmt = stmt.where(IndicatorAlertEvent.severity == severity)
        if category:
            rules = [rule.rule_key for rule in await self.list_alert_rules(category=category)]
            if not rules:
                return []
            stmt = stmt.where(IndicatorAlertEvent.rule_key.in_(rules))
        stmt = stmt.order_by(desc(IndicatorAlertEvent.triggered_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_alert_event_status(
        self, alert_event_id: str, status: str
    ) -> IndicatorAlertEvent | None:
        event = await self.session.get(IndicatorAlertEvent, alert_event_id)
        if event is None:
            return None
        event.status = status
        event.resolved_at = (
            datetime.now(timezone.utc) if status in {"resolved", "suppressed"} else None
        )
        await self.session.flush()
        return event

    async def upsert_macro_event(self, event: MacroEventCalendar) -> MacroEventCalendar:
        result = await self.session.execute(
            select(MacroEventCalendar).where(
                MacroEventCalendar.provider_key == event.provider_key,
                MacroEventCalendar.event_key == event.event_key,
                MacroEventCalendar.scheduled_at == event.scheduled_at,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(event)
            await self.session.flush()
            return event
        existing.title = event.title
        existing.country_code = event.country_code
        existing.actual_value_num = event.actual_value_num
        existing.consensus_value_num = event.consensus_value_num
        existing.previous_value_num = event.previous_value_num
        existing.surprise_num = event.surprise_num
        existing.importance = event.importance
        existing.status = event.status
        existing.source_ref = event.source_ref
        existing.payload_json = event.payload_json
        await self.session.flush()
        return existing

    async def list_macro_events(
        self,
        event_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MacroEventCalendar]:
        stmt = select(MacroEventCalendar)
        if event_key:
            stmt = stmt.where(MacroEventCalendar.event_key == event_key)
        if status:
            stmt = stmt.where(MacroEventCalendar.status == status)
        stmt = stmt.order_by(desc(MacroEventCalendar.scheduled_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_macro_event(
        self, event_key: str, released_only: bool = False
    ) -> MacroEventCalendar | None:
        stmt = select(MacroEventCalendar).where(MacroEventCalendar.event_key == event_key)
        if released_only:
            stmt = stmt.where(MacroEventCalendar.status == "released")
        stmt = stmt.order_by(desc(MacroEventCalendar.scheduled_at)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_macro_source_health(self, health: MacroSourceHealth) -> MacroSourceHealth:
        result = await self.session.execute(
            select(MacroSourceHealth).where(
                MacroSourceHealth.provider_key == health.provider_key,
                MacroSourceHealth.source_key == health.source_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self.session.add(health)
            await self.session.flush()
            return health
        existing.status = health.status
        existing.message = health.message
        existing.last_success_at = health.last_success_at
        existing.last_failure_at = health.last_failure_at
        existing.latency_ms = health.latency_ms
        existing.payload_json = health.payload_json
        await self.session.flush()
        return existing

    async def list_macro_source_health(
        self, *, provider_key: str | None = None
    ) -> list[MacroSourceHealth]:
        stmt = select(MacroSourceHealth)
        if provider_key is not None:
            stmt = stmt.where(MacroSourceHealth.provider_key == provider_key)
        result = await self.session.execute(
            stmt.order_by(MacroSourceHealth.provider_key, MacroSourceHealth.source_key)
        )
        return list(result.scalars().all())

    async def add_indicator_run(self, run: IndicatorRun) -> IndicatorRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_indicator_run(
        self,
        run_id: str,
        *,
        status: str,
        rows_written: int,
        error_code: str | None = None,
        error_message: str | None = None,
        finished_at: datetime | None = None,
        stats_json: dict | None = None,
    ) -> None:
        run = await self.session.get(IndicatorRun, run_id)
        if run is None:
            return
        run.status = status
        run.rows_written = rows_written
        run.error_code = error_code
        run.error_message = error_message
        run.finished_at = finished_at or datetime.now(timezone.utc)
        if stats_json is not None:
            run.stats_json = stats_json
        await self.session.flush()

    async def get_latest_structure_snapshot(
        self, instrument_id: str, timeframe: str
    ) -> StructureSnapshot | None:
        result = await self.session.execute(
            select(StructureSnapshot)
            .where(
                StructureSnapshot.instrument_id == instrument_id,
                StructureSnapshot.timeframe == timeframe,
                StructureSnapshot.is_latest.is_(True),
            )
            .order_by(desc(StructureSnapshot.generated_at))
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is not None:
            return snapshot
        result = await self.session.execute(
            select(StructureSnapshot)
            .where(
                StructureSnapshot.instrument_id == instrument_id,
                StructureSnapshot.timeframe == timeframe,
            )
            .order_by(desc(StructureSnapshot.generated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def replace_structure_snapshot_bundle(
        self,
        snapshot: StructureSnapshot,
        judgements: list[StructureSystemJudgement],
        system_scores: list[StructureSystemScore],
        active_items: list[StructureActiveItem],
        geometries: list[StructureGeometry],
        events: list[StructureEvent],
        alerts: list[StructureAlert],
    ) -> StructureSnapshot:
        await self.session.execute(
            delete(StructureSnapshot).where(
                StructureSnapshot.instrument_id == snapshot.instrument_id,
                StructureSnapshot.timeframe == snapshot.timeframe,
                StructureSnapshot.snapshot_version == snapshot.snapshot_version,
            )
        )
        await self.session.execute(
            delete(StructureSystemJudgement).where(
                StructureSystemJudgement.instrument_id == snapshot.instrument_id,
                StructureSystemJudgement.timeframe == snapshot.timeframe,
                StructureSystemJudgement.snapshot_version == snapshot.snapshot_version,
            )
        )
        await self.session.execute(
            delete(StructureActiveItem).where(
                StructureActiveItem.instrument_id == snapshot.instrument_id,
                StructureActiveItem.timeframe == snapshot.timeframe,
                StructureActiveItem.snapshot_version == snapshot.snapshot_version,
            )
        )
        await self.session.execute(
            delete(StructureGeometry).where(
                StructureGeometry.instrument_id == snapshot.instrument_id,
                StructureGeometry.timeframe == snapshot.timeframe,
                StructureGeometry.snapshot_version == snapshot.snapshot_version,
            )
        )
        await self.session.execute(
            delete(StructureSystemScore).where(
                StructureSystemScore.instrument_id == snapshot.instrument_id,
                StructureSystemScore.timeframe == snapshot.timeframe,
                StructureSystemScore.snapshot_version == snapshot.snapshot_version,
            )
        )

        await self.session.execute(
            delete(StructureSnapshot).where(
                StructureSnapshot.instrument_id == snapshot.instrument_id,
                StructureSnapshot.timeframe == snapshot.timeframe,
                StructureSnapshot.is_latest.is_(True),
            )
        )

        snapshot.is_latest = True
        self.session.add(snapshot)
        if judgements:
            self.session.add_all(judgements)
        if system_scores:
            self.session.add_all(system_scores)
        if active_items:
            self.session.add_all(active_items)
        if geometries:
            self.session.add_all(geometries)
        await self.session.flush()

        for event in events:
            await self.add_structure_event(event)
        for alert in alerts:
            await self.add_structure_alert(alert)
        await self.session.flush()
        return snapshot

    async def list_structure_system_judgements(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot_version: str,
    ) -> list[StructureSystemJudgement]:
        result = await self.session.execute(
            select(StructureSystemJudgement)
            .where(
                StructureSystemJudgement.instrument_id == instrument_id,
                StructureSystemJudgement.timeframe == timeframe,
                StructureSystemJudgement.snapshot_version == snapshot_version,
            )
            .order_by(StructureSystemJudgement.system)
        )
        return list(result.scalars().all())

    async def list_structure_system_scores(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot_version: str,
    ) -> list[StructureSystemScore]:
        result = await self.session.execute(
            select(StructureSystemScore)
            .where(
                StructureSystemScore.instrument_id == instrument_id,
                StructureSystemScore.timeframe == timeframe,
                StructureSystemScore.snapshot_version == snapshot_version,
            )
            .order_by(StructureSystemScore.system)
        )
        return list(result.scalars().all())

    async def list_structure_active_items(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot_version: str,
        *,
        active_only: bool = False,
    ) -> list[StructureActiveItem]:
        stmt = select(StructureActiveItem).where(
            StructureActiveItem.instrument_id == instrument_id,
            StructureActiveItem.timeframe == timeframe,
            StructureActiveItem.snapshot_version == snapshot_version,
        )
        if active_only:
            stmt = stmt.where(StructureActiveItem.is_active.is_(True))
        stmt = stmt.order_by(desc(StructureActiveItem.event_ts))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_structure_geometry(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot_version: str,
    ) -> list[StructureGeometry]:
        result = await self.session.execute(
            select(StructureGeometry)
            .where(
                StructureGeometry.instrument_id == instrument_id,
                StructureGeometry.timeframe == timeframe,
                StructureGeometry.snapshot_version == snapshot_version,
            )
            .order_by(StructureGeometry.system, StructureGeometry.kind)
        )
        return list(result.scalars().all())

    async def add_structure_event(self, event: StructureEvent) -> StructureEvent:
        result = await self.session.execute(
            select(StructureEvent).where(StructureEvent.dedupe_key == event.dedupe_key)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.bias = event.bias
            existing.status = event.status
            existing.confidence = event.confidence
            existing.anchor_bar_ts = event.anchor_bar_ts
            existing.confirmation_bar_ts = event.confirmation_bar_ts
            existing.event_ts = event.event_ts
            existing.detection_ts = event.detection_ts
            existing.payload_json = event.payload_json
            existing.structure_id = event.structure_id
            await self.session.flush()
            return existing
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_structure_events(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        limit: int = 100,
    ) -> list[StructureEvent]:
        result = await self.session.execute(
            select(StructureEvent)
            .where(
                StructureEvent.instrument_id == instrument_id,
                StructureEvent.timeframe == timeframe,
            )
            .order_by(desc(StructureEvent.event_ts))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_structure_alert(self, alert: StructureAlert) -> StructureAlert:
        result = await self.session.execute(
            select(StructureAlert).where(StructureAlert.dedupe_key == alert.dedupe_key)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.status = alert.status
            existing.title = alert.title
            existing.message = alert.message
            existing.triggered_at = alert.triggered_at
            existing.resolved_at = alert.resolved_at
            existing.event_payload_json = alert.event_payload_json
            await self.session.flush()
            return existing
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def list_structure_alerts(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        limit: int = 100,
    ) -> list[StructureAlert]:
        result = await self.session.execute(
            select(StructureAlert)
            .where(
                StructureAlert.instrument_id == instrument_id,
                StructureAlert.timeframe == timeframe,
            )
            .order_by(desc(StructureAlert.triggered_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_signal_outcome(self, outcome: SignalOutcome) -> SignalOutcome:
        result = await self.session.execute(
            select(SignalOutcome).where(
                SignalOutcome.signal_type == outcome.signal_type,
                SignalOutcome.signal_ref == outcome.signal_ref,
                SignalOutcome.timeframe == outcome.timeframe,
                SignalOutcome.signal_ts == outcome.signal_ts,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.instrument_id = outcome.instrument_id
            existing.entry_ref_price = outcome.entry_ref_price
            existing.bars_1 = outcome.bars_1
            existing.bars_3 = outcome.bars_3
            existing.bars_6 = outcome.bars_6
            existing.bars_12 = outcome.bars_12
            existing.bars_24 = outcome.bars_24
            existing.return_1 = outcome.return_1
            existing.return_3 = outcome.return_3
            existing.return_6 = outcome.return_6
            existing.return_12 = outcome.return_12
            existing.return_24 = outcome.return_24
            existing.mfe = outcome.mfe
            existing.mae = outcome.mae
            existing.stop_hit_first = outcome.stop_hit_first
            existing.take_profit_hit_first = outcome.take_profit_hit_first
            existing.payload_json = outcome.payload_json
            await self.session.flush()
            return existing
        self.session.add(outcome)
        await self.session.flush()
        return outcome

    async def list_signal_outcomes(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        signal_type: str | None = None,
        limit: int = 100,
    ) -> list[SignalOutcome]:
        stmt = select(SignalOutcome)
        if instrument_id is not None:
            stmt = stmt.where(SignalOutcome.instrument_id == instrument_id)
        if timeframe is not None:
            stmt = stmt.where(SignalOutcome.timeframe == timeframe)
        if signal_type is not None:
            stmt = stmt.where(SignalOutcome.signal_type == signal_type)
        stmt = stmt.order_by(desc(SignalOutcome.signal_ts)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_strategy_decision(self, decision: StrategyDecision) -> StrategyDecision:
        self.session.add(decision)
        await self.session.flush()
        return decision

    async def get_strategy_decision(self, decision_id: str) -> StrategyDecision | None:
        result = await self.session.execute(
            select(StrategyDecision).where(StrategyDecision.decision_id == decision_id)
        )
        return result.scalar_one_or_none()

    async def list_strategy_decisions(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        limit: int = 100,
    ) -> list[StrategyDecision]:
        stmt = select(StrategyDecision)
        if instrument_id is not None:
            stmt = stmt.where(StrategyDecision.instrument_id == instrument_id)
        if timeframe is not None:
            stmt = stmt.where(StrategyDecision.timeframe == timeframe)
        stmt = stmt.order_by(desc(StrategyDecision.decision_ts)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_strategy_decision_outcome(
        self, outcome: StrategyDecisionOutcome
    ) -> StrategyDecisionOutcome:
        self.session.add(outcome)
        await self.session.flush()
        return outcome

    async def list_strategy_decision_outcomes(
        self,
        *,
        decision_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[StrategyDecisionOutcome]:
        stmt = select(StrategyDecisionOutcome)
        if decision_ids:
            stmt = stmt.where(StrategyDecisionOutcome.decision_id.in_(decision_ids))
        stmt = stmt.order_by(desc(StrategyDecisionOutcome.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_strategy_iteration_proposal(
        self, proposal: StrategyIterationProposal
    ) -> StrategyIterationProposal:
        result = await self.session.execute(
            select(StrategyIterationProposal).where(
                StrategyIterationProposal.proposal_id == proposal.proposal_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.instrument_id = proposal.instrument_id
            existing.timeframe = proposal.timeframe
            existing.proposal_type = proposal.proposal_type
            existing.target_module = proposal.target_module
            existing.priority = proposal.priority
            existing.evidence_count = proposal.evidence_count
            existing.reason = proposal.reason
            existing.suggested_change_json = proposal.suggested_change_json
            existing.status = proposal.status
            existing.updated_at = proposal.updated_at
            await self.session.flush()
            return existing
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def list_strategy_iteration_proposals(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        status: str | None = "open",
        limit: int = 50,
    ) -> list[StrategyIterationProposal]:
        stmt = select(StrategyIterationProposal)
        if instrument_id is not None:
            stmt = stmt.where(
                or_(
                    StrategyIterationProposal.instrument_id == instrument_id,
                    StrategyIterationProposal.instrument_id.is_(None),
                )
            )
        if timeframe is not None:
            stmt = stmt.where(
                or_(
                    StrategyIterationProposal.timeframe == timeframe,
                    StrategyIterationProposal.timeframe.is_(None),
                )
            )
        if status is not None:
            stmt = stmt.where(StrategyIterationProposal.status == status)
        stmt = stmt.order_by(desc(StrategyIterationProposal.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
