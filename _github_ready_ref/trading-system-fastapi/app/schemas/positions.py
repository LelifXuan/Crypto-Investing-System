from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FillCreate(BaseModel):
    fill_id: str
    source: str
    order_id: str | None = None
    account_id: str
    strategy_id: str | None = None
    instrument_id: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str
    liquidity: str = "UNKNOWN"
    ts_event: datetime
    raw_payload: dict = Field(default_factory=dict)


class FillRead(ORMModel):
    fill_id: str
    source: str
    account_id: str
    strategy_id: str | None = None
    instrument_id: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    liquidity: str
    ts_event: datetime


class PositionViewRead(ORMModel):
    account_id: str
    strategy_id: str | None = None
    instrument_id: str
    cost_method: str
    net_qty: Decimal
    avg_cost_price: Decimal
    gross_notional: Decimal
    realized_pnl_json: dict
    unrealized_pnl_json: dict
    margin_used: Decimal
    leverage: Decimal
    updated_at: datetime


class RebuildPositionRequest(BaseModel):
    account_id: str
    instrument_id: str | None = None
    strategy_id: str | None = None
    cost_method: str = "AVG_COST"
