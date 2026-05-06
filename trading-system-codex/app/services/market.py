from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status

from app.cache.market_cache import market_cache
from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.db.models.instrument import Instrument
from app.db.models.market import MarketCandle, MarketEvent, MarketEventInstrument, MarkPrice
from app.integrations.gateio import GateIOPublicClient, GateMarketRef
from app.repositories.event_repository import EventRepository
from app.repositories.market_repository import MarketRepository
from app.services.eventing import EventPublisher


class MarketService:
    def __init__(
        self,
        repository: MarketRepository,
        event_repository: EventRepository | None = None,
        gate_client: GateIOPublicClient | None = None,
    ) -> None:
        self.repository = repository
        self.event_repository = event_repository
        self.gate_client = gate_client or GateIOPublicClient()

    async def add_mark_price(self, mark: MarkPrice) -> MarkPrice:
        persisted = await self.repository.add_mark_price(mark)
        if self.event_repository is not None:
            publisher = EventPublisher(self.event_repository)
            await publisher.publish(
                event_type="market.mark_price.updated",
                source="market-prices",
                partition_key=mark.instrument_id,
                payload={
                    "instrument_id": mark.instrument_id,
                    "mark_price": str(mark.mark_price),
                    "source": mark.source,
                    "ts_event": mark.ts_event.isoformat(),
                },
                idempotency_key=f"mark:{mark.instrument_id}:{mark.source}:{mark.ts_event.isoformat()}",
            )
        return persisted

    async def get_best_mark(self, instrument_id: str, prefer_live: bool = True) -> MarkPrice | None:
        if prefer_live and settings.market_stream_prefer_ws_cache:
            cached = await market_cache.get_mark(instrument_id)
            if cached is not None:
                return MarkPrice(
                    mark_id=0,
                    instrument_id=instrument_id,
                    mark_price=Decimal(str(cached["mark_price"])),
                    source=cached["source"],
                    ts_event=datetime.fromisoformat(cached["ts_event"]),
                )
        if prefer_live and settings.market_data_provider.lower() == "gateio":
            try:
                return await self.fetch_and_persist_live_mark(instrument_id)
            except Exception:
                pass
        return await self.repository.latest_mark(instrument_id)

    async def fetch_and_persist_live_mark(self, instrument_id: str) -> MarkPrice:
        instrument = await self._require_instrument(instrument_id)
        ref = self.resolve_gate_reference(instrument)
        ts_event = datetime.now(timezone.utc)
        if ref.product_type == "spot":
            ticker = await self.gate_client.get_spot_ticker(ref.symbol)
            model = MarkPrice(
                instrument_id=instrument.instrument_id,
                mark_price=ticker["last"],
                source="gateio:spot.tickers",
                ts_event=ts_event,
            )
        else:
            contract = await self.gate_client.get_futures_contract(
                ref.settle or settings.gateio_default_settle, ref.symbol
            )
            model = MarkPrice(
                instrument_id=instrument.instrument_id,
                mark_price=contract.get("mark_price") or contract.get("last_price"),
                source="gateio:futures.contracts",
                ts_event=ts_event,
            )
        return await self.add_mark_price(model)

    async def add_candle(self, candle: MarketCandle) -> MarketCandle:
        return await self.repository.add_candle(candle)

    async def sync_candles_from_provider(
        self,
        instrument_id: str,
        timeframe: str,
        limit: int = 200,
        price_kind: str = "last",
        from_ts: int | None = None,
        to_ts: int | None = None,
        persist: bool = True,
    ) -> list[MarketCandle]:
        cache_key = (
            f"candles:{instrument_id}:{timeframe}:{price_kind}:{limit}:"
            f"{from_ts or '-'}:{to_ts or '-'}"
        )

        async def producer() -> list[dict]:
            instrument = await self._require_instrument(instrument_id)
            ref = self.resolve_gate_reference(instrument)
            if ref.product_type == "spot":
                remote = await self.gate_client.get_spot_candles(
                    currency_pair=ref.symbol,
                    interval=timeframe,
                    limit=limit,
                    from_ts=from_ts,
                    to_ts=to_ts,
                )
            else:
                contract = ref.symbol
                if price_kind == "mark":
                    contract = f"mark_{contract}"
                elif price_kind == "index":
                    contract = f"index_{contract}"
                remote = await self.gate_client.get_futures_candles(
                    settle=ref.settle or settings.gateio_default_settle,
                    contract=contract,
                    interval=timeframe,
                    limit=limit,
                    from_ts=from_ts,
                    to_ts=to_ts,
                )
            return [
                {
                    "instrument_id": instrument.instrument_id,
                    "timeframe": timeframe,
                    "ts_open": item.ts_open,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                    "source": item.source
                    if price_kind == "last"
                    else f"{item.source}:{price_kind}",
                }
                for item in remote
            ]

        candle_rows = await shared_query_cache.get_or_set(
            cache_key,
            settings.shared_query_cache_seconds,
            producer,
        )
        candles = [MarketCandle(**row) for row in candle_rows]
        if not persist:
            return candles
        return await self.repository.upsert_candles(candles)

    async def add_market_event(self, event: MarketEvent, instrument_ids: list[str]) -> MarketEvent:
        event.ts_ingest = datetime.now(timezone.utc)
        persisted = await self.repository.add_market_event(event)
        if instrument_ids:
            await self.repository.add_market_event_links(
                [
                    MarketEventInstrument(event_id=persisted.event_id, instrument_id=inst)
                    for inst in instrument_ids
                ]
            )
        return persisted

    async def get_gate_server_time(self) -> dict:
        return await self.gate_client.get_server_time()

    async def _require_instrument(self, instrument_id: str) -> Instrument:
        instrument = await self.repository.get_instrument(instrument_id)
        if instrument is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"instrument not found: {instrument_id}",
            )
        return instrument

    @staticmethod
    def resolve_gate_reference(instrument: Instrument) -> GateMarketRef:
        metadata = instrument.metadata_json or {}
        gate_meta = metadata.get("gateio", {}) if isinstance(metadata, dict) else {}
        venue = (instrument.venue or "").lower().replace(".", "")
        if gate_meta == {} and venue not in {"gateio", "gate", "gateiofutures"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"instrument {instrument.instrument_id} is not mapped to gateio",
            )

        product_type = str(
            gate_meta.get("product_type")
            or MarketService._infer_product_type(instrument.asset_class)
        ).lower()
        symbol = str(
            gate_meta.get("currency_pair")
            or gate_meta.get("contract")
            or gate_meta.get("symbol")
            or instrument.symbol
        )
        symbol = MarketService.normalize_gate_symbol(symbol)
        settle = str(
            gate_meta.get("settle") or instrument.settle_ccy or settings.gateio_default_settle
        ).lower()
        if product_type == "spot":
            return GateMarketRef(product_type="spot", symbol=symbol, settle=None)
        return GateMarketRef(product_type="futures", symbol=symbol, settle=settle)

    @staticmethod
    def normalize_gate_symbol(symbol: str) -> str:
        return symbol.replace("/", "_").replace("-", "_").upper()

    @staticmethod
    def _infer_product_type(asset_class: str) -> str:
        asset = asset_class.lower()
        if asset in {"spot", "crypto_spot", "token", "cash"}:
            return "spot"
        return "futures"
