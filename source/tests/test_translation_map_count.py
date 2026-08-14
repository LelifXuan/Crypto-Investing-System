from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.market import MarketEvent, MarketEventTranslationMap
from app.repositories.market_repository import MarketRepository


async def _make_session() -> tuple[AsyncSession, async_sessionmaker, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_factory(), session_factory, engine


async def _seed_event(session: AsyncSession, event_id: str) -> None:
    session.add(
        MarketEvent(
            event_id=event_id,
            category="news",
            title="Bitcoin ETF inflows and Ethereum futures funding",
            summary="summary",
            source="test",
            reliability="high",
            ts_event=datetime(2026, 4, 5, 0, 0, tzinfo=UTC),
            payload_json={},
        )
    )
    await session.commit()


def _make_map(
    event_id: str,
    field_name: str,
    status: str,
    target_language: str = "zh-CN",
    provider: str = "tencent_tmt",
) -> MarketEventTranslationMap:
    return MarketEventTranslationMap(
        event_id=event_id,
        field_name=field_name,
        provider=provider,
        source_language="en",
        target_language=target_language,
        normalized_text_hash=f"hash-{event_id}-{field_name}-{status}",
        status=status,
        translated_text="translated" if status == "translated" else None,
        error_message="boom" if status == "error" else None,
    )


async def test_count_groups_by_status() -> None:
    session, _, engine = await _make_session()
    try:
        await _seed_event(session, "evt-1")
        repo = MarketRepository(session)
        # Use distinct (event_id, field_name) pairs to satisfy the unique
        # constraint on (event_id, field_name, provider, target_language).
        maps = [
            _make_map("evt-1", "title", "translated"),
            _make_map("evt-1", "summary", "translated"),
            _make_map("evt-1", "tagline", "pending"),
            _make_map("evt-1", "body", "error"),
        ]
        for m in maps:
            await repo.upsert_market_event_translation_map(m)
        await session.commit()

        counts = await repo.count_market_event_translation_maps_by_status()

        assert counts["translated"] == 2
        assert counts["pending"] == 1
        assert counts["error"] == 1
        assert counts["total"] == 4
    finally:
        await engine.dispose()


async def test_count_filters_by_target_language() -> None:
    session, _, engine = await _make_session()
    try:
        await _seed_event(session, "evt-1")
        repo = MarketRepository(session)
        await repo.upsert_market_event_translation_map(
            _make_map("evt-1", "title", "translated", target_language="zh-CN")
        )
        await repo.upsert_market_event_translation_map(
            _make_map("evt-1", "title", "translated", target_language="en-US")
        )
        await session.commit()

        zh_counts = await repo.count_market_event_translation_maps_by_status(
            target_language="zh-CN"
        )
        en_counts = await repo.count_market_event_translation_maps_by_status(
            target_language="en-US"
        )

        assert zh_counts["translated"] == 1
        assert zh_counts["total"] == 1
        assert en_counts["translated"] == 1
        assert en_counts["total"] == 1
    finally:
        await engine.dispose()


async def test_count_filters_by_provider() -> None:
    session, _, engine = await _make_session()
    try:
        await _seed_event(session, "evt-1")
        repo = MarketRepository(session)
        await repo.upsert_market_event_translation_map(
            _make_map("evt-1", "title", "translated", provider="tencent_tmt")
        )
        await repo.upsert_market_event_translation_map(
            _make_map("evt-1", "summary", "translated", provider="local_glossary")
        )
        await session.commit()

        tencent = await repo.count_market_event_translation_maps_by_status(
            provider="tencent_tmt"
        )
        local = await repo.count_market_event_translation_maps_by_status(
            provider="local_glossary"
        )

        assert tencent["translated"] == 1
        assert tencent["total"] == 1
        assert local["translated"] == 1
        assert local["total"] == 1
    finally:
        await engine.dispose()


async def test_count_returns_empty_dict_with_total_zero() -> None:
    session, _, engine = await _make_session()
    try:
        repo = MarketRepository(session)
        counts = await repo.count_market_event_translation_maps_by_status()
        assert counts == {"total": 0}
    finally:
        await engine.dispose()
