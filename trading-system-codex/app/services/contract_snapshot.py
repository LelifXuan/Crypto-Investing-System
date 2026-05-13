from __future__ import annotations

import hashlib
import json
from datetime import timezone, datetime
UTC = timezone.utc
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.integrations.gateio import GateMarketRef
from app.repositories.market_repository import MarketRepository
from app.services.cache_registry import CACHE_SOURCE_VERSION, expires_at_for_dataset
from app.services.market import MarketService


class ContractSnapshotService:
    def __init__(
        self,
        repository: MarketRepository,
        market_service: MarketService | None = None,
    ) -> None:
        self.repository = repository
        self.market_service = market_service or MarketService(repository)

    async def get_snapshot(
        self,
        instrument_id: str,
        *,
        include_book: bool = False,
        include_stats: bool = False,
        include_trades: bool = False,
        force: bool = False,
    ) -> dict:
        ref = await self._resolve_ref(instrument_id)
        settle = ref.settle or settings.gateio_default_settle
        if force:
            contract = await self.market_service.gate_client.get_futures_contract(
                settle,
                ref.symbol,
            )
        else:
            contract = await shared_query_cache.get_or_set(
                f"contract_snapshot:contract:{settle}:{ref.symbol}",
                5,
                lambda: self.market_service.gate_client.get_futures_contract(settle, ref.symbol),
            )
        payload = {
            "instrument_id": instrument_id,
            "contract": ref.symbol,
            "settle": settle,
            "last_price": self._to_string(contract.get("last_price")),
            "mark_price": self._to_string(contract.get("mark_price") or contract.get("last_price")),
            "index_price": self._to_string(contract.get("index_price")),
            "funding_rate": self._to_string(contract.get("funding_rate")),
            "basis_rate": self._basis_rate(contract),
            "ts": datetime.now(timezone.utc),
            "cache_state": "fresh",
        }
        if include_stats:
            if force:
                stats = await self.market_service.gate_client.get_futures_contract_stats(
                    settle=settle,
                    contract=ref.symbol,
                    interval="5m",
                    limit=2,
                )
            else:
                stats = await shared_query_cache.get_or_set(
                    f"contract_snapshot:stats:{settle}:{ref.symbol}",
                    30,
                    lambda: self.market_service.gate_client.get_futures_contract_stats(
                        settle=settle,
                        contract=ref.symbol,
                        interval="5m",
                        limit=2,
                    ),
                )
        if include_book:
            if force:
                book = await self.market_service.gate_client.get_futures_order_book(
                    settle=settle,
                    contract=ref.symbol,
                    limit=50,
                    with_id=True,
                )
            else:
                book = await shared_query_cache.get_or_set(
                    f"contract_snapshot:book:{settle}:{ref.symbol}",
                    5,
                    lambda: self.market_service.gate_client.get_futures_order_book(
                        settle=settle,
                        contract=ref.symbol,
                        limit=50,
                        with_id=True,
                    ),
                )
        if include_stats:
            latest_oi = stats[-1].open_interest if stats else Decimal("0")
            previous_oi = stats[-2].open_interest if len(stats) > 1 else None
            payload["open_interest"] = self._to_string(latest_oi)
            payload["open_interest_delta"] = (
                self._to_string(latest_oi - previous_oi)
                if previous_oi is not None
                else None
            )
        if include_book:
            payload["book"] = {
                "bids": [
                    [self._to_float(price), self._to_float(size)]
                    for price, size in book.bids[:10]
                ],
                "asks": [
                    [self._to_float(price), self._to_float(size)]
                    for price, size in book.asks[:10]
                ],
            }
        if include_trades:
            if force:
                trades = await self.market_service.gate_client.list_futures_trades(
                    settle=settle,
                    contract=ref.symbol,
                    limit=100,
                )
            else:
                trades = await shared_query_cache.get_or_set(
                    f"contract_snapshot:trades:{settle}:{ref.symbol}",
                    15,
                    lambda: self.market_service.gate_client.list_futures_trades(
                        settle=settle,
                        contract=ref.symbol,
                        limit=100,
                    ),
                )
            payload["trades"] = [
                {
                    "price": self._to_float(item.price),
                    "size": self._to_float(item.size),
                    "side": item.side,
                    "ts": item.ts_ms,
                }
                for item in trades
            ]
        await self._persist_component(
            instrument_id,
            "core",
            {
                key: payload.get(key)
                for key in (
                    "instrument_id",
                    "contract",
                    "settle",
                    "last_price",
                    "mark_price",
                    "index_price",
                    "funding_rate",
                    "basis_rate",
                    "ts",
                    "cache_state",
                )
            },
        )
        if include_stats:
            await self._persist_component(
                instrument_id,
                "stats",
                {
                    "instrument_id": instrument_id,
                    "contract": ref.symbol,
                    "settle": settle,
                    "open_interest": payload.get("open_interest"),
                    "open_interest_delta": payload.get("open_interest_delta"),
                    "ts": payload["ts"],
                    "cache_state": "fresh",
                },
            )
        if include_book:
            await self._persist_component(
                instrument_id,
                "book",
                {
                    "instrument_id": instrument_id,
                    "contract": ref.symbol,
                    "settle": settle,
                    "book": payload.get("book"),
                    "ts": payload["ts"],
                    "cache_state": "fresh",
                },
            )
        if include_trades:
            await self._persist_component(
                instrument_id,
                "trades",
                {
                    "instrument_id": instrument_id,
                    "contract": ref.symbol,
                    "settle": settle,
                    "trades": payload.get("trades", []),
                    "ts": payload["ts"],
                    "cache_state": "fresh",
                },
            )
        return payload

    async def _persist_component(self, instrument_id: str, component: str, payload: dict) -> None:
        await self.repository.upsert_computed_dataset_cache(
            cache_key=f"contract_snapshot_{component}:{instrument_id.lower()}:{CACHE_SOURCE_VERSION}",
            dataset_type=f"contract_snapshot_{component}",
            instrument_id=instrument_id,
            timeframe=None,
            source_data_ts=payload["ts"],
            source_hash=self._fingerprint(payload),
            payload_json=jsonable_encoder(payload),
            cache_state="fresh",
            source_version=CACHE_SOURCE_VERSION,
            calculated_at=payload["ts"],
            expires_at=expires_at_for_dataset(f"contract_snapshot_{component}"),
            meta_json={"component": component},
        )

    async def _resolve_ref(self, instrument_id: str) -> GateMarketRef:
        instrument = await self.repository.get_instrument(instrument_id)
        if instrument is None:
            raise ValueError(f"instrument not found: {instrument_id}")
        return self.market_service.resolve_gate_reference(instrument)

    @staticmethod
    def _basis_rate(contract: dict) -> str | None:
        mark = contract.get("mark_price") or contract.get("last_price")
        index = contract.get("index_price")
        if not mark or not index:
            return None
        mark_decimal = Decimal(str(mark))
        index_decimal = Decimal(str(index))
        if not index_decimal:
            return None
        return str((mark_decimal - index_decimal) / index_decimal)

    @staticmethod
    def _to_string(value) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _to_float(value) -> float:
        return float(value or 0)

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        stable = json.dumps(jsonable_encoder(payload), sort_keys=True).encode("utf-8")
        return hashlib.sha1(stable).hexdigest()
