from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(slots=True)
class ParsedMarkUpdate:
    symbol: str
    price: Decimal
    mark_price: Decimal | None
    last_price: Decimal | None
    source: str
    ts_event: datetime
    payload: dict


@dataclass(slots=True)
class ParsedBookTicker:
    symbol: str
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    source: str
    ts_event: datetime
    payload: dict


@dataclass(slots=True)
class ParsedCandle:
    symbol: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool
    source: str
    payload: dict


@dataclass(slots=True)
class ParsedLiquidation:
    symbol: str
    side: str | None
    price: Decimal | None
    size: Decimal | None
    source: str
    ts_event: datetime
    payload: dict


@dataclass(slots=True)
class ParsedFuturesTrade:
    symbol: str
    trade_id: str | None
    price: Decimal
    size: Decimal
    side: str | None
    source: str
    ts_event: datetime
    payload: dict


@dataclass(slots=True)
class ParsedOrderBookUpdate:
    symbol: str
    first_update_id: int | None
    final_update_id: int | None
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    source: str
    ts_event: datetime
    payload: dict


@dataclass(slots=True)
class ParsedContractStats:
    symbol: str
    open_interest: Decimal | None
    volume: Decimal | None
    funding_rate: Decimal | None
    mark_price: Decimal | None
    source: str
    ts_event: datetime
    payload: dict


ParsedGateWSItem = (
    ParsedMarkUpdate
    | ParsedBookTicker
    | ParsedCandle
    | ParsedLiquidation
    | ParsedFuturesTrade
    | ParsedOrderBookUpdate
    | ParsedContractStats
)


class GateWSParser:
    @staticmethod
    def parse_message(message: dict) -> list[ParsedGateWSItem]:
        if not isinstance(message, dict):
            return []
        channel = str(message.get("channel") or "")
        result = message.get("result")
        if not result:
            return []
        items = result if isinstance(result, list) else [result]
        parsed: list[ParsedGateWSItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                if channel in {"spot.tickers", "futures.tickers"}:
                    parsed.append(GateWSParser._parse_ticker(channel, item))
                elif channel in {"spot.book_ticker", "futures.book_ticker"}:
                    parsed.append(GateWSParser._parse_book(channel, item))
                elif channel in {"spot.candlesticks", "futures.candlesticks"}:
                    candle = GateWSParser._parse_candle(channel, item)
                    if candle is not None:
                        parsed.append(candle)
                elif channel == "futures.liquidates":
                    parsed.append(GateWSParser._parse_liquidation(channel, item))
                elif channel == "futures.trades":
                    parsed.append(GateWSParser._parse_trade(channel, item))
                elif channel == "futures.order_book_update":
                    parsed.append(GateWSParser._parse_order_book_update(channel, item))
                elif channel == "futures.contract_stats":
                    parsed.append(GateWSParser._parse_contract_stats(channel, item))
            except Exception:
                continue
        return parsed

    @staticmethod
    def _parse_ticker(channel: str, item: dict) -> ParsedMarkUpdate:
        symbol = str(item.get("currency_pair") or item.get("contract") or item.get("symbol"))
        last_price = item.get("last")
        mark_price = item.get("mark_price")
        price = Decimal(str(mark_price or last_price or item.get("close")))
        return ParsedMarkUpdate(
            symbol=symbol.upper(),
            price=price,
            mark_price=Decimal(str(mark_price)) if mark_price is not None else None,
            last_price=Decimal(str(last_price)) if last_price is not None else None,
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(item.get("time_ms") or item.get("time")),
            payload=item,
        )

    @staticmethod
    def _parse_book(channel: str, item: dict) -> ParsedBookTicker:
        symbol = str(item.get("currency_pair") or item.get("contract") or item.get("symbol"))
        return ParsedBookTicker(
            symbol=symbol.upper(),
            bid_price=GateWSParser._maybe_decimal(item.get("b") or item.get("highest_bid")),
            bid_size=GateWSParser._maybe_decimal(item.get("B") or item.get("bid_size")),
            ask_price=GateWSParser._maybe_decimal(item.get("a") or item.get("lowest_ask")),
            ask_size=GateWSParser._maybe_decimal(item.get("A") or item.get("ask_size")),
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(item.get("time_ms") or item.get("time")),
            payload=item,
        )

    @staticmethod
    def _parse_candle(channel: str, item: dict) -> ParsedCandle | None:
        symbol = str(item.get("currency_pair") or item.get("contract") or item.get("symbol") or "")
        timeframe = str(item.get("interval") or "")
        name = str(item.get("n") or "")
        if name and "," in name:
            timeframe, symbol = name.split(",", 1)
        elif not symbol:
            symbol = name
        open_ts = item.get("t") or item.get("start")
        if open_ts is None:
            return None
        return ParsedCandle(
            symbol=symbol.upper(),
            timeframe=timeframe,
            ts_open=GateWSParser._coerce_ts(open_ts),
            open=Decimal(str(item.get("o") or item.get("open"))),
            high=Decimal(str(item.get("h") or item.get("high"))),
            low=Decimal(str(item.get("l") or item.get("low"))),
            close=Decimal(str(item.get("c") or item.get("close"))),
            volume=Decimal(str(item.get("v") or item.get("volume") or "0")),
            is_closed=bool(item.get("x") or item.get("is_closed") or False),
            source=f"gateio:{channel}",
            payload=item,
        )

    @staticmethod
    def _parse_liquidation(channel: str, item: dict) -> ParsedLiquidation:
        symbol = str(item.get("contract") or item.get("symbol"))
        return ParsedLiquidation(
            symbol=symbol.upper(),
            side=item.get("side"),
            price=GateWSParser._maybe_decimal(item.get("fill_price") or item.get("price")),
            size=GateWSParser._maybe_decimal(item.get("size") or item.get("qty")),
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(item.get("time_ms") or item.get("time")),
            payload=item,
        )

    @staticmethod
    def _parse_trade(channel: str, item: dict) -> ParsedFuturesTrade:
        symbol = str(item.get("contract") or item.get("symbol"))
        size = GateWSParser._maybe_decimal(
            item.get("size") or item.get("amount") or item.get("qty")
        )
        side = item.get("side")
        if side is None and size is not None and size != 0:
            side = "buy" if size > 0 else "sell"
        return ParsedFuturesTrade(
            symbol=symbol.upper(),
            trade_id=str(item.get("id")) if item.get("id") is not None else None,
            price=Decimal(str(item.get("price"))),
            size=abs(size or Decimal("0")),
            side=str(side).lower() if side is not None else None,
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(
                item.get("create_time_ms")
                or item.get("time_ms")
                or item.get("create_time")
                or item.get("time")
            ),
            payload=item,
        )

    @staticmethod
    def _parse_order_book_update(channel: str, item: dict) -> ParsedOrderBookUpdate:
        symbol = str(item.get("s") or item.get("contract") or item.get("symbol"))
        return ParsedOrderBookUpdate(
            symbol=symbol.upper(),
            first_update_id=GateWSParser._maybe_int(item.get("U")),
            final_update_id=GateWSParser._maybe_int(item.get("u")),
            bids=GateWSParser._parse_levels(item.get("b") or item.get("bids") or []),
            asks=GateWSParser._parse_levels(item.get("a") or item.get("asks") or []),
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(item.get("E") or item.get("t") or item.get("time")),
            payload=item,
        )

    @staticmethod
    def _parse_contract_stats(channel: str, item: dict) -> ParsedContractStats:
        symbol = str(item.get("contract") or item.get("symbol"))
        return ParsedContractStats(
            symbol=symbol.upper(),
            open_interest=GateWSParser._maybe_decimal(
                item.get("open_interest") or item.get("open_interest_usd")
            ),
            volume=GateWSParser._maybe_decimal(
                item.get("volume") or item.get("volume_24h") or item.get("volume_usd")
            ),
            funding_rate=GateWSParser._maybe_decimal(item.get("funding_rate")),
            mark_price=GateWSParser._maybe_decimal(item.get("mark_price")),
            source=f"gateio:{channel}",
            ts_event=GateWSParser._coerce_ts(
                item.get("time_ms") or item.get("time") or item.get("t")
            ),
            payload=item,
        )

    @staticmethod
    def _coerce_ts(value) -> datetime:
        if value is None:
            return datetime.now(UTC)
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000
        return datetime.fromtimestamp(raw, tz=UTC)

    @staticmethod
    def _maybe_decimal(value) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _maybe_int(value) -> int | None:
        return int(value) if value is not None else None

    @staticmethod
    def _parse_levels(levels) -> list[tuple[Decimal, Decimal]]:
        parsed: list[tuple[Decimal, Decimal]] = []
        for level in levels:
            if isinstance(level, dict):
                price = level.get("p") or level.get("price")
                size = level.get("s") or level.get("size") or level.get("amount")
            else:
                price = level[0] if len(level) > 0 else None
                size = level[1] if len(level) > 1 else None
            if price is None or size is None:
                continue
            parsed.append((Decimal(str(price)), abs(Decimal(str(size)))))
        return parsed
