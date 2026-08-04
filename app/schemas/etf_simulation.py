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
    # Quarter-end rebalance executes N trading days AFTER the month-end DCA.
    # 0 keeps the original behaviour (DCA + rebalance on the same trading day,
    # which underweights the post-DCA drift). Recommended 5: the rebalance
    # then sees the price drift the DCA itself introduced plus ~1 week of
    # market noise, so the ERC target gets a fairer chance to "catch up"
    # with the post-DCA shape. Cap at 20 (~1 calendar month) to prevent
    # the rebalance from drifting into the next quarter's DCA window.
    rebalance_offset_days: int = Field(
        5, ge=0, le=20,
        description="Trading days between month-end DCA and quarter-end rebalance",
    )


class EtfSimulationRequest(BaseModel):
    from_month: date = Field(..., description="First calendar month of the simulation (any day)")
    to_date: date | None = Field(None, description="End date; defaults to today")
    params: EtfSimulationParams = Field(default_factory=EtfSimulationParams)


class EtfSimulationEvent(BaseModel):
    """A single simulated event at month-end (DCA or rebalance)."""

    date: date
    # When ``rebalance_offset_days > 0``, ``date`` is the date the rebalance
    # fires (which may be in the next calendar month if offset is large).
    # ``dca_date`` always records the underlying month-end DCA that
    # triggered the offset. Both are equal when offset = 0.
    dca_date: date | None = None
    rebalance_date: date | None = None
    rebalance_offset_days: int = 0
    kind: Literal["monthly_dca", "quarterly_rebalance", "no_trigger", "monthly_dca_only"]
    cashflow_shares_added: int = 0
    halo_dca: dict[str, int] = Field(default_factory=dict)  # per-symbol shares added
    rebalance_trades: dict[str, Decimal] = Field(
        default_factory=dict
    )  # symbol -> traded notional (positive=buy, negative=sell)
    # Per-symbol rationale for why this ETF was traded. Populated only when
    # ``kind == "quarterly_rebalance"``; left empty otherwise. Schema is
    # ``{symbol: {side, target_weight, current_weight, drift_pct, notional}}``.
    # ``side`` is "buy" or "sell"; weights and drift are decimal strings.
    trade_rationale: dict[str, dict[str, str]] = Field(default_factory=dict)
    sell_count: int = 0  # number of HALO symbols sold in this event
    buy_count: int = 0   # number of HALO symbols bought in this event
    friction_cost: Decimal = Decimal("0")
    notes: str = ""


class EtfSimulationPoint(BaseModel):
    date: date
    total_value: Decimal
    cost_value: Decimal  # cumulative cost basis = cash spent on shares so far
    cash_value: Decimal  # uninvested cash (after dca + rebalance settles)
    per_symbol_shares: dict[str, int]
    per_symbol_value: dict[str, Decimal]
    # Buy-and-hold benchmark: total_value of an equal-weight lump-sum
    # position opened on the FIRST trading day of from_month, funded
    # with the same total cash that the DCA strategy eventually
    # deploys. After the opening day the position never rebalances,
    # so this curve shows what the user would have earned by skipping
    # DCA entirely and going all-in at the start.
    lump_sum_value: Decimal = Decimal("0")
    # Cash-on-cash return for the DCA strategy at this snapshot:
    # (total_value - cost_value) / cost_value. Zero when cost_value
    # is 0 (the first month-end before any DCA fires) so the line
    # starts cleanly at the origin. Quantised to 4 decimals
    # (0.01% precision) so the chart can plot it directly.
    return_pct: Decimal = Decimal("0")
    # Cash-on-cash return for the buy-and-hold lump-sum benchmark at
    # this snapshot: (lump_sum_value - lump_sum_total_cash) /
    # lump_sum_total_cash. Zero when the benchmark never opened.
    lump_sum_return_pct: Decimal = Decimal("0")


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
    # Buy-and-hold benchmark for the same total cash outlay as the
    # DCA strategy (no rebalancing after opening day).
    lump_sum_final_value: Decimal = Decimal("0")
    # DCA strategy outperformance vs the lump-sum benchmark at to_date.
    # Positive means DCA beat buy-and-hold; negative means lump-sum
    # won. Zero when the benchmark never opened (no NAV history at
    # from_month's first trading day).
    lump_sum_vs_dca_pct: Decimal = Decimal("0")


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