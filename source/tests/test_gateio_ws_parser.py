from decimal import Decimal

from app.integrations.gateio_ws import (
    GateWSParser,
    ParsedBookTicker,
    ParsedCandle,
    ParsedContractStats,
    ParsedFuturesTrade,
    ParsedMarkUpdate,
    ParsedOrderBookUpdate,
)


def test_parse_mark_update() -> None:
    message = {
        "channel": "futures.tickers",
        "result": {
            "contract": "BTC_USDT",
            "last": "68001.2",
            "mark_price": "68000.1",
            "time": 1712140800,
        },
    }
    items = GateWSParser.parse_message(message)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedMarkUpdate)
    assert item.symbol == "BTC_USDT"
    assert item.mark_price == Decimal("68000.1")


def test_parse_book_ticker() -> None:
    message = {
        "channel": "futures.book_ticker",
        "result": {
            "contract": "BTC_USDT",
            "b": "67999.9",
            "B": "12",
            "a": "68000.1",
            "A": "9",
            "time": 1712140800,
        },
    }
    items = GateWSParser.parse_message(message)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedBookTicker)
    assert item.bid_price == Decimal("67999.9")
    assert item.ask_price == Decimal("68000.1")


def test_parse_candle_closed() -> None:
    message = {
        "channel": "futures.candlesticks",
        "result": {
            "n": "1m,BTC_USDT",
            "t": 1712140800,
            "o": "67950",
            "h": "68100",
            "l": "67900",
            "c": "68000",
            "v": "22",
            "x": True,
        },
    }
    items = GateWSParser.parse_message(message)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedCandle)
    assert item.timeframe == "1m"
    assert item.close == Decimal("68000")
    assert item.is_closed is True


def test_parse_message_ignores_bad_payload() -> None:
    assert (
        GateWSParser.parse_message(
            {"channel": "futures.tickers", "result": {"contract": "BTC_USDT"}}
        )
        == []
    )


def test_parse_futures_trade() -> None:
    items = GateWSParser.parse_message(
        {
            "channel": "futures.trades",
            "result": {
                "id": 5,
                "contract": "BTC_USDT",
                "price": "68000",
                "size": "-2",
                "create_time": 1712140800,
            },
        }
    )

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedFuturesTrade)
    assert item.side == "sell"
    assert item.size == Decimal("2")


def test_parse_order_book_update() -> None:
    items = GateWSParser.parse_message(
        {
            "channel": "futures.order_book_update",
            "result": {
                "s": "BTC_USDT",
                "U": 10,
                "u": 12,
                "b": [["67999", "3"]],
                "a": [["68001", "4"]],
                "t": 1712140800,
            },
        }
    )

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedOrderBookUpdate)
    assert item.first_update_id == 10
    assert item.bids == [(Decimal("67999"), Decimal("3"))]


def test_parse_contract_stats() -> None:
    items = GateWSParser.parse_message(
        {
            "channel": "futures.contract_stats",
            "result": {
                "contract": "BTC_USDT",
                "open_interest": "100",
                "volume": "200",
                "funding_rate": "0.0001",
                "mark_price": "68000",
                "time": 1712140800,
            },
        }
    )

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ParsedContractStats)
    assert item.open_interest == Decimal("100")
    assert item.mark_price == Decimal("68000")
