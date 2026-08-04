"""Pydantic schemas for the ETF equity-curve endpoint.

The equity-curve endpoint reconstructs the historical mark-to-market value
of a user's ETF position from a user-selected start date up to today. It
does not project forward — it is a faithful historical replay.

Money is always returned as ``Decimal`` (string-friendly) so we never
accumulate float drift across thousands of trading days.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EtfEquityCurvePosition(BaseModel):
    """One position in the user's portfolio (subset of rebalance plan row)."""

    symbol: str = Field(..., description="ETF symbol e.g. '563010.SH'")
    code: str | None = Field(None, description="Bare code without market suffix")
    shares: int = Field(..., ge=0)
    cost_price: Decimal | None = None


class EtfEquityCurveRequest(BaseModel):
    """Request body for ``POST /ashare-etf/equity-curve``."""

    from_date: date | None = Field(
        None, description="Window start; defaults to 5 years back"
    )
    to_date: date | None = Field(None, description="Window end; defaults to today")
    positions: list[EtfEquityCurvePosition] = Field(default_factory=list)
    cash: Decimal = Field(Decimal("0"), ge=Decimal("0"))


class EtfEquityCurveSummary(BaseModel):
    """Aggregate stats over the requested window."""

    current_total_value: Decimal
    starting_total_value: Decimal
    peak_total_value: Decimal
    trough_total_value: Decimal
    max_drawdown_pct: Decimal  # peak → trough drawdown as negative pct
    total_return_pct: Decimal  # (current - starting) / starting
    cumulative_cost: Decimal   # starting market value (cash + Σ shares × cost)
    days_observed: int


class EtfEquityCurveMeta(BaseModel):
    """Provenance + coverage metadata. Always returned, never empty."""

    data_source: str = Field("eastmoney_kline", description="provider id")
    fetched_at: datetime
    coverage_start: date
    coverage_end: date
    missing_dates: list[date] = Field(default_factory=list)
    symbols_with_data: list[str] = Field(default_factory=list)
    symbols_missing: list[str] = Field(default_factory=list)
    source_status: Literal["ok", "stale", "partial", "unavailable"] = "ok"


class EtfEquityCurveResponse(BaseModel):
    scope: Literal["ashare-etf"] = "ashare-etf"
    from_date: date
    to_date: date
    labels: list[date] = Field(default_factory=list)
    total_value: list[Decimal] = Field(default_factory=list)
    per_symbol: dict[str, list[Decimal | None]] = Field(default_factory=dict)
    summary: EtfEquityCurveSummary
    meta: EtfEquityCurveMeta
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "EtfEquityCurveMeta",
    "EtfEquityCurvePosition",
    "EtfEquityCurveRequest",
    "EtfEquityCurveResponse",
    "EtfEquityCurveSummary",
]