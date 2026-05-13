from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RecomputePnLRequest(BaseModel):
    account_id: str
    strategy_id: str | None = None
    cost_method: str = "AVG_COST"
    base_currency: str = "USD"
    formula_version: str = "v2"


class CashMovementCreate(BaseModel):
    movement_id: str
    account_id: str
    strategy_id: str | None = None
    movement_type: str
    amount: Decimal
    currency: str
    ts_event: datetime
    metadata_json: dict = Field(default_factory=dict)


class CashMovementRead(ORMModel):
    movement_id: str
    account_id: str
    strategy_id: str | None = None
    movement_type: str
    amount: Decimal
    currency: str
    ts_event: datetime
    metadata_json: dict


class FundingEventCreate(BaseModel):
    funding_id: str
    account_id: str
    strategy_id: str | None = None
    instrument_id: str
    rate: Decimal
    payment: Decimal
    currency: str
    ts_event: datetime
    metadata_json: dict = Field(default_factory=dict)


class FundingEventRead(ORMModel):
    funding_id: str
    account_id: str
    strategy_id: str | None = None
    instrument_id: str
    rate: Decimal
    payment: Decimal
    currency: str
    ts_event: datetime
    metadata_json: dict


class FXRateCreate(BaseModel):
    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str
    ts_event: datetime


class FXRateRead(ORMModel):
    fx_id: int
    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str
    ts_event: datetime


class PnLSnapshotRead(ORMModel):
    snapshot_id: str
    account_id: str
    strategy_id: str | None = None
    as_of_ts: datetime
    base_currency: str
    equity: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    funding: Decimal
    slippage_cost: Decimal
    exposure_notional: Decimal
    formula_version: str
    payload: dict
