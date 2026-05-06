from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from websockets.asyncio.client import connect

from app.cache.market_cache import market_cache
from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import MarketCandle, MarketEvent, MarkPrice
from app.events.bus import event_bus_worker  # noqa: F401  # keep import reachable in startup graph
from app.integrations.gateio_ws import GateWSParser, ParsedBookTicker, ParsedCandle, ParsedLiquidation, ParsedMarkUpdate
from app.repositories.event_repository import EventRepository
from app.repositories.market_repository import MarketRepository
from app.services.eventing import EventPublisher
from app.services.market import MarketService

logger = logging.getLogger(__name__)


class MarketStreamWorker:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()
        self._last_mark_persist: dict[str, datetime] = {}

    async def start(self) -> None:
        if not settings.market_stream_enabled or self._tasks:
            return
        specs = await self._load_specs()
        if not specs["spot"] and not specs["futures"]:
            logger.info("market stream worker skipped because no Gate.io instruments are configured")
            return
        self._stopping.clear()
        if specs["spot"]:
            self._tasks.append(asyncio.create_task(self._run_spot(specs["spot"]), name="gateio-spot-stream"))
        for settle, settle_specs in specs["futures"].items():
            name = f"gateio-futures-stream-{settle}"
            self._tasks.append(asyncio.create_task(self._run_futures(settle, settle_specs), name=name))

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
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
                    await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "spot.tickers", "event": "subscribe", "payload": symbols}))
                    await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "spot.book_ticker", "event": "subscribe", "payload": symbols}))
                    for timeframe in settings.market_stream_timeframes:
                        for symbol in symbols:
                            await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "spot.candlesticks", "event": "subscribe", "payload": [timeframe, symbol]}))
                    ping_task = asyncio.create_task(self._ping_loop(ws, "spot.ping"))
                    try:
                        async for raw in ws:
                            message = json.loads(raw)
                            await self._handle_message(message, symbol_map)
                    finally:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("spot websocket loop failed: %s", exc)
                await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)

    async def _run_futures(self, settle: str, specs: list[dict]) -> None:
        symbols = sorted({item["symbol"] for item in specs})
        symbol_map = {item["symbol"]: item["instrument_id"] for item in specs}
        ws_url = settings.gateio_futures_ws_url_template.format(settle=settle)
        while not self._stopping.is_set():
            try:
                async with connect(ws_url, ping_interval=None, additional_headers={"X-Gate-Size-Decimal": "1"}) as ws:
                    await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "futures.tickers", "event": "subscribe", "payload": symbols}))
                    await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "futures.book_ticker", "event": "subscribe", "payload": symbols}))
                    await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "futures.liquidates", "event": "subscribe", "payload": symbols}))
                    for timeframe in settings.market_stream_timeframes:
                        for symbol in symbols:
                            await ws.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": "futures.candlesticks", "event": "subscribe", "payload": [timeframe, symbol]}))
                    ping_task = asyncio.create_task(self._ping_loop(ws, "futures.ping"))
                    try:
                        async for raw in ws:
                            message = json.loads(raw)
                            await self._handle_message(message, symbol_map)
                    finally:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception("futures websocket loop failed for %s: %s", settle, exc)
                await asyncio.sleep(settings.market_stream_reconnect_delay_seconds)

    async def _ping_loop(self, websocket, channel: str) -> None:
        while not self._stopping.is_set():
            await asyncio.sleep(settings.market_stream_ping_interval_seconds)
            await websocket.send(json.dumps({"time": int(datetime.now(UTC).timestamp()), "channel": channel}))

    async def _handle_message(self, message: dict, symbol_map: dict[str, str]) -> None:
        parsed_items = GateWSParser.parse_message(message)
        if not parsed_items:
            return
        async with db_manager.session() as session:
            repo = MarketRepository(session)
            event_repo = EventRepository(session)
            market_service = MarketService(repo, event_repo)
            publisher = EventPublisher(event_repo)
            for item in parsed_items:
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
                    await self._process_liquidation(market_service, instrument_id, item)

    async def _process_mark(self, market_service: MarketService, instrument_id: str, item: ParsedMarkUpdate) -> None:
        await market_cache.set_mark(
            instrument_id,
            {
                "instrument_id": instrument_id,
                "price": str(item.price),
                "last_price": str(item.last_price or item.price),
                "mark_price": str(item.mark_price or item.price),
                "source": item.source,
                "ts_event": item.ts_event.isoformat(),
                "payload": item.payload or {},
            },
        )
        if not settings.market_stream_persist_marks:
            return
        last_persist = self._last_mark_persist.get(instrument_id)
        if last_persist is not None and item.ts_event - last_persist < timedelta(seconds=settings.market_stream_mark_persist_min_interval_seconds):
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
                "source": item.source,
                "ts_event": item.ts_event.isoformat(),
                "payload": item.payload or {},
            },
        )

    async def _process_candle(self, repo: MarketRepository, publisher: EventPublisher, instrument_id: str, item: ParsedCandle) -> None:
        candle = MarketCandle(
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
        await market_cache.set_candle(
            instrument_id,
            item.timeframe,
            item.source,
            {
                "instrument_id": instrument_id,
                "timeframe": item.timeframe,
                "ts_open": item.ts_open.isoformat(),
                "open": str(item.open),
                "high": str(item.high),
                "low": str(item.low),
                "close": str(item.close),
                "volume": str(item.volume),
                "source": item.source,
                "is_closed": item.is_closed,
                "payload": item.payload or {},
            },
        )
        if settings.market_stream_persist_candles:
            await repo.upsert_candles([candle])
        if item.is_closed:
            await publisher.publish(
                event_type="market.candle.closed",
                source=item.source,
                partition_key=f"{instrument_id}:{item.timeframe}",
                payload={
                    "instrument_id": instrument_id,
                    "timeframe": item.timeframe,
                    "price_kind": "mark" if ":mark" in item.source else "last",
                    "source_preference": "gateio",
                    "ts_open": item.ts_open.isoformat(),
                },
                idempotency_key=f"candle-close:{instrument_id}:{item.timeframe}:{item.source}:{item.ts_open.isoformat()}",
            )

    async def _process_liquidation(self, market_service: MarketService, instrument_id: str, item: ParsedLiquidation) -> None:
        title = f"Gate liquidation event on {item.symbol}"
        summary = None
        size = item.payload.get("size")
        if size is not None:
            summary = f"size={size} mark_price={item.payload.get('mark_price')} liq_price={item.payload.get('liq_price')}"
        await market_service.add_market_event(
            MarketEvent(
                event_id=item.event_key,
                category="liquidation",
                title=title,
                summary=summary,
                source="gateio:ws:futures.liquidates",
                reliability="HIGH",
                ts_event=item.ts_event,
                payload_json=item.payload,
            ),
            instrument_ids=[instrument_id],
        )


market_stream_worker = MarketStreamWorker()
