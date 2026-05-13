from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ReviewRead(BaseModel):
    account_id: str
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    realized_trade_count: int
    winning_trade_count: int
    win_rate: Decimal
    pnl_ratio: Decimal
    max_drawdown: Decimal
    total_fees: Decimal
    total_realized_pnl: Decimal
    instrument_contribution: dict[str, str]
