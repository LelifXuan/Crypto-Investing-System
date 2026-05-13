from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


UTC = timezone.utc


def _dt_from_seconds(value: Any) -> datetime:
    return datetime.fromtimestamp(int(float(value)), tz=UTC)


@dataclass(slots=True)
class GateMarketRef:
    product_type: str
    symbol: str
    settle: str | None = None


@dataclass(slots=True)
class GateMarketCandle:
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


@dataclass(slots=True)
class GateFuturesTrade:
    trade_id: str | None
    ts_event: datetime
    contract: str
    price: Decimal
    size: Decimal
    side: str | None
    source: str
    payload: dict[str, Any]


@dataclass(slots=True)
class GateFuturesOrderBook:
    contract: str
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    order_book_id: int | None
    ts_event: datetime
    source: str
    payload: dict[str, Any]


@dataclass(slots=True)
class GateFuturesContractStats:
    ts_event: datetime
    contract: str
    open_interest: Decimal
    volume: Decimal
    source: str
    payload: dict[str, Any]


class GateIOPublicClient:
    def __init__(self, *, base_url: str | None = None, timeout_seconds: int | None = None) -> None:
        self.base_url = (base_url or settings.gateio_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.gateio_timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GateIOPublicClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_server_time(self) -> dict[str, Any]:
        return await self._get("/spot/time")

    async def get_spot_ticker(self, currency_pair: str) -> dict[str, Decimal]:
        payload = await self._get("/spot/tickers", params={"currency_pair": currency_pair})
        row = payload[0] if isinstance(payload, list) and payload else {}
        return {
            "last": _decimal(row.get("last")),
            "lowest_ask": _decimal(row.get("lowest_ask")),
            "highest_bid": _decimal(row.get("highest_bid")),
        }

    async def get_futures_contract(self, settle: str, contract: str) -> dict[str, Decimal]:
        row = await self._get(f"/futures/{settle}/contracts/{contract}")
        return {
            "mark_price": _decimal(row.get("mark_price")),
            "index_price": _decimal(row.get("index_price")),
            "last_price": _decimal(row.get("last_price")),
            "funding_rate": _decimal(row.get("funding_rate")),
            "order_price_round": _decimal(row.get("order_price_round")),
            "quanto_multiplier": _decimal(
                row.get("quanto_multiplier") or row.get("multiplier") or "1"
            ),
        }

    async def get_spot_candles(
        self,
        *,
        currency_pair: str,
        interval: str,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[GateMarketCandle]:
        rows = await self._get(
            "/spot/candlesticks",
            params=self._compact_params(
                currency_pair=currency_pair,
                interval=interval,
                limit=limit,
                _from=from_ts,
                to=to_ts,
            ),
        )
        candles: list[GateMarketCandle] = []
        for row in rows or []:
            candles.append(self.parse_spot_candle(row))
        return candles

    async def get_futures_candles(
        self,
        *,
        settle: str,
        contract: str,
        interval: str,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[GateMarketCandle]:
        rows = await self._get(
            f"/futures/{settle}/candlesticks",
            params=self._compact_params(
                contract=contract,
                interval=interval,
                limit=limit,
                _from=from_ts,
                to=to_ts,
            ),
        )
        candles: list[GateMarketCandle] = []
        for row in rows or []:
            candles.append(self.parse_futures_candle(row))
        return candles

    async def get_futures_contract_stats(
        self,
        *,
        settle: str,
        contract: str,
        interval: str = "5m",
        limit: int = 100,
        from_ts: int | None = None,
    ) -> list[GateFuturesContractStats]:
        rows = await self._get(
            f"/futures/{settle}/contract_stats",
            params=self._compact_params(
                contract=contract,
                interval=interval,
                limit=limit,
                _from=from_ts,
            ),
        )
        return [self.parse_futures_contract_stats(row, contract=contract) for row in rows or []]

    async def list_futures_trades(
        self,
        *,
        settle: str,
        contract: str,
        limit: int = 100,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[GateFuturesTrade]:
        rows = await self._get(
            f"/futures/{settle}/trades",
            params=self._compact_params(
                contract=contract,
                limit=limit,
                _from=from_ts,
                to=to_ts,
            ),
        )
        return [self.parse_futures_trade(row, contract=contract) for row in rows or []]

    async def get_futures_order_book(
        self,
        *,
        settle: str,
        contract: str,
        interval: str = "0",
        limit: int = 50,
        with_id: bool = True,
    ) -> GateFuturesOrderBook:
        row = await self._get(
            f"/futures/{settle}/order_book",
            params=self._compact_params(
                contract=contract,
                interval=interval,
                limit=limit,
                with_id=with_id,
            ),
        )
        return self.parse_futures_order_book(row, contract=contract)

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        client = await self._ensure_client()
        response = await client.get(f"{self.base_url}{path}", params=params)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def parse_spot_candle(row: list[Any] | dict[str, Any]) -> GateMarketCandle:
        if isinstance(row, dict):
            return GateMarketCandle(
                ts_open=_dt_from_seconds(row.get("t") or row.get("time") or row.get("timestamp")),
                volume=_decimal(row.get("v") or row.get("volume") or row.get("base_volume")),
                close=_decimal(row.get("c") or row.get("close")),
                high=_decimal(row.get("h") or row.get("high")),
                low=_decimal(row.get("l") or row.get("low")),
                open=_decimal(row.get("o") or row.get("open")),
                source="gateio:spot.candlesticks",
            )
        return GateMarketCandle(
            ts_open=_dt_from_seconds(row[0]),
            volume=_decimal(row[6] if len(row) > 6 else row[1] if len(row) > 1 else None),
            close=_decimal(row[2] if len(row) > 2 else None),
            high=_decimal(row[3] if len(row) > 3 else None),
            low=_decimal(row[4] if len(row) > 4 else None),
            open=_decimal(row[5] if len(row) > 5 else None),
            source="gateio:spot.candlesticks",
        )

    @staticmethod
    def parse_futures_candle(row: dict[str, Any] | list[Any]) -> GateMarketCandle:
        if isinstance(row, list):
            return GateMarketCandle(
                ts_open=_dt_from_seconds(row[0]),
                volume=_decimal(row[1] if len(row) > 1 else None),
                close=_decimal(row[2] if len(row) > 2 else None),
                high=_decimal(row[3] if len(row) > 3 else None),
                low=_decimal(row[4] if len(row) > 4 else None),
                open=_decimal(row[5] if len(row) > 5 else None),
                source="gateio:futures.candlesticks",
            )
        return GateMarketCandle(
            ts_open=_dt_from_seconds(row.get("t")),
            volume=_decimal(row.get("v")),
            close=_decimal(row.get("c")),
            high=_decimal(row.get("h")),
            low=_decimal(row.get("l")),
            open=_decimal(row.get("o")),
            source="gateio:futures.candlesticks",
        )

    @staticmethod
    def parse_futures_trade(
        row: dict[str, Any], *, contract: str | None = None
    ) -> GateFuturesTrade:
        size = _decimal(row.get("size") or row.get("amount") or row.get("qty"))
        side = row.get("side")
        if side is None and size != 0:
            side = "buy" if size > 0 else "sell"
        ts_value = (
            row.get("create_time_ms")
            or row.get("time_ms")
            or row.get("create_time")
            or row.get("time")
        )
        return GateFuturesTrade(
            trade_id=str(row.get("id")) if row.get("id") is not None else None,
            ts_event=_dt_from_seconds(ts_value),
            contract=str(row.get("contract") or contract or "").upper(),
            price=_decimal(row.get("price")),
            size=abs(size),
            side=str(side).lower() if side is not None else None,
            source="gateio:futures.trades",
            payload=row,
        )

    @staticmethod
    def parse_futures_order_book(
        row: dict[str, Any], *, contract: str | None = None
    ) -> GateFuturesOrderBook:
        ts_value = row.get("current") or row.get("t") or row.get("time")
        ts_value = ts_value or datetime.now(timezone.utc).timestamp()
        return GateFuturesOrderBook(
            contract=str(row.get("contract") or row.get("s") or contract or "").upper(),
            bids=GateIOPublicClient._parse_book_levels(row.get("bids") or row.get("b") or []),
            asks=GateIOPublicClient._parse_book_levels(row.get("asks") or row.get("a") or []),
            order_book_id=int(row["id"]) if row.get("id") is not None else None,
            ts_event=_dt_from_seconds(ts_value),
            source="gateio:futures.order_book",
            payload=row,
        )

    @staticmethod
    def parse_futures_contract_stats(
        row: dict[str, Any], *, contract: str | None = None
    ) -> GateFuturesContractStats:
        return GateFuturesContractStats(
            ts_event=_dt_from_seconds(row.get("time") or row.get("t")),
            contract=str(row.get("contract") or contract or "").upper(),
            open_interest=_decimal(row.get("open_interest") or row.get("open_interest_usd")),
            volume=_decimal(row.get("volume") or row.get("volume_24h") or row.get("volume_usd")),
            source="gateio:futures.contract_stats",
            payload=row,
        )

    @staticmethod
    def _parse_book_levels(levels: list[Any]) -> list[tuple[Decimal, Decimal]]:
        parsed: list[tuple[Decimal, Decimal]] = []
        for level in levels:
            if isinstance(level, dict):
                price = level.get("p") or level.get("price")
                size = level.get("s") or level.get("size") or level.get("amount")
            else:
                price = level[0] if len(level) > 0 else None
                size = level[1] if len(level) > 1 else None
            parsed.append((_decimal(price), abs(_decimal(size))))
        return parsed

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    @staticmethod
    def _compact_params(**kwargs: Any) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            params["from" if key == "_from" else key] = value
        return params
