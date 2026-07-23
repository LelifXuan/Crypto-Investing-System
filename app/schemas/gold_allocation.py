from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class GoldPortfolioInput(BaseModel):
    total_portfolio_value: float | None = Field(default=None, gt=0)
    total_value: float | None = Field(default=None, gt=0)
    current_gold_value: float = Field(ge=0)
    monthly_new_cash: float = Field(default=0, ge=0)
    current_gold_cost: float | None = Field(default=None, ge=0)
    is_quarterly_rebalance_month: bool = False
    crypto_weight: float | None = Field(default=None, ge=0)
    us_equity_weight: float | None = Field(default=None, ge=0)
    us_stock_weight: float | None = Field(default=None, ge=0)
    a_share_weight: float | None = Field(default=None, ge=0)
    ashare_weight: float | None = Field(default=None, ge=0)
    halo_etf_weight: float | None = Field(default=None, ge=0)
    cashflow_etf_weight: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_total_value(self) -> "GoldPortfolioInput":
        if self.total_portfolio_value is None and self.total_value is None:
            raise ValueError("total_portfolio_value or total_value is required")
        return self


class GoldAllocationOptions(BaseModel):
    base_currency: str = "元"
    allow_quarterly_sell: bool = True
    max_monthly_gold_cash_fraction: float = Field(default=0.6, ge=0, le=1)
    prefer_staged_execution: bool = True


class GoldAllocationPlanRequest(BaseModel):
    portfolio: GoldPortfolioInput
    options: GoldAllocationOptions = Field(default_factory=GoldAllocationOptions)
    market: dict[str, Any] | None = None
    macro: dict[str, Any] | None = None
    goldhub: dict[str, Any] | None = None


class TargetRange(BaseModel):
    min: float
    max: float


class GoldAllocationPlanResponse(BaseModel):
    allocation_state: str
    allocation_score: float
    target_range: TargetRange
    current_weight: float
    gap_to_target_min: float
    gap_above_target_max: float
    suggested_this_month: float
    execution_style: str
    primary_instruction: str
    decision_summary: str
    reasoning_steps: list[str]
    module_cards: list[dict[str, Any]]
    data_quality: dict[str, Any]
    warnings: list[str]

    target_weight_min: float
    target_weight_max: float
    gap_to_min_amount: float
    overweight_above_max_amount: float
    action: str
    suggested_this_month_amount: float
    drivers: dict[str, Any]
    summary: str
    risk_notes: list[str]
    asset_impact_summary: dict[str, str]
    gold_macro_snapshot: dict[str, Any] = Field(default_factory=dict)


class GoldQuoteInput(BaseModel):
    price: float = Field(gt=0)
    updated_at: datetime


class GoldExecutionSettingsInput(BaseModel):
    rsi_candidate: float | None = None
    rsi_strong: float | None = None
    cci_candidate: float | None = None
    cci_strong: float | None = None
    percent_b_candidate: float | None = None
    percent_b_strong: float | None = None
    return_7d_trigger: float | None = None
    return_14d_trigger: float | None = None
    drawdown_30d_trigger: float | None = None
    drawdown_60d_trigger: float | None = None
    ema20_deviation_trigger: float | None = None
    ema50_deviation_trigger: float | None = None
    candidate_min_signals: int | None = Field(default=None, ge=1)
    trigger_min_signals: int | None = Field(default=None, ge=1)


class GoldExecutionPlanRequest(BaseModel):
    symbol: str = "XAUT_USDT"
    daily_dca_amount: float = Field(default=0, ge=0)
    dip_add_amount: float = Field(default=0, ge=0)
    cooldown_days: int = Field(default=7, ge=0, le=60)
    quote_max_age_seconds: int = Field(default=172800, ge=60)
    available_cash: float | None = Field(default=None, ge=0)
    executed_today: bool = False
    last_dip_add_date: date | None = None
    last_dip_cycle_id: str | None = None
    settings: GoldExecutionSettingsInput | None = None
    quote: GoldQuoteInput | None = None
    indicators: dict[str, Any] | None = None
    candles: list[dict[str, Any]] | None = None
    now: datetime | None = None


class GoldExecutionPlanResponse(BaseModel):
    symbol: str
    as_of: str
    quote: dict[str, Any]
    daily_dca: dict[str, Any]
    dip_add: dict[str, Any]
    execution: dict[str, Any]
    indicators: dict[str, Any] | None = None
    diagnostics: dict[str, Any]


class GoldMarketStateResponse(BaseModel):
    instrument_id: str
    xaut_symbol: str
    source: str
    role: str
    timeframes: list[str]

    price: float | None = None
    ret_1d: float | None = None
    ret_7d: float | None = None
    ret_30d: float | None = None
    drawdown_60d: float | None = None
    natr_14: float | None = None
    volume_zscore: float | None = None
    above_ma50: bool | None = None
    above_ma200: bool | None = None
    daily_window: dict[str, Any] | None = None
    weekly_window: dict[str, Any] | None = None
    updated_at: str | None = None

    xaut_price: float | None = None
    xaut_change_7d_pct: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    natr_pct: float | None = None
    distance_to_ma50_pct: float | None = None
    drawdown_pct: float | None = None
    evidence_level: str
    data_quality_note: str
