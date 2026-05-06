from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import desc, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.instrument import Instrument
from app.db.models.market import (
    IndicatorRefreshPolicy,
    IndicatorValue,
    MarketCandle,
    MarketEvent,
    MarketEventInstrument,
    MarkPrice,
)


class MarketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_instrument(self, instrument_id: str) -> Instrument | None:
        return await self.session.get(Instrument, instrument_id)

    async def list_gateio_stream_instruments(self) -> list[Instrument]:
        result = await self.session.execute(
            select(Instrument).where(or_(Instrument.venue.ilike("%gate%"), Instrument.metadata_json.contains({"gateio": {}})))
        )
        return list(result.scalars().all())

    async def add_mark_price(self, mark: MarkPrice) -> MarkPrice:
        self.session.add(mark)
        await self.session.flush()
        return mark

    async def latest_mark(self, instrument_id: str) -> MarkPrice | None:
        result = await self.session.execute(
            select(MarkPrice).where(MarkPrice.instrument_id == instrument_id).order_by(desc(MarkPrice.ts_event)).limit(1)
        )
        return result.scalar_one_or_none()

    async def add_candle(self, candle: MarketCandle) -> MarketCandle:
        self.session.add(candle)
        await self.session.flush()
        return candle

    async def upsert_candles(self, candles: list[MarketCandle]) -> list[MarketCandle]:
        if not candles:
            return []
        keys = [(c.instrument_id, c.timeframe, c.ts_open, c.source) for c in candles]
        existing_stmt = select(MarketCandle).where(
            tuple_(MarketCandle.instrument_id, MarketCandle.timeframe, MarketCandle.ts_open, MarketCandle.source).in_(keys)
        )
        existing_result = await self.session.execute(existing_stmt)
        existing = list(existing_result.scalars().all())
        existing_map = {(c.instrument_id, c.timeframe, c.ts_open, c.source): c for c in existing}
        persisted = list(existing)
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

    async def list_candles(self, instrument_id: str, timeframe: str, limit: int = 200) -> list[MarketCandle]:
        result = await self.session.execute(
            select(MarketCandle)
            .where(MarketCandle.instrument_id == instrument_id, MarketCandle.timeframe == timeframe)
            .order_by(desc(MarketCandle.ts_open))
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def add_indicator_value(self, value: IndicatorValue) -> IndicatorValue:
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

    async def upsert_indicator_refresh_policy(self, policy: IndicatorRefreshPolicy) -> IndicatorRefreshPolicy:
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

    async def add_market_event_links(self, links: list[MarketEventInstrument]) -> None:
        if not links:
            return
        existing_stmt = select(MarketEventInstrument).where(
            tuple_(MarketEventInstrument.event_id, MarketEventInstrument.instrument_id).in_(
                [(link.event_id, link.instrument_id) for link in links]
            )
        )
        existing_rows = await self.session.execute(existing_stmt)
        existing = {(row.event_id, row.instrument_id) for row in existing_rows.scalars().all()}
        for link in links:
            key = (link.event_id, link.instrument_id)
            if key in existing:
                continue
            self.session.add(link)
        await self.session.flush()

    async def list_market_events(self, limit: int = 50) -> list[MarketEvent]:
        result = await self.session.execute(select(MarketEvent).order_by(desc(MarketEvent.ts_event)).limit(limit))
        return list(result.scalars().all())

    async def match_instrument_ids(self, tokens: Sequence[str]) -> list[str]:
        if not tokens:
            return []
        normalized = {token.upper() for token in tokens}
        result = await self.session.execute(select(Instrument))
        matched: list[str] = []
        for instrument in result.scalars().all():
            parts = {
                instrument.instrument_id.upper(),
                instrument.symbol.upper(),
                instrument.base_ccy.upper(),
                instrument.quote_ccy.upper(),
                instrument.settle_ccy.upper(),
            }
            if normalized.intersection(parts):
                matched.append(instrument.instrument_id)
        return matched
