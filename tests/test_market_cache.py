from app.cache.market_cache import market_cache


async def test_market_cache_overwrites_mark() -> None:
    await market_cache.set_mark(
        "btc-usdt-perp",
        {
            "instrument_id": "btc-usdt-perp",
            "mark_price": "1",
            "source": "a",
            "ts_event": "2026-04-05T00:00:00+00:00",
        },
    )
    await market_cache.set_mark(
        "btc-usdt-perp",
        {
            "instrument_id": "btc-usdt-perp",
            "mark_price": "2",
            "source": "b",
            "ts_event": "2026-04-05T00:01:00+00:00",
        },
    )
    payload = await market_cache.get_mark("btc-usdt-perp")
    assert payload is not None
    assert payload["mark_price"] == "2"
    assert payload["source"] == "b"


async def test_market_cache_keeps_candles_by_timeframe() -> None:
    await market_cache.set_candle(
        "btc-usdt-perp",
        "1m",
        "gateio:futures.candlesticks",
        {
            "instrument_id": "btc-usdt-perp",
            "timeframe": "1m",
            "ts_open": "2026-04-05T00:00:00+00:00",
            "close": "1",
            "open": "1",
            "high": "1",
            "low": "1",
            "volume": "1",
            "source": "gateio:futures.candlesticks",
        },
    )
    await market_cache.set_candle(
        "btc-usdt-perp",
        "5m",
        "gateio:futures.candlesticks",
        {
            "instrument_id": "btc-usdt-perp",
            "timeframe": "5m",
            "ts_open": "2026-04-05T00:00:00+00:00",
            "close": "2",
            "open": "2",
            "high": "2",
            "low": "2",
            "volume": "2",
            "source": "gateio:futures.candlesticks",
        },
    )
    candle_1m = await market_cache.get_candle("btc-usdt-perp", "1m")
    candle_5m = await market_cache.get_candle("btc-usdt-perp", "5m")
    assert candle_1m is not None and candle_1m["close"] == "1"
    assert candle_5m is not None and candle_5m["close"] == "2"
