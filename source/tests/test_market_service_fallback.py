from datetime import datetime, timezone
from decimal import Decimal

from app.cache.market_cache import market_cache
from app.cache.shared_query_cache import shared_query_cache
from app.db.models.market import MarketCandle, MarkPrice
from app.services.market import MarketService


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
            "ts_event": "2026-04-05T00:00:00+00:00",
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
