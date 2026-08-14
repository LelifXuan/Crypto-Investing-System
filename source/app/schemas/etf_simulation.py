"""Pydantic schemas for the ETF strategy-simulation endpoint.

Unlike the equity-curve endpoint (which is a faithful historical mark-to-
market replay of an existing portfolio), this endpoint **simulates** the
ETF 资金投入 strategy from a user-selected start month, following the
execution rules in 《ETF Rolling-252 Cov 策略与资金投入说明书》(定稿
2026-08-06):

- 初始建仓一次: first trading day, deploy ``initial_capital`` towards the
  confirmed target weights (fixed, research-output weights — NOT a rolling
  ERC solve), snapping to whole lots, keeping at least ``min_cash_reserve``.
- 定投只买不卖: each DCA period (calendar week or month per ``frequency``)
  add ``period_amount`` of cash, then buy ONLY the under-allocated ETFs
  (largest deficit first); never sell. If no whole lot can be afforded,
  HOLD and roll cash to the next period.
- 季末调仓: after the quarter-end DCA is booked, review drift against the
  per-symbol bandwidth ``max(target_weight × bandwidth_pct,
  bandwidth_floor_pp)``; when any symbol is beyond its band, sell the
  overweight symbols first (down to a target whole-lot share), then buy
  the underweight ones. No bandwidth breach → no sell.
- 整手、费用与现金: all orders are 100-share lots; commissions
  ``max(notional × commission_rate, min_commission)`` and slippage are
  deducted from cash; cash never drops below ``min_cash_reserve``.

``cost_value`` in the snapshot is the cumulative cash DEPLOYED INTO THE
PORTFOLIO (initial_capital + every period_amount), not the share purchase
cost, so the yield view ``return_pct = (total_value − cost_value) /
cost_value`` is a cash-on-cash return on invested capital — the convention
the front-end yield chart plots.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Confirmed target weights from the strategy spec (表1, 定稿 2026-08-06).
# Research only outputs the final weights; the simulation replays them
# across the whole window (no historical weight versions).
DEFAULT_TARGET_WEIGHTS: dict[str, Decimal] = {
    "561560": Decimal("0.2500"),  # 电力
    "159930": Decimal("0.1898"),  # 能源
    "512400": Decimal("0.1059"),  # 有色金属
    "516950": Decimal("0.1908"),  # 基建
    "512660": Decimal("0.1435"),  # 军工
    "563010": Decimal("0.1200"),  # 电信主题
}

# Per-symbol effective bandwidth = max(weight × 20%, 2.5pp) — matches the
# spec's 表1 bandwidth column (5.00% / ≈3.80% / 2.50% / ≈3.82% / ≈2.87% /
# 2.50%).
DEFAULT_BANDWIDTHS: dict[str, Decimal] = {
    "561560": Decimal("0.0500"),
    "159930": Decimal("0.0380"),
    "512400": Decimal("0.0250"),
    "516950": Decimal("0.0382"),
    "512660": Decimal("0.0287"),
    "563010": Decimal("0.0250"),
}


class EtfSimulationParams(BaseModel):
    """Strategy parameters exposed to the user (mirrors xlsx INPUTS tab).

    The defaults reflect the execution file of 定稿 2026-08-06: fixed
    target weights, fixed-frequency DCA (week or month per ``frequency``)
    of ``period_amount``, quarter-end bandwidth review, whole-lot trading
    with commissions + slippage and a minimum cash reserve.

    Full strategy (2026-08-07): every DCA period's cash is split between
    the HALO basket (6 ETFs — weekly DCA + quarterly rebalance) and the
    cashflow ETF 159201 (weekly DCA only: buy-only, never rebalanced,
    never sold) at ``cashflow_ratio : 1`` (default 6:1). See
    ``cashflow_ratio`` for the split arithmetic.
    """

    # 资金投入
    initial_capital: Decimal = Field(
        Decimal("100000"), gt=Decimal("0"),
        description="初始建仓资金(一次性,按目标权重建仓)",
    )
    period_amount: Decimal = Field(
        Decimal("5000"), ge=Decimal("0"),
        description="每期定投金额(月定投=每月,周定投=每周);0 表示不定投",
    )
    # 每周/每期资金按 HALO:现金流 = cashflow_ratio:1 拆分(默认 6:1):
    #   cashflow_amount = period_amount / (cashflow_ratio + 1)
    #   halo_amount     = period_amount − cashflow_amount
    # 现金流部分只买入 159201(现金流ETF),不参与季末调仓、永不卖出。
    cashflow_ratio: Decimal = Field(
        Decimal("6"), gt=Decimal("0"), le=Decimal("100"),
        description="HALO 部分与现金流 ETF 部分的每周资金比例(HALO:现金流=ratio:1,默认 6:1)",
    )
    # 周定投与月定投只是资金到账频率的区别;首次建档后保持固定(说明书§2.2/表0)。
    frequency: Literal["week", "month"] = Field(
        "month",
        description="定投频率:月定投(默认)或周定投(每周最后一个交易日)",
    )
    lot_size: int = Field(100, ge=1, description="每手份额(默认 100 份)")

    # 目标权重与带宽
    target_weights: dict[str, Decimal] = Field(
        default_factory=lambda: dict(DEFAULT_TARGET_WEIGHTS),
        description="研究确认的目标权重(表1);合计必须=1",
    )
    bandwidth_pct: Decimal = Field(
        Decimal("0.20"), gt=Decimal("0"), le=Decimal("1"),
        description="带宽 = 目标权重 × bandwidth_pct,再与 floor 取大",
    )
    bandwidth_floor_pp: Decimal = Field(
        Decimal("0.025"), gt=Decimal("0"), le=Decimal("0.5"),
        description="带宽下限(百分点,如 0.025 = 2.5pp)",
    )

    # 费用与现金约束
    commission_rate: Decimal = Field(
        Decimal("0.00025"), ge=Decimal("0"), le=Decimal("0.01"),
        description="佣金费率(万2.5)",
    )
    min_commission: Decimal = Field(
        Decimal("5"), ge=Decimal("0"),
        description="最低佣金(元/笔)",
    )
    slippage_rate: Decimal = Field(
        Decimal("0.001"), ge=Decimal("0"), le=Decimal("0.05"),
        description="滑点:买价×(1+slip),卖价×(1−slip)",
    )
    min_cash_reserve: Decimal = Field(
        Decimal("0"), ge=Decimal("0"),
        description="交易后最低保留现金",
    )

    # 季末调仓时点:资金可用当日(0)或随后 1–2 个交易日;不机械等 5/10 日。
    rebalance_offset_days: int = Field(
        0, ge=0, le=5,
        description="季末定投后 N 个交易日再复核带宽并调仓(0=当日)",
    )


class EtfSimulationRequest(BaseModel):
    from_month: date = Field(..., description="First calendar month of the simulation (any day)")
    to_date: date | None = Field(None, description="End date; defaults to today")
    params: EtfSimulationParams = Field(default_factory=EtfSimulationParams)


class EtfSimulationEvent(BaseModel):
    """A single simulated event at month-end (DCA and/or rebalance)."""

    date: date
    # When ``rebalance_offset_days > 0``, ``date`` is the date the rebalance
    # fires (which may be in the next calendar month if offset is large).
    # ``dca_date`` always records the underlying month-end DCA that
    # triggered the offset. Both are equal when offset = 0.
    dca_date: date | None = None
    rebalance_date: date | None = None
    rebalance_offset_days: int = 0
    kind: Literal[
        "monthly_dca", "weekly_dca", "quarterly_rebalance", "no_trigger",
        "monthly_dca_only", "quarterly_topup",
    ]
    # Cash added to the account this period (``period_amount``), then
    # spent (partially or fully) on under-allocated ETFs.
    dca_cash_added: Decimal = Decimal("0")
    # Per-symbol SHARES bought by the DCA this month (empty = HOLD).
    dca_trades: dict[str, Decimal] = Field(
        default_factory=dict
    )  # symbol -> notional spent (positive = buy)
    halo_dca: dict[str, int] = Field(default_factory=dict)  # per-symbol shares added
    # Cashflow-ETF (159201) leg of this DCA period: cash booked into the
    # cashflow pool, shares actually bought (whole lots), notional spent.
    # The cashflow leg never rebalances and never sells.
    cashflow_cash_added: Decimal = Decimal("0")
    cashflow_shares_added: int = 0
    cashflow_notional: Decimal = Decimal("0")
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
    friction_cost: Decimal = Decimal("0")  # commissions + slippage this event
    notes: str = ""


class EtfSimulationPoint(BaseModel):
    date: date
    total_value: Decimal
    # Cumulative cash DEPLOYED into the portfolio: initial_capital + every
    # period_amount booked up to this snapshot. NOT the share purchase
    # cost — sells do not reduce it (money already invested).
    cost_value: Decimal
    cash_value: Decimal  # uninvested HALO cash (after dca + rebalance settles)
    per_symbol_shares: dict[str, int]
    per_symbol_value: dict[str, Decimal]
    # Cashflow-ETF (159201) sleeve: market value, whole-lot shares + its
    # dedicated cash pool. The sleeve is funded by the cashflow leg of
    # every DCA period (HALO:cashflow = cashflow_ratio:1) and is never
    # rebalanced/sold.
    cashflow_value: Decimal = Decimal("0")
    cashflow_shares: int = 0
    cashflow_cash_value: Decimal = Decimal("0")
    # Buy-and-hold benchmark: total_value of a lump-sum position opened on
    # the FIRST trading day of from_month with the same TOTAL cash
    # (initial_capital + all monthly amounts), allocated at the target
    # weights. After the opening day the position never rebalances, so
    # this curve shows what the user would have earned by skipping DCA
    # entirely and going all-in at the start.
    lump_sum_value: Decimal = Decimal("0")
    # Cash-on-cash return on invested capital for the DCA strategy at this
    # snapshot: (total_value - cost_value) / cost_value. Zero when
    # cost_value is 0 (the first month-end before the initial build fires)
    # so the line starts cleanly at the origin. Quantised to 4 decimals
    # (0.01% precision) so the chart can plot it directly.
    return_pct: Decimal = Decimal("0")
    # Cash-on-cash return for the buy-and-hold lump-sum benchmark at this
    # snapshot: (lump_sum_value - lump_sum_total_cash) /
    # lump_sum_total_cash. Zero when the benchmark never opened.
    lump_sum_return_pct: Decimal = Decimal("0")


class EtfSimulationSummary(BaseModel):
    final_total_value: Decimal
    final_cost_value: Decimal
    final_cash_value: Decimal = Decimal("0")
    # Cashflow-ETF (159201) sleeve at to_date: market value, whole-lot
    # shares, and its dedicated cash pool.
    final_cashflow_value: Decimal = Decimal("0")
    final_cashflow_shares: int = 0
    final_cashflow_cash: Decimal = Decimal("0")
    peak_total_value: Decimal
    trough_total_value: Decimal
    max_drawdown_pct: Decimal
    total_return_pct: Decimal
    rebalance_count: int
    # 季末加码次数(quarterly_topup):欠配符号在季末补买至目标权重,无卖出。
    # 与 rebalance_count(必须含卖出的调仓)分离,2026-08-11 方案 A。
    quarterly_topup_count: int = 0
    cumulative_friction: Decimal
    months_simulated: int
    # Buy-and-hold benchmark for the same total cash outlay as the DCA
    # strategy (no rebalancing after opening day).
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
    # Optional weekly-granularity trail. ``weeks`` is the ISO-week label
    # for each ``weekly_series`` point (e.g. ``2026-W27``). Populated by
    # the simulation engine alongside ``series`` so the frontend can
    # render the equity curve at weekly x-axis granularity with one
    # weekly mark-to-market snapshot per ISO week. Optional for backward
    # compatibility with clients / caches that predate this field.
    weeks: list[date] | None = Field(
        default=None,
        description="Snapshot dates for the weekly mark-to-market trail "
        "(one entry per ISO week; aligns 1:1 with ``weekly_series``). "
        "Absent when the simulation did not emit weekly snapshots.",
    )
    weekly_series: list[EtfSimulationPoint] | None = Field(
        default=None,
        description="Weekly mark-to-market snapshots (pure valuation, no "
        "extra trading activity). One snapshot per ISO week, taken on the "
        "latest funding date within that week. Absent when weekly "
        "granularity was not produced.",
    )


__all__ = [
    "DEFAULT_BANDWIDTHS",
    "DEFAULT_TARGET_WEIGHTS",
    "EtfSimulationEvent",
    "EtfSimulationMeta",
    "EtfSimulationParams",
    "EtfSimulationPoint",
    "EtfSimulationRequest",
    "EtfSimulationResponse",
    "EtfSimulationSummary",
]
