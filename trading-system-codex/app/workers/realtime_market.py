from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from datetime import timezone, datetime, timedelta
UTC = timezone.utc
from decimal import Decimal

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.cache.market_cache import market_cache
from app.core.config import settings
from app.core.db import db_manager
from app.core.ids import new_id
from app.db.models.market import IndicatorObservation, MarketCandle, MarkPrice
from app.integrations.gateio_ws import (
    GateWSParser,
    ParsedBookTicker,
    ParsedCandle,
    ParsedContractStats,
    ParsedFuturesTrade,
    ParsedLiquidation,
    ParsedMarkUpdate,
    ParsedOrderBookUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.market_repository import MarketRepository
from app.services.eventing import EventPublisher
from app.services.market import MarketService
from app.services.microstructure import (
    TradeSample,
    aggregate_cvd_delta,
    summarize_depth_slippage,
)

logger = logging.getLogger(__name__)


class MarketStreamWorker:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()
        self._last_mark_persist: dict[str, datetime] = {}
        self._micro_trades: dict[str, list[TradeSample]] = defaultdict(list)
        self._micro_books: dict[str, ParsedOrderBookUpdate] = {}
        self._micro_stats: dict[str, ParsedContractStats] = {}
        self._last_micro_flush: datetime | None = None

    async def start(self) -> None:
        if not settings.market_stream_enabled or self._tasks:
            return
        specs = await self._load_specs()
        if not specs["spot"] and not specs["futures"]:
            logger.info(
                "market stream worker skipped because no Gate.io instruments are configured"
            )
            return
        self._stopping.clear()
        if specs["spot"]:
            self._tasks.append(
                asyncio.create_task(self._run_spot(specs["spot"]), name="gateio-spot-stream")
            )
        for settle, settle_specs in specs["futures"].items():
            self._tasks.append(
                asyncio.create_task(
                    self._run_futures(settle, settle_specs), name=f"gateio-futures-{settle}"
                )
            )

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _load_specs(self) -> dict:
        async with db_manager.session() as session:
            repo = MarketRepository(session)
            instruments = await repo.list_gateio_stream_instruments()
        spot_specs: list[dict] = []
        futures_specs: dict[str, list[dict]] = defaultdict(list)
        for instrument in instruments:
            ref = MarketService.resolve_gate_reference(instrument)
            item = {
                "instrument_id": instrument.instrument_id,
                "symbol": ref.symbol,
                "settle": ref.settle,
            }
            if ref.product_type == "spot":
                spot_specs.append(item)
            else:
                futures_specs[ref.settle or settings.gateio_default_settle].append(item)
        return {"spot": spot_specs, "futures": futures_specs}

    async def _run_spot(self, specs: list[dict]) -> None:
        symbols = sorted({item["symbol"] for item in specs})
        symbol_map = {item["symbol"]: item["instrument_id"] for item in specs}
        while not self._stopping.is_set():
            try:
                async with connect(settings.gateio_spot_ws_url, ping_interval=None) as ws:
                    await self._subscribe_spot(ws, symbols)
                    await self._consume(ws, symbol_map, ping_channel="spot.ping")
            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:  # pragma: no cover
                if not self._stopping.is_set():
                    logger.info("spot websocket disconnected: %s", self._describe_disconnect(exc))
                    await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)
            except Exception as exc:  # pragma: no cover
                logger.exception("spot websocket loop failed: %s", exc)
                await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)

    async def _run_futures(self, settle: str, specs: list[dict]) -> None:
        symbols = sorted({item["symbol"] for item in specs})
        symbol_map = {item["symbol"]: item["instrument_id"] for item in specs}
        ws_url = settings.gateio_futures_ws_url_template.format(settle=settle)
        while not self._stopping.is_set():
            try:
                async with connect(ws_url, ping_interval=None) as ws:
                    await self._subscribe_futures(ws, symbols)
                    await self._consume(ws, symbol_map, ping_channel="futures.ping")
            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:  # pragma: no cover
                if not self._stopping.is_set():
                    logger.info(
                        "futures websocket disconnected for %s: %s",
                        settle,
                        self._describe_disconnect(exc),
                    )
                    await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)
            except Exception as exc:  # pragma: no cover
                logger.exception("futures websocket loop failed for %s: %s", settle, exc)
                await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)

    async def _subscribe_spot(self, ws, symbols: list[str]) -> None:
        await ws.send(
            json.dumps(
                {
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "channel": "spot.tickers",
                    "event": "subscribe",
                    "payload": symbols,
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "channel": "spot.book_ticker",
                    "event": "subscribe",
                    "payload": symbols,
                }
            )
        )
        for timeframe in settings.market_stream_timeframes:
            for symbol in symbols:
                await ws.send(
                    json.dumps(
                        {
                            "time": int(datetime.now(timezone.utc).timestamp()),
                            "channel": "spot.candlesticks",
                            "event": "subscribe",
                            "payload": [timeframe, symbol],
                        }
                    )
                )

    async def _subscribe_futures(self, ws, symbols: list[str]) -> None:
        await ws.send(
            json.dumps(
                {
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "channel": "futures.tickers",
                    "event": "subscribe",
                    "payload": symbols,
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "channel": "futures.book_ticker",
                    "event": "subscribe",
                    "payload": symbols,
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "time": int(datetime.now(timezone.utc).timestamp()),
                    "channel": "futures.liquidates",
                    "event": "subscribe",
                    "payload": symbols,
                }
            )
        )
        for timeframe in settings.market_stream_timeframes:
            for symbol in symbols:
                await ws.send(
                    json.dumps(
                        {
                            "time": int(datetime.now(timezone.utc).timestamp()),
                            "channel": "futures.candlesticks",
                            "event": "subscribe",
                            "payload": [timeframe, symbol],
                        }
                    )
                )

    async def _consume(self, ws, symbol_map: dict[str, str], *, ping_channel: str) -> None:
        ping_task = asyncio.create_task(self._ping_loop(ws, ping_channel))
        try:
            async for raw in ws:
                await self._handle_message(json.loads(raw), symbol_map)
        finally:
            ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping_task

    async def _ping_loop(self, ws, ping_channel: str) -> None:
        while not self._stopping.is_set():
            await asyncio.sleep(settings.market_stream_ping_interval_seconds)
            try:
                await ws.send(
                    json.dumps(
                        {"time": int(datetime.now(timezone.utc).timestamp()), "channel": ping_channel}
                    )
                )
            except ConnectionClosed:
                return

    async def _handle_message(self, message: dict, symbol_map: dict[str, str]) -> None:
        parsed_items = GateWSParser.parse_message(message)
        if not parsed_items:
            return
        legacy_items = []
        for item in parsed_items:
            instrument_id = symbol_map.get(item.symbol)
            if instrument_id is None:
                continue
            if isinstance(item, ParsedFuturesTrade):
                self._micro_trades[instrument_id].append(
                    TradeSample(price=item.price, size=item.size, side=item.side)
                )
            elif isinstance(item, ParsedOrderBookUpdate):
                self._micro_books[instrument_id] = item
            elif isinstance(item, ParsedContractStats):
                self._micro_stats[instrument_id] = item
            else:
                legacy_items.append(item)
        await self._flush_microstructure_if_due()
        if not legacy_items:
            return
        async with db_manager.session() as session:
            repo = MarketRepository(session)
            event_repo = EventRepository(session)
            market_service = MarketService(repo, event_repo)
            publisher = EventPublisher(event_repo)
            for item in legacy_items:
                instrument_id = symbol_map.get(item.symbol)
                if instrument_id is None:
                    continue
                if isinstance(item, ParsedMarkUpdate):
                    await self._process_mark(market_service, instrument_id, item)
                elif isinstance(item, ParsedBookTicker):
                    await self._process_book(instrument_id, item)
                elif isinstance(item, ParsedCandle):
                    await self._process_candle(repo, publisher, instrument_id, item)
                elif isinstance(item, ParsedLiquidation):
                    await self._process_liquidation(publisher, instrument_id, item)

    async def _flush_microstructure_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_micro_flush and (now - self._last_micro_flush).total_seconds() < 60:
            return
        self._last_micro_flush = now
        if not (self._micro_trades or self._micro_books or self._micro_stats):
            return
        trades = self._micro_trades
        books = self._micro_books
        stats = self._micro_stats
        self._micro_trades = defaultdict(list)
        self._micro_books = {}
        self._micro_stats = {}
        async with db_manager.session() as session:
            repo = MarketRepository(session)
            for instrument_id, samples in trades.items():
                definition = await repo.get_indicator_definition("cvd_delta")
                if definition is None or not samples:
                    continue
                summary = aggregate_cvd_delta(samples)
                await repo.add_or_update_observation(
                    IndicatorObservation(
                        observation_id=new_id("obs"),
                        dedupe_key=f"cvd_delta|{instrument_id}|1m|{now.isoformat()}",
                        indicator_key="cvd_delta",
                        category="technical",
                        instrument_id=instrument_id,
                        timeframe="1m",
                        observation_ts=now,
                        value_num=summary.delta,
                        value_json={
                            "buy_volume": str(summary.buy_volume),
                            "sell_volume": str(summary.sell_volume),
                            "delta": str(summary.delta),
                            "cvd": str(summary.cvd),
                            "trade_count": summary.trade_count,
                        },
                        signal_state="buy_delta" if summary.delta > 0 else "sell_delta",
                        source_provider="gateio",
                        source_ref="futures.trades.ws",
                        source_granularity="1m",
                    )
                )
            for instrument_id, book in books.items():
                if not book.bids and not book.asks:
                    continue
                summary = summarize_depth_slippage(
                    book.bids,
                    book.asks,
                    notional=Decimal("10000"),
                )
                await repo.add_or_update_observation(
                    IndicatorObservation(
                        observation_id=new_id("obs"),
                        dedupe_key=f"depth_liquidity|{instrument_id}|1m|{now.isoformat()}",
                        indicator_key="depth_liquidity",
                        category="technical",
                        instrument_id=instrument_id,
                        timeframe="1m",
                        observation_ts=now,
                        value_num=summary.depth_50bps,
                        value_json={
                            "spread_bps": str(summary.spread_bps),
                            "depth_10bps": str(summary.depth_10bps),
                            "depth_50bps": str(summary.depth_50bps),
                            "depth_100bps": str(summary.depth_100bps),
                            "buy_slippage_bps": str(summary.buy_slippage_bps)
                            if summary.buy_slippage_bps is not None
                            else None,
                            "sell_slippage_bps": str(summary.sell_slippage_bps)
                            if summary.sell_slippage_bps is not None
                            else None,
                        },
                        signal_state="normal",
                        source_provider="gateio",
                        source_ref="futures.order_book_update.ws",
                        source_granularity="1m",
                    )
                )
            for instrument_id, stat in stats.items():
                if stat.open_interest is None:
                    continue
                notional = (
                    stat.open_interest * stat.mark_price
                    if stat.mark_price is not None
                    else stat.open_interest
                )
                await repo.add_or_update_observation(
                    IndicatorObservation(
                        observation_id=new_id("obs"),
                        dedupe_key=(
                            f"open_interest_notional|{instrument_id}|1m|{now.isoformat()}"
                        ),
                        indicator_key="open_interest_notional",
                        category="technical",
                        instrument_id=instrument_id,
                        timeframe="1m",
                        observation_ts=now,
                        value_num=notional,
                        value_json={
                            "open_interest": str(stat.open_interest),
                            "open_interest_notional": str(notional),
                            "funding_rate": str(stat.funding_rate)
                            if stat.funding_rate is not None
                            else None,
                            "mark_price": str(stat.mark_price)
                            if stat.mark_price is not None
                            else None,
                        },
                        signal_state="normal",
                        source_provider="gateio",
                        source_ref="futures.contract_stats.ws",
                        source_granularity="1m",
                    )
                )

    async def _process_mark(
        self, market_service: MarketService, instrument_id: str, item: ParsedMarkUpdate
    ) -> None:
        await market_cache.set_mark(
            instrument_id,
            {
                "instrument_id": instrument_id,
                "mark_price": str(item.mark_price or item.price),
                "last_price": str(item.last_price or item.price),
                "source": f"cache:{item.source}",
                "ts_event": item.ts_event.isoformat(),
                "payload": item.payload,
            },
        )
        if not settings.market_stream_persist_marks:
            return
        last_persist = self._last_mark_persist.get(instrument_id)
        if last_persist and item.ts_event - last_persist < timedelta(
            seconds=settings.market_stream_mark_persist_min_interval_seconds
        ):
            return
        self._last_mark_persist[instrument_id] = item.ts_event
        await market_service.add_mark_price(
            MarkPrice(
                instrument_id=instrument_id,
                mark_price=item.mark_price or item.price,
                source=item.source,
                ts_event=item.ts_event,
            )
        )

    async def _process_book(self, instrument_id: str, item: ParsedBookTicker) -> None:
        await market_cache.set_book_ticker(
            instrument_id,
            {
                "instrument_id": instrument_id,
                "bid_price": str(item.bid_price) if item.bid_price is not None else None,
                "bid_size": str(item.bid_size) if item.bid_size is not None else None,
                "ask_price": str(item.ask_price) if item.ask_price is not None else None,
                "ask_size": str(item.ask_size) if item.ask_size is not None else None,
                "source": f"cache:{item.source}",
                "ts_event": item.ts_event.isoformat(),
            },
        )

    async def _process_candle(
        self,
        repo: MarketRepository,
        publisher: EventPublisher,
        instrument_id: str,
        item: ParsedCandle,
    ) -> None:
        payload = {
            "instrument_id": instrument_id,
            "timeframe": item.timeframe,
            "ts_open": item.ts_open.isoformat(),
            "open": str(item.open),
            "high": str(item.high),
            "low": str(item.low),
            "close": str(item.close),
            "volume": str(item.volume),
            "source": f"cache:{item.source}",
            "is_closed": item.is_closed,
            "payload": item.payload,
        }
        await market_cache.set_candle(instrument_id, item.timeframe, item.source, payload)
        if settings.market_stream_persist_candles or item.is_closed:
            await repo.upsert_candles(
                [
                    MarketCandle(
                        instrument_id=instrument_id,
                        timeframe=item.timeframe,
                        ts_open=item.ts_open,
                        open=item.open,
                        high=item.high,
                        low=item.low,
                        close=item.close,
                        volume=item.volume,
                        source=item.source,
                    )
                ]
            )
        if item.is_closed:
            await publisher.publish(
                event_type="market.candle.closed",
                source=item.source,
                partition_key=f"{instrument_id}:{item.timeframe}",
                payload={
                    "instrument_id": instrument_id,
                    "timeframe": item.timeframe,
                    "source_preference": "gateio",
                    "price_kind": "last",
                },
                idempotency_key=f"candle-closed:{instrument_id}:{item.timeframe}:{item.ts_open.isoformat()}",
            )

    async def _process_liquidation(
        self, publisher: EventPublisher, instrument_id: str, item: ParsedLiquidation
    ) -> None:
        await publisher.publish(
            event_type="market.liquidation.detected",
            source=item.source,
            partition_key=instrument_id,
            payload={
                "instrument_id": instrument_id,
                "side": item.side,
                "price": str(item.price) if item.price is not None else None,
                "size": str(item.size) if item.size is not None else None,
                "ts_event": item.ts_event.isoformat(),
            },
            idempotency_key=f"liquidation:{instrument_id}:{item.ts_event.isoformat()}:{item.side}",
        )

    @staticmethod
    def _describe_disconnect(exc: ConnectionClosed) -> str:
        code = getattr(exc.rcvd, "code", None) or getattr(exc.sent, "code", None)
        reason = getattr(exc.rcvd, "reason", None) or getattr(exc.sent, "reason", None)
        if code is None and not reason:
            return "connection closed without a close frame"
        if reason:
            return f"code={code}, reason={reason}"
        return f"code={code}"


market_stream_worker = MarketStreamWorker()
