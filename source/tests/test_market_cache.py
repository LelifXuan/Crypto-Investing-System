from datetime import datetime, timedelta, timezone

from app.cache.market_cache import (
    LIVE_MARK_MAX_AGE_SECONDS,
    is_mark_fresh,
    market_cache,
)


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


# ---------------------------------------------------------------------------
# 2026-09-22 price-lag bug: cache freshness helper + bulk eviction
# ---------------------------------------------------------------------------

UTC = timezone.utc


def test_is_mark_fresh_returns_false_for_missing_payload() -> None:
    assert is_mark_fresh(None) is False
    assert is_mark_fresh({}) is False
    assert is_mark_fresh({"ts_event": ""}) is False


def test_is_mark_fresh_returns_false_for_unparseable_timestamp() -> None:
    assert is_mark_fresh({"ts_event": "not-an-iso"}) is False
    assert is_mark_fresh({"ts_event": "2026-13-99T99:99:99"}) is False


def test_is_mark_fresh_returns_false_for_future_timestamp() -> None:
    # Clock skew / provider pushing a pre-stamped future event must not
    # pass as fresh — otherwise the fast path would happily return a price
    # the user has not actually been quoted yet.
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    assert is_mark_fresh({"ts_event": future}) is False


def test_is_mark_fresh_within_budget_returns_true() -> None:
    now = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
    payload = {"ts_event": (now - timedelta(seconds=LIVE_MARK_MAX_AGE_SECONDS)).isoformat()}
    assert is_mark_fresh(payload, now=now) is True


def test_is_mark_fresh_just_outside_budget_returns_false() -> None:
    now = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
    payload = {
        "ts_event": (now - timedelta(seconds=LIVE_MARK_MAX_AGE_SECONDS + 1)).isoformat()
    }
    assert is_mark_fresh(payload, now=now) is False


async def test_clear_marks_evicts_only_listed_ids() -> None:
    await market_cache.clear()
    await market_cache.set_mark(
        "btc-usdt-perp",
        {"instrument_id": "btc-usdt-perp", "mark_price": "1", "source": "x",
         "ts_event": "2026-09-22T00:00:00+00:00"},
    )
    await market_cache.set_mark(
        "eth-usdt-perp",
        {"instrument_id": "eth-usdt-perp", "mark_price": "2", "source": "x",
         "ts_event": "2026-09-22T00:00:00+00:00"},
    )
    await market_cache.clear_marks(["btc-usdt-perp", "missing-instrument"])
    assert await market_cache.get_mark("btc-usdt-perp") is None
    assert await market_cache.get_mark("eth-usdt-perp") is not None
    await market_cache.clear()


async def test_clear_marks_with_empty_iterable_is_a_noop() -> None:
    await market_cache.clear()
    await market_cache.set_mark(
        "btc-usdt-perp",
        {"instrument_id": "btc-usdt-perp", "mark_price": "1", "source": "x",
         "ts_event": "2026-09-22T00:00:00+00:00"},
    )
    await market_cache.clear_marks([])
    assert await market_cache.get_mark("btc-usdt-perp") is not None
    await market_cache.clear()
