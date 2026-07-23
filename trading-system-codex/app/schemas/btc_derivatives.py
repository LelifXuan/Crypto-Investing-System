from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChartDataset(BaseModel):
    label: str
    data: list[float | None] = Field(default_factory=list)
    axis_profile: str = "generic"
    chart_type: str | None = None
    y_axis_id: str = "y"
    value_format: str | None = None
    unit: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)


class ChartAxis(BaseModel):
    profile: str = "generic"
    position: Literal["left", "right"] = "left"
    unit: str | None = None
    display_ticks: bool = True
    grid: bool = True
    include_annotations: bool = True
    baseline: float | None = None
    padding_ratio: float | None = None


class ChartPayload(BaseModel):
    id: str
    type: Literal["line", "bar", "mixed"] = "line"
    title: str
    labels: list[str] = Field(default_factory=list)
    axes: dict[str, ChartAxis] = Field(default_factory=dict)
    datasets: list[ChartDataset] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    empty_reason: str | None = None


class ChartLayoutCard(BaseModel):
    span: Literal[4, 6, 8, 12]
    density: Literal["hero", "surface", "standard", "compact"] = "standard"
    section: str


class ChartLayoutSection(BaseModel):
    id: str
    title: str
    charts: list[str] = Field(default_factory=list)


class ChartLayout(BaseModel):
    sections: list[ChartLayoutSection] = Field(default_factory=list)
    cards: dict[str, ChartLayoutCard] = Field(default_factory=dict)


class DashboardSelection(BaseModel):
    expiry_mode: Literal["fixed", "constant_maturity"] = "constant_maturity"
    maturity_bucket: Literal["30D", "60D", "90D"] = "60D"
    selected_expiry: str | None = None
    effective_expiry: str | None = None
    effective_dte: int | None = None
    selection_status: str = "ok"
    selection_reason: str = ""
    window: Literal["7D", "30D", "90D", "180D", "365D"] | None = None
    strike_range_pct: Literal["10", "20", "30", "50", "all"] = "30"


class DecisionCard(BaseModel):
    id: str
    label: str
    state: str = "neutral"
    score: float | None = None
    confidence: str = "low"
    summary: str = ""
    conclusion: str = ""
    basis: list[str] = Field(default_factory=list)
    implication: str = ""
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KeyLevelCard(BaseModel):
    id: Literal["call_wall", "put_wall", "max_pain", "constant_maturity"]
    label: str
    subtitle: str
    value: float | str | None = None
    distance_pct: float | None = None
    movement: str
    current_meaning: str
    knowledge_term: str


class KeyLevelAxisItem(BaseModel):
    id: Literal["call_wall", "put_wall", "max_pain"]
    label: str
    value: float | None = None
    previous_value: float | None = None
    shift_pct: float | None = None
    movement: str = "data_insufficient"
    distance_pct: float | None = None
    signal: str = "data_insufficient"
    bias: str = "neutral"
    confirmation: str = "unavailable"
    explanation: str = ""


class OptionsWallSignal(BaseModel):
    schema_version: str = "options_wall_signal.v1"
    status: str = "data_insufficient"
    overall_signal: str = "data_insufficient"
    bias: str = "neutral"
    confirmation: str = "unavailable"
    confidence: str = "low"
    status_label: str = ""
    spot_price: float | None = None
    previous_spot_price: float | None = None
    spot_change_pct: float | None = None
    spot_direction: str = "unknown"
    expiry_context: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    quality: str = "data_insufficient"
    comparison_basis: str = "previous_available_point"
    comparison_timestamp: str | None = None
    comparison_is_same_day: bool = False
    levels: dict[str, KeyLevelAxisItem] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    summary: str = ""
    risk_note: str = ""
    direct_command: bool = False


KeyLevelsAxis = OptionsWallSignal


class FuturesRow(BaseModel):
    exchange: str
    instrument: str
    timestamp: str
    mark_price: float | None = None
    funding_rate: float | None = None
    open_interest_usd: float | None = None
    oi_change_pct: float | None = None
    volume_24h_usd: float | None = None
    expiry: str | None = None
    basis_pct: float | None = None
    annualized_basis_pct: float | None = None


class OptionSide(BaseModel):
    bid: float | None = None
    ask: float | None = None
    mark: float | None = None
    mid: float | None = None
    spread_pct: float | None = None
    iv: float | None = None
    delta: float | None = None
    open_interest: float | None = None
    volume_24h: float | None = None
    liquidity: str = "poor"


class OptionChainRow(BaseModel):
    expiry: str
    strike: float
    call: OptionSide | None = None
    put: OptionSide | None = None


class FuturesSection(BaseModel):
    rows: list[FuturesRow] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    charts: dict[str, ChartPayload] = Field(default_factory=dict)


class OptionsSection(BaseModel):
    selected_expiry: str | None = None
    expiries: list[str] = Field(default_factory=list)
    standard_expiries: list[str] = Field(default_factory=list)
    maturity_ladder: list[dict[str, Any]] = Field(default_factory=list)
    chain: list[OptionChainRow] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    walls: dict[str, Any] = Field(default_factory=dict)
    max_pain: dict[str, Any] = Field(default_factory=dict)
    key_level_cards: list[KeyLevelCard] = Field(default_factory=list)
    charts: dict[str, ChartPayload] = Field(default_factory=dict)


class DataQuality(BaseModel):
    status: str = "data_insufficient"
    mode: str = "data_insufficient"
    providers: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    stale_snapshots: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    history_available: bool = False
    greeks_coverage: dict[str, Any] = Field(default_factory=dict)
    expiry_coverage: dict[str, Any] = Field(default_factory=dict)


class BtcDerivativesDashboardResponse(BaseModel):
    generated_at: str
    underlying: str = "BTC"
    snapshot_state: Literal["live", "stale", "data_insufficient"] = "data_insufficient"
    data_timestamp: str | None = None
    source_status: list[dict[str, Any]] = Field(default_factory=list)
    cards: list[DecisionCard] = Field(default_factory=list)
    futures: FuturesSection = Field(default_factory=FuturesSection)
    options: OptionsSection = Field(default_factory=OptionsSection)
    chart_layout: ChartLayout = Field(default_factory=ChartLayout)
    selection: DashboardSelection = Field(default_factory=DashboardSelection)
    maturity_selection: dict[str, Any] = Field(default_factory=dict)
    joint_analysis: dict[str, Any] = Field(default_factory=dict)
    hedge_context: dict[str, Any] = Field(default_factory=dict)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    indicator_judgements: list[dict[str, Any]] = Field(default_factory=list)


class HedgePlanRequest(BaseModel):
    portfolio_type: Literal["spot_only", "long_grid", "short_grid", "neutral_grid"]
    underlying: str = "BTC"
    spot_price: float = Field(gt=0)
    grid_lower: float | None = Field(default=None, gt=0)
    grid_upper: float | None = Field(default=None, gt=0)
    net_notional_usd: float = Field(default=0, ge=0)
    hedge_budget_usd: float = Field(default=0, ge=0)
    preferred_expiry_bucket: Literal["30D", "60D", "90D"] = "60D"
    allow_debit_spread: bool = True
    iv_state: str | None = None
    liquidity_state: str | None = None

    @model_validator(mode="after")
    def validate_grid_bounds(self) -> "HedgePlanRequest":
        if self.grid_lower and self.grid_upper and self.grid_lower >= self.grid_upper:
            raise ValueError("grid_lower must be lower than grid_upper")
        return self


class HedgePlanResponse(BaseModel):
    action: str
    label: str
    candidate_legs: list[dict[str, Any]] = Field(default_factory=list)
    protection_zone: str | None = None
    estimated_premium_usd: float | None = None
    budget_ok: bool | None = None
    liquidity_status: str | None = None
    warnings: list[str] = Field(default_factory=list)
    explanation: str
