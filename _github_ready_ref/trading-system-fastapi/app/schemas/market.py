from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MarkPriceCreate(BaseModel):
    instrument_id: str
    mark_price: Decimal
    source: str
    ts_event: datetime


class MarkPriceRead(ORMModel):
    mark_id: int
    instrument_id: str
    mark_price: Decimal
    source: str
    ts_event: datetime


class CachedMarkRead(BaseModel):
    instrument_id: str
    price: Decimal
    last_price: Decimal | None = None
    mark_price: Decimal | None = None
    source: str
    ts_event: datetime
    payload: dict = Field(default_factory=dict)


class CachedBookTickerRead(BaseModel):
    instrument_id: str
    bid_price: Decimal | None = None
    bid_size: Decimal | None = None
    ask_price: Decimal | None = None
    ask_size: Decimal | None = None
    source: str
    ts_event: datetime
    payload: dict = Field(default_factory=dict)


class CandleCreate(BaseModel):
    instrument_id: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    source: str


class CandleRead(ORMModel):
    candle_id: int
    instrument_id: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


class IndicatorCalculateRequest(BaseModel):
    instrument_id: str
    timeframe: str
    source_preference: str = "gateio"
    fetch_limit: int = 300
    persist_candles: bool = True
    price_kind: str = "last"
    sma_window: int = 14
    ema_window: int = 14
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bbands_window: int = 20
    bbands_stddev: Decimal = Decimal("2")


class IndicatorRefreshPolicyCreate(BaseModel):
    instrument_id: str
    timeframe: str
    price_kind: str = "last"
    source_preference: str = "gateio"
    is_enabled: bool = True
    persist_candles: bool = True
    fetch_limit: int = 300
    parameters_json: dict = Field(default_factory=dict)


class IndicatorRefreshPolicyRead(ORMModel):
    policy_id: int
    instrument_id: str
    timeframe: str
    price_kind: str
    source_preference: str
    is_enabled: bool
    persist_candles: bool
    fetch_limit: int
    parameters_json: dict


class IndicatorValueRead(ORMModel):
    indicator_value_id: int
    instrument_id: str
    timeframe: str
    indicator_name: str
    params_hash: str
    ts_value: datetime
    value_json: dict


class MarketEventCreate(BaseModel):
    event_id: str
    category: str
    title: str
    summary: str | None = None
    source: str
    reliability: str
    ts_event: datetime
    payload_json: dict = Field(default_factory=dict)
    instrument_ids: list[str] = Field(default_factory=list)


class MarketEventRead(ORMModel):
    event_id: str
    category: str
    title: str
    summary: str | None = None
    source: str
    reliability: str
    ts_event: datetime
    payload_json: dict


class MarketEventSyncResponse(BaseModel):
    fetched: int
    upserted: int
