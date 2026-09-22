from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.cache.market_cache import market_cache
from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.db.models.market import MarketCandle, MarkPrice
from app.services.market import (
    LIVE_MARK_FALLBACK_MAX_AGE_SECONDS,
    MarketService,
)


class DummyRepo:
    def __init__(self, latest: MarkPrice | None = None) -> None:
        self.latest = latest

    async def latest_mark(self, instrument_id: str) -> MarkPrice | None:
        return self.latest


class DummyGateClient:
    async def get_spot_ticker(self, symbol: str):  # pragma: no cover
        raise RuntimeError("not expected")

    async def get_futures_contract(self, settle: str, symbol: str):
        return {"mark_price": Decimal("68100")}


class DummyRepoWithInstrument(DummyRepo):
    async def get_instrument(self, instrument_id: str):
        from app.db.models.instrument import Instrument

        return Instrument(
            instrument_id=instrument_id,
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
            metadata_json={
                "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
            },
        )

    async def add_mark_price(self, mark: MarkPrice) -> MarkPrice:
        self.latest = mark
        return mark

    async def upsert_candles(self, candles: list[MarketCandle]) -> list[MarketCandle]:
        return candles


class DummyGateClientWithCandles(DummyGateClient):
    def __init__(self) -> None:
        self.calls = 0

    async def get_futures_candles(
        self, settle: str, contract: str, interval: str, limit: int, from_ts=None, to_ts=None
    ):
        self.calls += 1

        class Candle:
            def __init__(self):
                self.ts_open = datetime(2026, 4, 9, tzinfo=timezone.utc)
                self.open = Decimal("100")
                self.high = Decimal("110")
                self.low = Decimal("90")
                self.close = Decimal("105")
                self.volume = Decimal("1000")
                self.source = "gateio:futures.candlesticks"

        return [Candle()]


async def test_get_best_mark_uses_cache_first() -> None:
    await market_cache.clear()
    await market_cache.set_mark(
        "btc-usdt-perp",
        {
            "instrument_id": "btc-usdt-perp",
            "mark_price": "68000.5",
            "last_price": "68000.8",
            "source": "cache:test",
            "ts_event": datetime.now(timezone.utc).isoformat(),
        },
    )
    service = MarketService(DummyRepo())
    mark = await service.get_best_mark("btc-usdt-perp", prefer_live=True)
    assert mark is not None
    assert mark.mark_price == Decimal("68000.5")
    assert mark.source == "cache:test"


async def test_get_best_mark_falls_back_to_db() -> None:
    await market_cache.clear()
    db_mark = MarkPrice(
        mark_id=1,
        instrument_id="btc-usdt-perp",
        mark_price=Decimal("67900"),
        source="db:test",
        ts_event=datetime.now(timezone.utc),
    )
    service = MarketService(DummyRepo(latest=db_mark))
    mark = await service.get_best_mark("eth-usdt-perp", prefer_live=False)
    assert mark is db_mark


async def test_get_best_mark_falls_back_to_rest_when_cache_missing() -> None:
    await market_cache.clear()
    instrument_id = "eth-usdt-perp"
    service = MarketService(DummyRepoWithInstrument(), gate_client=DummyGateClient())
    mark = await service.get_best_mark(instrument_id, prefer_live=True)
    assert mark is not None
    assert mark.mark_price == Decimal("68100")


async def test_get_best_mark_can_read_live_without_persisting() -> None:
    await market_cache.clear()
    repository = DummyRepoWithInstrument()
    service = MarketService(repository, gate_client=DummyGateClient())

    mark = await service.get_best_mark(
        "btc-usdt-perp",
        prefer_live=True,
        persist_live=False,
    )

    assert mark is not None
    assert mark.mark_price == Decimal("68100")
    assert repository.latest is None


async def test_sync_candles_reuses_shared_query_cache() -> None:
    await shared_query_cache.clear()
    repo = DummyRepoWithInstrument()
    gate = DummyGateClientWithCandles()
    service = MarketService(repo, gate_client=gate)

    first = await service.sync_candles_from_provider("btc-usdt-perp", "1d", limit=50, persist=True)
    second = await service.sync_candles_from_provider("btc-usdt-perp", "1d", limit=50, persist=True)

    assert len(first) == 1
    assert len(second) == 1
    assert gate.calls == 1
    await shared_query_cache.clear()


# ---------------------------------------------------------------------------
# 2026-09-22 price-lag bug: WS residue must not out-vote DB LKG forever
# ---------------------------------------------------------------------------


def _price_payload(instrument_id: str, mark_price: str, ts_event: datetime) -> dict:
    return {
        "instrument_id": instrument_id,
        "mark_price": mark_price,
        "last_price": mark_price,
        "source": "cache:test",
        "ts_event": ts_event.isoformat(),
    }


async def test_get_best_mark_evicts_ws_residue_older_than_fallback_budget(
    monkeypatch,
) -> None:
    """A WS residue older than LIVE_MARK_FALLBACK_MAX_AGE_SECONDS must be
    evicted from market_cache and must NOT participate in the LKG merge.

    Pre-fix bug: the residue survived, was wrapped as mark_id=0, and the
    `max(candidates, key=ts_event)` branch returned it whenever it was
    "less old" than the next DB row — even if that meant displaying a
    6-day-old quote as the user's current mark price.
    """
    await market_cache.clear()
    instrument_id = "btc-usdt-perp"
    stale_ts = datetime.now(timezone.utc) - timedelta(
        seconds=LIVE_MARK_FALLBACK_MAX_AGE_SECONDS + 60
    )
    await market_cache.set_mark(instrument_id, _price_payload(instrument_id, "1.23", stale_ts))

    db_mark = MarkPrice(
        mark_id=1,
        instrument_id=instrument_id,
        mark_price=Decimal("67900"),
        source="db:test",
        ts_event=datetime.now(timezone.utc),
    )
    service = MarketService(DummyRepo(latest=db_mark))

    monkeypatch.setattr(settings, "market_stream_prefer_ws_cache", True)
    monkeypatch.setattr(settings, "market_data_provider", "noop")  # skip REST path

    mark = await service.get_best_mark(instrument_id, prefer_live=True)

    assert mark is db_mark  # DB row wins; residue was evicted
    assert await market_cache.get_mark(instrument_id) is None  # cache cleaned
    await market_cache.clear()


async def test_get_best_mark_merges_fresh_cache_with_older_db_row(monkeypatch) -> None:
    """Cache within the fallback budget but older than the fast path should
    be merged with the DB row using ts_event as the tie-breaker. The newer
    of the two wins; the older still shapes the fallback but cannot
    out-vote a fresher neighbour."""
    await market_cache.clear()
    instrument_id = "eth-usdt-perp"
    cache_ts = datetime.now(timezone.utc) - timedelta(seconds=30)
    await market_cache.set_mark(
        instrument_id, _price_payload(instrument_id, "3200.5", cache_ts)
    )

    db_mark = MarkPrice(
        mark_id=2,
        instrument_id=instrument_id,
        mark_price=Decimal("3199.0"),
        source="db:test",
        ts_event=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    service = MarketService(DummyRepo(latest=db_mark))

    monkeypatch.setattr(settings, "market_stream_prefer_ws_cache", True)
    monkeypatch.setattr(settings, "market_data_provider", "noop")

    mark = await service.get_best_mark(instrument_id, prefer_live=True)

    assert mark is not None
    assert mark.mark_price == Decimal("3200.5")  # cache is newer
    assert mark.source == "cache:test"
    assert mark.mark_id == 0  # sentinel preserved for live-only transport
    await market_cache.clear()


async def test_get_best_mark_still_returns_db_when_cache_is_older_than_db(
    monkeypatch,
) -> None:
    """Mirror of the previous case: DB is fresher, cache is within budget
    but older. DB must win — proving the merge respects ts_event, not
    cache-priority."""
    await market_cache.clear()
    instrument_id = "eth-usdt-perp"
    cache_ts = datetime.now(timezone.utc) - timedelta(minutes=2)
    await market_cache.set_mark(
        instrument_id, _price_payload(instrument_id, "3200.5", cache_ts)
    )

    db_mark = MarkPrice(
        mark_id=3,
        instrument_id=instrument_id,
        mark_price=Decimal("3199.0"),
        source="db:test",
        ts_event=datetime.now(timezone.utc),
    )
    service = MarketService(DummyRepo(latest=db_mark))

    monkeypatch.setattr(settings, "market_stream_prefer_ws_cache", True)
    monkeypatch.setattr(settings, "market_data_provider", "noop")

    mark = await service.get_best_mark(instrument_id, prefer_live=True)

    assert mark is db_mark
    await market_cache.clear()


async def test_get_best_mark_returns_none_with_aged_cache_and_no_db(
    monkeypatch,
) -> None:
    """If cache is residue and the DB has no row either, we must return
    None — not the residue, not a zero — so the caller can show a clear
    waiting/empty state instead of "缓存 · 6 天前"."""
    await market_cache.clear()
    instrument_id = "sol-usdt-perp"
    stale_ts = datetime.now(timezone.utc) - timedelta(
        seconds=LIVE_MARK_FALLBACK_MAX_AGE_SECONDS + 120
    )
    await market_cache.set_mark(
        instrument_id, _price_payload(instrument_id, "99.9", stale_ts)
    )

    service = MarketService(DummyRepo(latest=None))

    monkeypatch.setattr(settings, "market_stream_prefer_ws_cache", True)
    monkeypatch.setattr(settings, "market_data_provider", "noop")

    mark = await service.get_best_mark(instrument_id, prefer_live=True)

    assert mark is None
    assert await market_cache.get_mark(instrument_id) is None
    await market_cache.clear()
