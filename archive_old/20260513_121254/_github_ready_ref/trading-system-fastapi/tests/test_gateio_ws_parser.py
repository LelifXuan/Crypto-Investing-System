from __future__ import annotations

from app.integrations.gateio_ws import GateWSParser, ParsedCandle, ParsedMarkUpdate


def test_parse_futures_ticker_message() -> None:
    payload = {
        "time": 1541659086,
        "channel": "futures.tickers",
        "event": "update",
        "result": [{"contract": "BTC_USDT", "last": "118.4", "mark_price": "118.35"}],
    }
    parsed = GateWSParser.parse_message(payload)
    assert len(parsed) == 1
    item = parsed[0]
    assert isinstance(item, ParsedMarkUpdate)
    assert item.symbol == "BTC_USDT"


def test_parse_spot_candle_message() -> None:
    payload = {
        "time": 1606292600,
        "channel": "spot.candlesticks",
        "event": "update",
        "result": {"t": "1606292580", "v": "2362.32035", "c": "19128.1", "h": "19128.1", "l": "19128.1", "o": "19128.1", "n": "1m_BTC_USDT", "w": True},
    }
    parsed = GateWSParser.parse_message(payload)
    assert len(parsed) == 1
    item = parsed[0]
    assert isinstance(item, ParsedCandle)
    assert item.timeframe == "1m"
    assert item.symbol == "BTC_USDT"
