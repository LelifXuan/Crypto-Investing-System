from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.instrument import Instrument
from app.db.models.market import MarketCandle
from app.repositories.market_repository import MarketRepository


async def test_upsert_candles_deduplicates_batch_entries() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ts_open = datetime(2026, 4, 5, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="GATEIO",
                symbol="BTC_USDT",
                asset_class="PERP",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={},
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = MarketRepository(session)
        first = MarketCandle(
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            ts_open=ts_open,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("108"),
            volume=Decimal("1000"),
            source="gateio:test",
        )
        duplicate = MarketCandle(
            instrument_id="btc-usdt-perp",
            timeframe="1d",
            ts_open=ts_open,
            open=Decimal("100"),
            high=Decimal("111"),
            low=Decimal("94"),
            close=Decimal("109"),
            volume=Decimal("1200"),
            source="gateio:test",
        )

        persisted = await repo.upsert_candles([first, duplicate])
        await session.commit()

        assert len(persisted) == 1
        assert persisted[0].close == Decimal("109")

        rows = await session.execute(select(MarketCandle))
        candles = list(rows.scalars().all())
        assert len(candles) == 1
        assert candles[0].high == Decimal("111")

    await engine.dispose()
