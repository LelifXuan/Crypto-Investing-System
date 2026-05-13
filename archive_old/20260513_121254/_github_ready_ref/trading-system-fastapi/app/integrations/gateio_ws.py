from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class ParsedMarkUpdate:
    symbol: str
    price: Decimal
    source: str
    ts_event: datetime
    last_price: Decimal | None = None
    mark_price: Decimal | None = None
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ParsedBookTicker:
    symbol: str
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    source: str
    ts_event: datetime
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ParsedCandle:
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    ts_open: datetime
    is_closed: bool
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ParsedLiquidation:
    symbol: str
    ts_event: datetime
    event_key: str
    payload: dict[str, Any]


class GateWSParser:
    @staticmethod
    def parse_message(message: dict[str, Any]) -> list[ParsedMarkUpdate | ParsedBookTicker | ParsedCandle | ParsedLiquidation]:
        channel = str(message.get("channel") or "")
        if message.get("event") != "update":
            return []
        if channel == "spot.tickers":
            return GateWSParser._parse_spot_tickers(message)
        if channel == "spot.book_ticker":
            item = GateWSParser._parse_spot_book_ticker(message)
            return [item] if item else []
        if channel == "spot.candlesticks":
            item = GateWSParser._parse_spot_candle(message)
            return [item] if item else []
        if channel == "futures.tickers":
            return GateWSParser._parse_futures_tickers(message)
        if channel == "futures.book_ticker":
            item = GateWSParser._parse_futures_book_ticker(message)
            return [item] if item else []
        if channel == "futures.candlesticks":
            parsed = GateWSParser._parse_futures_candles(message)
            return [parsed] if parsed else []
        if channel == "futures.liquidates":
            return GateWSParser._parse_futures_liquidations(message)
        return []

    @staticmethod
    def _parse_spot_tickers(message: dict[str, Any]) -> list[ParsedMarkUpdate]:
        result = message.get("result") or []
        items = result if isinstance(result, list) else [result]
        parsed: list[ParsedMarkUpdate] = []
        ts_event = GateWSParser._event_ts(message)
        for item in items:
            symbol = GateWSParser._normalize_symbol(item.get("currency_pair") or item.get("cp") or item.get("s"))
            last = item.get("last") or item.get("close") or item.get("c")
            if not symbol or last is None:
                continue
            price = Decimal(str(last))
            parsed.append(
                ParsedMarkUpdate(
                    symbol=symbol,
                    price=price,
                    last_price=price,
                    mark_price=None,
                    source="gateio:ws:spot.tickers",
                    ts_event=ts_event,
                    payload=dict(item),
                )
            )
        return parsed

    @staticmethod
    def _parse_spot_book_ticker(message: dict[str, Any]) -> ParsedBookTicker | None:
        item = message.get("result") or {}
        symbol = GateWSParser._normalize_symbol(item.get("s") or item.get("currency_pair") or item.get("cp"))
        if not symbol:
            return None
        return ParsedBookTicker(
            symbol=symbol,
            bid_price=GateWSParser._decimal_or_none(item.get("b")),
            bid_size=GateWSParser._decimal_or_none(item.get("B")),
            ask_price=GateWSParser._decimal_or_none(item.get("a")),
            ask_size=GateWSParser._decimal_or_none(item.get("A")),
            source="gateio:ws:spot.book_ticker",
            ts_event=GateWSParser._event_ts(message),
            payload=dict(item),
        )

    @staticmethod
    def _parse_spot_candle(message: dict[str, Any]) -> ParsedCandle | None:
        item = message.get("result") or {}
        name = str(item.get("n") or "")
        if "_" not in name:
            return None
        timeframe, symbol = name.split("_", 1)
        ts_open = datetime.fromtimestamp(int(item.get("t", 0)), tz=UTC)
        return ParsedCandle(
            symbol=GateWSParser._normalize_symbol(symbol),
            timeframe=timeframe,
            open=Decimal(str(item.get("o", "0"))),
            high=Decimal(str(item.get("h", "0"))),
            low=Decimal(str(item.get("l", "0"))),
            close=Decimal(str(item.get("c", "0"))),
            volume=Decimal(str(item.get("v", item.get("a", "0")))),
            source="gateio:ws:spot.candlesticks",
            ts_open=ts_open,
            is_closed=bool(item.get("w", False)),
            payload=dict(item),
        )

    @staticmethod
    def _parse_futures_tickers(message: dict[str, Any]) -> list[ParsedMarkUpdate]:
        result = message.get("result") or []
        items = result if isinstance(result, list) else [result]
        parsed: list[ParsedMarkUpdate] = []
        ts_event = GateWSParser._event_ts(message)
        for item in items:
            symbol = GateWSParser._normalize_symbol(item.get("contract") or item.get("s"))
            mark = item.get("mark_price")
            last = item.get("last") or item.get("last_price")
            price_raw = mark or last
            if not symbol or price_raw is None:
                continue
            parsed.append(
                ParsedMarkUpdate(
                    symbol=symbol,
                    price=Decimal(str(price_raw)),
                    last_price=GateWSParser._decimal_or_none(last),
                    mark_price=GateWSParser._decimal_or_none(mark),
                    source="gateio:ws:futures.tickers",
                    ts_event=ts_event,
                    payload=dict(item),
                )
            )
        return parsed

    @staticmethod
    def _parse_futures_book_ticker(message: dict[str, Any]) -> ParsedBookTicker | None:
        item = message.get("result") or {}
        symbol = GateWSParser._normalize_symbol(item.get("s") or item.get("contract"))
        if not symbol:
            return None
        ts_raw = item.get("t") or message.get("time_ms") or message.get("time")
        ts_event = GateWSParser._coerce_timestamp(ts_raw)
        return ParsedBookTicker(
            symbol=symbol,
            bid_price=GateWSParser._decimal_or_none(item.get("b")),
            bid_size=GateWSParser._decimal_or_none(item.get("B")),
            ask_price=GateWSParser._decimal_or_none(item.get("a")),
            ask_size=GateWSParser._decimal_or_none(item.get("A")),
            source="gateio:ws:futures.book_ticker",
            ts_event=ts_event,
            payload=dict(item),
        )

    @staticmethod
    def _parse_futures_candles(message: dict[str, Any]) -> ParsedCandle | None:
        raw = message.get("result") or {}
        item = raw[0] if isinstance(raw, list) and raw else raw
        if not isinstance(item, dict):
            return None
        symbol = GateWSParser._normalize_symbol(item.get("n") or item.get("contract") or item.get("s"))
        timeframe = str(item.get("interval") or item.get("n") or "")
        if timeframe and "_" in timeframe:
            timeframe, symbol_from_name = timeframe.split("_", 1)
            symbol = GateWSParser._normalize_symbol(symbol_from_name)
        if not symbol:
            return None
        return ParsedCandle(
            symbol=symbol,
            timeframe=str(timeframe or "1m"),
            open=Decimal(str(item.get("o", "0"))),
            high=Decimal(str(item.get("h", "0"))),
            low=Decimal(str(item.get("l", "0"))),
            close=Decimal(str(item.get("c", "0"))),
            volume=Decimal(str(item.get("v", "0"))),
            source="gateio:ws:futures.candlesticks",
            ts_open=GateWSParser._coerce_timestamp(item.get("t") or item.get("time") or 0),
            is_closed=bool(item.get("w", True)),
            payload=dict(item),
        )

    @staticmethod
    def _parse_futures_liquidations(message: dict[str, Any]) -> list[ParsedLiquidation]:
        result = message.get("result") or []
        items = result if isinstance(result, list) else [result]
        parsed: list[ParsedLiquidation] = []
        for item in items:
            symbol = GateWSParser._normalize_symbol(item.get("contract") or item.get("s"))
            if not symbol:
                continue
            ts_event = GateWSParser._coerce_timestamp(item.get("time_ms") or item.get("time") or 0)
            order_id = item.get("order_id") or item.get("id") or "na"
            event_key = f"gateio:liq:{symbol}:{order_id}:{int(ts_event.timestamp() * 1000)}"
            parsed.append(ParsedLiquidation(symbol=symbol, ts_event=ts_event, event_key=event_key, payload=dict(item)))
        return parsed

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("/", "_").replace("-", "_").upper()

    @staticmethod
    def _event_ts(message: dict[str, Any]) -> datetime:
        return GateWSParser._coerce_timestamp(message.get("time_ms") or message.get("time") or 0)

    @staticmethod
    def _coerce_timestamp(raw: Any) -> datetime:
        if raw in (None, ""):
            return datetime.now(UTC)
        numeric = int(str(raw))
        if numeric > 10_000_000_000:
            return datetime.fromtimestamp(numeric / 1000, tz=UTC)
        return datetime.fromtimestamp(numeric, tz=UTC)

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))
