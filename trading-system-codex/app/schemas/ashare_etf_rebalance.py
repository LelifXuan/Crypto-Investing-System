from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PlanMode = Literal["monthly_dca", "quarterly_rebalance"]
TradeSide = Literal["BUY", "SELL", "HOLD"]
EtfStateLiteral = Literal[
    "ON_TARGET",
    "UNDERWEIGHT",
    "OVERWEIGHT",
    "BUY_PLANNED",
    "SELL_PLANNED",
    "NO_ADD",
    "LOT_BLOCKED",
    "CASH_LEFT",
    "DATA_STALE",
    "INPUT_MISSING",
]


class AShareEtfRebalancePosition(BaseModel):
    symbol: str | None = None
    code: str | None = None
    shares: int = Field(ge=0)
    cost_price: float = Field(ge=0)
    current_price: float | None = Field(default=None, gt=0)

    @field_validator("symbol", "code")
    @classmethod
    def strip_symbolish(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AShareEtfRebalancePlanRequest(BaseModel):
    mode: PlanMode = "monthly_dca"
    # Legacy / convenience fields — kept for callers that still send the
    # old 7-ETF shape.  159201.SZ in ``positions`` is filtered out server-side
    # with a warning.  Prefer the new ``halo_*`` fields.
    cash_to_invest: float = Field(default=0, ge=0)
    positions: list[AShareEtfRebalancePosition] = Field(default_factory=list)
    # New HALO-only fields
    halo_cash_to_invest: float | None = Field(default=None, ge=0)
    halo_positions: list[AShareEtfRebalancePosition] | None = None
    halo_target_weights: dict[str, float] | None = None
    # Optimizer knobs
    lot_size: int = Field(default=100, gt=0)
    tolerance_pct: float = Field(default=0.02, ge=0)
    hard_tolerance_pct: float = Field(default=0.05, ge=0)
    min_trade_amount: float = Field(default=0, ge=0)
    fee_rate: float = Field(default=0, ge=0)
    min_fee: float = Field(default=0, ge=0)
    trade_count_penalty: float = Field(default=0.0002, ge=0)
    cash_deviation_penalty: float = Field(default=0.35, ge=0)
    avoid_loss_sell_inside_hard_band: bool = True


class AShareEtfRebalanceOrder(BaseModel):
    symbol: str
    code: str
    name: str
    side: Literal["BUY", "SELL"]
    shares: int
    estimated_amount: float
    price: float
    fee_estimate: float = 0
    before_weight: float
    after_weight: float
    target_weight: float
    before_deviation: float
    after_deviation: float
    pnl_pct: float | None = None
    reason: str
    state: EtfStateLiteral | None = None


class AShareEtfRebalanceRow(BaseModel):
    symbol: str
    code: str
    name: str
    bucket: Literal["HALO", "CASHFLOW"]
    role: str
    current_shares: int
    final_shares: int
    current_price: float
    cost_price: float
    current_value: float
    final_value: float
    pnl_amount: float
    pnl_pct: float | None = None
    target_weight: float
    before_weight: float
    after_weight: float
    before_deviation: float
    after_deviation: float
    action: TradeSide
    trade_shares: int
    estimated_trade_amount: float
    fee_estimate: float = 0
    explanation: str
    state: EtfStateLiteral | None = None


class AShareEtfRebalanceCash(BaseModel):
    initial_cash_to_invest: float
    cash_left: float
    cash_weight_after: float
    target_cash_weight: float = 0


class AShareEtfRebalanceDeviationSummary(BaseModel):
    before_total_abs_deviation: float
    before_max_abs_deviation: float
    after_total_abs_deviation: float
    after_max_abs_deviation: float
    improvement_total_abs_deviation: float


class AShareEtfRebalanceExecutionConstraints(BaseModel):
    lot_size: int
    min_trade_amount: float
    fee_rate: float = 0
    min_fee: float = 0
    tolerance_pct: float
    hard_tolerance_pct: float
    exact_weight_required: bool
    rounding_policy: str


class AShareEtfRebalancePortfolio(BaseModel):
    before_total_value: float
    after_total_value: float
    turnover_amount: float
    trade_count: int


class AShareEtfExcludedEtf(BaseModel):
    symbol: str
    name: str
    reason: str


class AShareEtfRebalanceWarning(BaseModel):
    code: str
    message: str


class AShareEtfRebalancePlanResponse(BaseModel):
    scope: Literal["HALO_ONLY"] | None = None
    mode: PlanMode
    orders: list[AShareEtfRebalanceOrder]
    rows: list[AShareEtfRebalanceRow]
    cash: AShareEtfRebalanceCash
    deviation_summary: AShareEtfRebalanceDeviationSummary
    portfolio: AShareEtfRebalancePortfolio
    execution_constraints: AShareEtfRebalanceExecutionConstraints
    target_weights: dict[str, float]
    excluded_etfs: list[AShareEtfExcludedEtf] = Field(default_factory=list)
    warnings: list[AShareEtfRebalanceWarning] = Field(default_factory=list)
    notes: list[str]
