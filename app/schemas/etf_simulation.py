"""Pydantic schemas for the ETF strategy-simulation endpoint.

Unlike the equity-curve endpoint (which is a faithful historical mark-to-
market replay of an existing portfolio), this endpoint **simulates** the
HALO rolling-252-Cov strategy from a user-selected start month:

- Start with 0 shares
- Each calendar month, dollar-cost-average 100 lots into every HALO ETF
  and 100 lots into the Cashflow ETF (no sell, no rebalance)
- At each quarter-end (last trading day of Mar/Jun/Sep/Dec), compute the
  252-day rolling covariance matrix and solve the constrained equal-risk-
  contribution target weights. Compare to current weights; if any
  individual drift exceeds the bandwidth θ (default 20%), rebalance to
  the target (selling overweight, buying underweight, with friction).
- Cashflow ETF is excluded from rebalancing entirely.

The endpoint reports the simulated portfolio over time, the rebalance
events that fired, and a summary of realised vs cumulative-cost.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EtfSimulationParams(BaseModel):
    """Strategy parameters exposed to the user (mirrors xlsx INPUTS tab)."""

    dca_lots_halo: int = Field(1, ge=0, description="Monthly lots per HALO ETF")
    dca_lots_cashflow: int = Field(1, ge=0, description="Monthly lots for cashflow ETF")
    lot_size: int = Field(100, ge=1, description="Shares per lot (default 100)")
    rebalance_bandwidth: Decimal = Field(
        Decimal("0.20"), ge=Decimal("0"), le=Decimal("1"),
        description="Drift threshold θ per symbol; trigger rebalance if any drift > θ",
    )
    single_weight_cap: Decimal = Field(Decimal("0.25"), description="Max single HALO weight")
    commodity_cap: Decimal = Field(Decimal("0.35"), description="能源+有色 cap")
    stability_floor: Decimal = Field(Decimal("0.25"), description="电力+电信 floor")
    dianxin_cap: Decimal = Field(Decimal("0.12"), description="电信(563010) cap (liquidity)")
    friction_rate: Decimal = Field(
        Decimal("0.001"), ge=Decimal("0"), le=Decimal("0.05"),
        description="Round-trip friction as fraction of traded notional",
    )
    iterations: int = Field(15, ge=1, le=50, description="ERC iterations per rebalance")


class EtfSimulationRequest(BaseModel):
    from_month: date = Field(..., description="First calendar month of the simulation (any day)")
    to_date: date | None = Field(None, description="End date; defaults to today")
    params: EtfSimulationParams = Field(default_factory=EtfSimulationParams)


class EtfSimulationEvent(BaseModel):
    """A single simulated event at month-end (DCA or rebalance)."""

    date: date
    kind: Literal["monthly_dca", "quarterly_rebalance", "no_trigger", "monthly_dca_only"]
    cashflow_shares_added: int = 0
    halo_dca: dict[str, int] = Field(default_factory=dict)  # per-symbol shares added
    rebalance_trades: dict[str, Decimal] = Field(
        default_factory=dict
    )  # symbol -> traded notional (positive=buy, negative=sell)
    friction_cost: Decimal = Decimal("0")
    notes: str = ""


class EtfSimulationPoint(BaseModel):
    date: date
    total_value: Decimal
    cost_value: Decimal  # cumulative cost basis = cash spent on shares so far
    cash_value: Decimal  # uninvested cash (after dca + rebalance settles)
    per_symbol_shares: dict[str, int]
    per_symbol_value: dict[str, Decimal]


class EtfSimulationSummary(BaseModel):
    final_total_value: Decimal
    final_cost_value: Decimal
    peak_total_value: Decimal
    trough_total_value: Decimal
    max_drawdown_pct: Decimal
    total_return_pct: Decimal
    rebalance_count: int
    cumulative_friction: Decimal
    months_simulated: int


class EtfSimulationMeta(BaseModel):
    data_source: str = "eastmoney_kline"
    fetched_at: datetime
    coverage_start: date
    coverage_end: date
    symbols_with_data: list[str] = Field(default_factory=list)
    symbols_missing: list[str] = Field(default_factory=list)
    source_status: Literal["ok", "partial", "stale", "unavailable"] = "ok"
    # Earliest date on which all HALO symbols have data — the suggested
    # default from_month for the simulation (so the user starts at the
    # first month where every HALO ETF is already trading).
    halos_listing_start: date | None = None


class EtfSimulationResponse(BaseModel):
    scope: Literal["ashare-etf"] = "ashare-etf"
    from_month: date
    to_date: date
    months: list[date] = Field(default_factory=list)
    series: list[EtfSimulationPoint] = Field(default_factory=list)
    events: list[EtfSimulationEvent] = Field(default_factory=list)
    summary: EtfSimulationSummary
    meta: EtfSimulationMeta
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "EtfSimulationEvent",
    "EtfSimulationMeta",
    "EtfSimulationParams",
    "EtfSimulationPoint",
    "EtfSimulationRequest",
    "EtfSimulationResponse",
    "EtfSimulationSummary",
]