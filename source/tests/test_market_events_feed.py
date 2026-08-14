from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from xml.etree import ElementTree

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.instrument import Instrument
from app.db.models.market import MarketEvent
from app.repositories.market_repository import MarketRepository
from app.services.market_event_sources import MarketEventSource, load_market_event_sources
from app.services.market_events_feed import FeedEntry, MarketEventFeedService


class DummyRepo:
    def __init__(self) -> None:
        self.events = []
        self.links = []
        self._instruments = [
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
            ),
            Instrument(
                instrument_id="eth-usdt-perp",
                venue="GATEIO",
                symbol="ETH_USDT",
                asset_class="PERP",
                base_ccy="ETH",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={},
            ),
        ]

    async def list_instruments(self):
        return self._instruments

    async def add_market_event(self, event):
        self.events.append(event)
        return event

    async def add_market_event_links(self, links):
        self.links.extend(links)


async def test_match_instruments_from_keywords() -> None:
    repo = DummyRepo()
    service = MarketEventFeedService(repo)
    entry = FeedEntry(
        title="Bitcoin and Ethereum rally after ETF optimism",
        summary="BTC leads while Ethereum follows.",
        link="https://example.test/story",
        published_at=datetime(2026, 4, 5, tzinfo=UTC),
        source="Cointelegraph",
        source_id="crypto.cointelegraph.markets",
        category="news",
        reliability="high",
        importance="high",
        tags=["markets"],
    )
    matched = service._match_instruments(entry, await repo.list_instruments())
    assert matched == ["btc-usdt-perp", "eth-usdt-perp"]


def test_event_id_is_stable() -> None:
    entry = FeedEntry(
        title="BTC market update",
        summary="Summary",
        link="https://example.test/story",
        published_at=datetime(2026, 4, 5, tzinfo=UTC),
        source="Decrypt",
        source_id="crypto.decrypt.feed",
        category="news",
        reliability="high",
        importance="medium",
        tags=["retail"],
    )
    first = MarketEventFeedService._event_id(entry)
    second = MarketEventFeedService._event_id(entry)
    assert first == second


def test_event_id_ignores_source_identity() -> None:
    published_at = datetime(2026, 4, 5, tzinfo=UTC)
    first = FeedEntry(
        title="BTC market update",
        summary="Summary",
        link="https://example.test/story",
        published_at=published_at,
        source="Cointelegraph",
        source_id="crypto.cointelegraph.markets",
        category="news",
        reliability="high",
        importance="medium",
        tags=["retail"],
    )
    second = FeedEntry(
        title="BTC market update",
        summary="Summary",
        link="https://example.test/story",
        published_at=published_at,
        source="Cointelegraph Markets",
        source_id="crypto.cointelegraph.rss",
        category="news",
        reliability="high",
        importance="medium",
        tags=["retail"],
    )
    assert MarketEventFeedService._event_id(first) == MarketEventFeedService._event_id(second)


def test_clean_html_unescapes_entities() -> None:
    raw = "<p>Bitcoin &amp; Ethereum rally on ETF&nbsp;hopes</p>"
    assert MarketEventFeedService._clean_html(raw) == "Bitcoin & Ethereum rally on ETF hopes"


def test_load_source_catalog_includes_panews() -> None:
    source_ids = {item.source_id for item in load_market_event_sources()}
    assert "crypto.panews.rss" in source_ids


def test_parse_atom_feed_supports_updated_and_link() -> None:
    service = MarketEventFeedService(DummyRepo())
    source = MarketEventSource(
        source_id="crypto.atom.sample",
        provider_name="Atom Sample",
        entry_url="https://example.test/feed",
        category="news",
        access_mode="atom",
        reliability="medium",
    )
    root = ElementTree.fromstring(
        """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>SEC reviews ETH ETF filing</title>
            <updated>2026-04-05T05:00:00+00:00</updated>
            <summary>ETF review moves into another stage.</summary>
            <link href="https://example.test/eth-etf" />
          </entry>
        </feed>
        """
    )
    entries = service._parse_atom_feed(root, source)
    assert len(entries) == 1
    assert entries[0].link == "https://example.test/eth-etf"
    assert entries[0].category == "macro"


def test_parse_panews_html_feed_fallback() -> None:
    service = MarketEventFeedService(DummyRepo())
    source = MarketEventSource(
        source_id="crypto.panews.rss",
        provider_name="PANews",
        entry_url="https://www.panewslab.com/zh/rss",
        category="newsflash",
        access_mode="rss",
        reliability="medium",
    )
    html = """
    <html>
      <body>
        <script id="__NUXT_DATA__" type="application/json">
        [
          {"slug":1,"title":2,"desc":3,"createdAt":4},
          "btc-breakout",
          "BTC breakout confirmed",
          "Momentum expands",
          "2026-04-10T08:57:19.686Z"
        ]
        </script>
      </body>
    </html>
    """
    entries = service._parse_html_feed(html, source)
    assert len(entries) == 1
    assert entries[0].title == "BTC breakout confirmed"
    assert entries[0].link == "https://www.panewslab.com/zh/articles/btc-breakout"


async def test_fetch_feed_uses_panews_html_fallback_on_parse_error() -> None:
    service = MarketEventFeedService(DummyRepo())
    source = MarketEventSource(
        source_id="crypto.panews.rss",
        provider_name="PANews",
        entry_url="https://www.panewslab.com/zh/rss",
        category="newsflash",
        access_mode="rss",
        reliability="medium",
    )
    html = """
    <html>
      <body>
        <script id="__NUXT_DATA__" type="application/json">
        [
          {"slug":1,"title":2,"desc":3,"createdAt":4},
          "btc-breakout",
          "BTC breakout confirmed",
          "Momentum expands",
          "2026-04-10T08:57:19.686Z"
        ]
        </script>
      </body>
    </html>
    """

    class DummyResponse:
        text = html
        headers = {"content-type": "application/xml"}

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def get(self, url: str):
            return DummyResponse()

    entries = await service._fetch_feed(DummyClient(), source)

    assert len(entries) == 1
    assert entries[0].title == "BTC breakout confirmed"


async def test_market_repository_dedupes_existing_duplicate_market_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ts_event = datetime(2026, 4, 5, 0, 0, tzinfo=UTC)
    payload = {"link": "https://example.test/story"}

    async with session_factory() as session:
        session.add_all(
            [
                MarketEvent(
                    event_id="feed-old-1",
                    category="news",
                    title="BTC market update",
                    summary="Summary",
                    source="Cointelegraph",
                    reliability="high",
                    ts_event=ts_event,
                    payload_json=payload,
                ),
                MarketEvent(
                    event_id="feed-old-2",
                    category="news",
                    title="BTC market update",
                    summary="Summary",
                    source="Cointelegraph Markets",
                    reliability="high",
                    ts_event=ts_event,
                    payload_json=payload,
                ),
                MarketEvent(
                    event_id="feed-other",
                    category="macro",
                    title="ETH market update",
                    summary="Another summary",
                    source="Decrypt",
                    reliability="high",
                    ts_event=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
                    payload_json={"link": "https://example.test/other"},
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        repo = MarketRepository(session)
        events = await repo.list_market_events(limit=10)
        assert len(events) == 2
        assert events[0].title == "BTC market update"
        assert events[0].event_id in {"feed-old-1", "feed-old-2"}
        assert events[1].event_id == "feed-other"

    await engine.dispose()


async def test_add_market_event_reuses_existing_matching_event() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ts_event = datetime(2026, 4, 5, 0, 0, tzinfo=UTC)

    async with session_factory() as session:
        repo = MarketRepository(session)
        await repo.add_market_event(
            MarketEvent(
                event_id="feed-old-1",
                category="news",
                title="BTC market update",
                summary="Summary",
                source="Cointelegraph",
                reliability="high",
                ts_event=ts_event,
                payload_json={"link": "https://example.test/story"},
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = MarketRepository(session)
        saved = await repo.add_market_event(
            MarketEvent(
                event_id="feed-new-2",
                category="news",
                title="BTC market update",
                summary="Summary",
                source="Cointelegraph Markets",
                reliability="high",
                ts_event=ts_event,
                payload_json={"link": "https://example.test/story"},
            )
        )
        await session.commit()

        count = await session.scalar(select(func.count()).select_from(MarketEvent))
        assert saved.event_id == "feed-old-1"
        assert count == 1

    await engine.dispose()
