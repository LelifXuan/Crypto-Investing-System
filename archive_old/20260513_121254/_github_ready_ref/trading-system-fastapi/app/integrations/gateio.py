from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.core.config import settings


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
    raw_payload: dict | list


class GateIOPublicClient:
    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self.base_url = base_url or settings.gateio_base_url
        self.timeout = timeout or settings.gateio_timeout_seconds

    async def _get(self, path: str, params: dict | None = None):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get(path, params=params, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()

    async def get_server_time(self) -> dict:
        return await self._get("/spot/time")

    async def get_spot_ticker(self, currency_pair: str) -> dict:
        payload = await self._get("/spot/tickers", params={"currency_pair": currency_pair})
        if not payload:
            raise ValueError(f"gateio spot ticker not found for {currency_pair}")
        return payload[0]

    async def get_spot_candles(
        self,
        currency_pair: str,
        interval: str,
        limit: int,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[GateMarketCandle]:
        params: dict[str, str | int] = {"currency_pair": currency_pair, "interval": interval}
        if from_ts is not None or to_ts is not None:
            if from_ts is not None:
                params["from"] = from_ts
            if to_ts is not None:
                params["to"] = to_ts
        else:
            params["limit"] = limit
        payload = await self._get("/spot/candlesticks", params=params)
        return [self.parse_spot_candle(row) for row in payload]

    async def get_futures_contract(self, settle: str, contract: str) -> dict:
        return await self._get(f"/futures/{settle}/contracts/{contract}")

    async def get_futures_candles(
        self,
        settle: str,
        contract: str,
        interval: str,
        limit: int,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[GateMarketCandle]:
        params: dict[str, str | int] = {"contract": contract, "interval": interval}
        if from_ts is not None or to_ts is not None:
            if from_ts is not None:
                params["from"] = from_ts
            if to_ts is not None:
                params["to"] = to_ts
        else:
            params["limit"] = limit
        payload = await self._get(f"/futures/{settle}/candlesticks", params=params)
        return [self.parse_futures_candle(row) for row in payload]

    @staticmethod
    def parse_spot_candle(row: list[str]) -> GateMarketCandle:
        if len(row) < 7:
            raise ValueError("invalid gateio spot candle payload")
        ts_open = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
        quote_volume = Decimal(str(row[1]))
        close = Decimal(str(row[2]))
        high = Decimal(str(row[3]))
        low = Decimal(str(row[4]))
        open_ = Decimal(str(row[5]))
        base_volume = Decimal(str(row[6]))
        volume = base_volume if base_volume != 0 else quote_volume
        return GateMarketCandle(
            ts_open=ts_open,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            source="gateio:spot.candlesticks",
            raw_payload=row,
        )

    @staticmethod
    def parse_futures_candle(row: dict) -> GateMarketCandle:
        ts_open = datetime.fromtimestamp(int(row["t"]), tz=timezone.utc)
        return GateMarketCandle(
            ts_open=ts_open,
            open=Decimal(str(row["o"])),
            high=Decimal(str(row["h"])),
            low=Decimal(str(row["l"])),
            close=Decimal(str(row["c"])),
            volume=Decimal(str(row.get("v", "0"))),
            source="gateio:futures.candlesticks",
            raw_payload=row,
        )
