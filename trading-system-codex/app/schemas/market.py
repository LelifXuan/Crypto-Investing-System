from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MarkPriceCreate(BaseModel):
    instrument_id: str
    mark_price: Decimal
    source: str
    ts_event: datetime


class MarkPriceRead(ORMModel):
    mark_id: int
    instrument_id: str
    mark_price: Decimal
    source: str
    ts_event: datetime


class CandleCreate(BaseModel):
    instrument_id: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    source: str


class CandleRead(ORMModel):
    candle_id: int
    instrument_id: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str


class IndicatorCalculateRequest(BaseModel):
    instrument_id: str
    timeframe: str
    source_preference: str = "gateio"
    fetch_limit: int = 300
    persist_candles: bool = True
    price_kind: str = "last"
    ema_window: int = 14
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bbands_window: int = 20
    bbands_stddev: Decimal = Decimal("2")


class IndicatorValueRead(ORMModel):
    indicator_value_id: int
    instrument_id: str
    timeframe: str
    indicator_name: str
    params_hash: str
    ts_value: datetime
    value_json: dict


class IndicatorRefreshPolicyCreate(BaseModel):
    instrument_id: str
    timeframe: str
    price_kind: str = "last"
    source_preference: str = "gateio"
    is_enabled: bool = True
    persist_candles: bool = True
    fetch_limit: int = 300
    parameters_json: dict = Field(default_factory=dict)


class IndicatorRefreshPolicyRead(ORMModel):
    policy_id: int
    instrument_id: str
    timeframe: str
    price_kind: str
    source_preference: str
    is_enabled: bool
    persist_candles: bool
    fetch_limit: int
    parameters_json: dict
    created_at: datetime
    updated_at: datetime


class MarketEventCreate(BaseModel):
    event_id: str
    category: str
    title: str
    summary: str | None = None
    source: str
    reliability: str
    ts_event: datetime
    payload_json: dict = Field(default_factory=dict)
    instrument_ids: list[str] = Field(default_factory=list)


class MarketEventRead(ORMModel):
    event_id: str
    category: str
    title: str
    summary: str | None = None
    source: str
    reliability: str
    ts_event: datetime
    payload_json: dict
    instrument_ids: list[str] = Field(default_factory=list)


class IndicatorPoint(BaseModel):
    ts: int
    indicator: str
    value: dict | str


class IndicatorQueryResponse(BaseModel):
    instrument_id: str
    timeframe: str
    refreshed: bool = False
    last_updated_ts: int | None = None
    next_refresh_ts: int | None = None
    refresh_interval_seconds: int = 600
    points: list[IndicatorPoint]


class CandleQueryResponse(BaseModel):
    instrument_id: str
    timeframe: str
    candles: list[CandleRead]


class CacheMarkResponse(BaseModel):
    instrument_id: str
    mark_price: Decimal
    last_price: Decimal | None = None
    source: str
    ts_event: datetime
    payload: dict = Field(default_factory=dict)


class CacheBookTickerResponse(BaseModel):
    instrument_id: str
    bid_price: Decimal | None = None
    bid_size: Decimal | None = None
    ask_price: Decimal | None = None
    ask_size: Decimal | None = None
    source: str
    ts_event: datetime


class CacheCandleResponse(BaseModel):
    instrument_id: str
    timeframe: str
    ts_open: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    is_closed: bool = False
    payload: dict = Field(default_factory=dict)


class MarketEventQueryResponse(BaseModel):
    items: list[MarketEventRead]


class IndicatorDefinitionRead(ORMModel):
    indicator_key: str
    display_name: str
    category: str
    family: str
    source_provider: str
    source_kind: str
    calc_engine: str
    calc_params_json: dict
    supported_assets_json: list
    supported_timeframes_json: list
    output_fields_json: list
    signal_states_json: list
    default_thresholds_json: dict
    use_cases_json: list
    is_enabled: bool


class IndicatorObservationRead(ORMModel):
    observation_id: str
    indicator_key: str
    category: str
    instrument_id: str | None = None
    asset_code: str | None = None
    country_code: str | None = None
    timeframe: str | None = None
    observation_ts: datetime
    value_num: Decimal | None = None
    value_text: str | None = None
    value_json: dict
    baseline_num: Decimal | None = None
    delta_num: Decimal | None = None
    zscore_num: Decimal | None = None
    percentile_num: Decimal | None = None
    signal_state: str | None = None
    signal_score: Decimal | None = None
    source_provider: str
    source_ref: str | None = None
    source_granularity: str | None = None
    is_preliminary: bool
    quality_score: Decimal
    run_id: str | None = None


class MonitoringPolicyRead(ORMModel):
    policy_id: str
    indicator_key: str
    scope_type: str
    instrument_id: str | None = None
    asset_code: str | None = None
    timeframe: str | None = None
    mode: str
    interval_seconds: int | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    event_key: str | None = None
    calendar_source: str | None = None
    release_key: str | None = None
    fallback_interval_seconds: int | None = None
    priority: int
    is_enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class AlertRuleRead(ORMModel):
    rule_key: str
    indicator_key: str
    enabled: bool
    severity: str
    category: str
    scope_type: str
    condition_type: str
    comparator: str | None = None
    threshold_num: Decimal | None = None
    lower_threshold_num: Decimal | None = None
    upper_threshold_num: Decimal | None = None
    state_value: str | None = None
    percentile_ref_window_points: int | None = None
    consecutive_points: int | None = None
    dedupe_window_seconds: int
    cooldown_seconds: int
    action_channels_json: list
    message_template: str
    extra_config_json: dict


class AlertEventRead(ORMModel):
    alert_event_id: str
    rule_key: str
    indicator_key: str
    observation_id: str | None = None
    severity: str
    status: str
    instrument_id: str | None = None
    asset_code: str | None = None
    timeframe: str | None = None
    triggered_at: datetime
    resolved_at: datetime | None = None
    title: str
    message: str
    event_payload_json: dict


class AlertEventStatusUpdate(BaseModel):
    status: str


class MacroEventCalendarRead(ORMModel):
    event_id: str
    provider_key: str
    event_key: str
    country_code: str
    title: str
    scheduled_at: datetime
    actual_value_num: Decimal | None = None
    consensus_value_num: Decimal | None = None
    previous_value_num: Decimal | None = None
    surprise_num: Decimal | None = None
    importance: str
    status: str
    source_ref: str | None = None
    payload_json: dict


class MonitoringSyncResponse(BaseModel):
    runs: list[dict]


class IndicatorRefreshRequest(BaseModel):
    instrument_id: str = "btc-usdt-perp"
    timeframe: str | None = None
    fetch_limit: int = 300
    persist_candles: bool = True
    source_preference: str = "gateio"
    price_kind: str = "last"


class DivergenceSignalRead(BaseModel):
    indicator: str | None = None
    type: str | None = None
    direction: str | None = None
    tone: str
    title: str
    message: str
    weight: float | None = None
    strength: float | None = None
    recency: float | None = None
    score: float | None = None
    trend_context: str | None = None
    confirmation: str | None = None
    invalidation: str | None = None
    cooldown: int | None = None
    dedupe_key: str | None = None
    event_ts: datetime | None = None


class DivergenceOverallRead(BaseModel):
    tone: str
    title: str
    score: float
    confidence: float
    leaders: list[str] = Field(default_factory=list)
    message: str
    trend_context: str | None = None
    instrument_id: str | None = None
    timeframe: str | None = None


class DivergenceSummaryRead(BaseModel):
    instrument_id: str
    timeframe: str
    overall: DivergenceOverallRead
    signals: list[DivergenceSignalRead] = Field(default_factory=list)
    filters: list[DivergenceSignalRead] = Field(default_factory=list)
    trend_context: str | None = None
    generated_at: datetime


class ChipStructureEvidenceRead(BaseModel):
    key: str
    label: str
    value: str
    impact: str
    summary: str


class ChipStructureTimeframeRead(BaseModel):
    timeframe: str
    regime: str
    bias: str
    range_position: str
    summary: str
    confidence_score: float
    status: str
    evidence: list[str] = Field(default_factory=list)


class ChipStructureDataQualityRead(BaseModel):
    status: str
    score: float
    issues: list[str] = Field(default_factory=list)
    can_analyze: bool = True
    can_alert: bool = True


class ChipStructureRead(BaseModel):
    instrument_id: str
    timeframe: str
    state: str
    state_label: str
    state_reason: str
    primary_regime: str
    primary_regime_label: str | None = None
    evidence_quality: str = "proxy_only"
    weekly_context: str
    daily_bias: str
    h4_structure: str
    h1_confirmation: str
    direction_score: float
    direction_label: str = "neutral"
    confidence_score: float
    confidence_label: str = "invalid"
    execution_score: float = 0.0
    execution_label: str = "blocked"
    risk_score: float = 100.0
    risk_label: str = "extreme"
    confidence_cap: float = 0.0
    conflict_level: int
    position_multiplier: float
    capital_allocation_pct_min: float
    capital_allocation_pct_max: float
    capital_allocation_label: str
    position_sizing_reason: str
    spot_allocation_pct_min: float
    spot_allocation_pct_max: float
    futures_allocation_pct_min: float
    futures_allocation_pct_max: float
    probe_position_pct_max: float
    spot_allocation_label: str
    futures_allocation_label: str
    probe_position_label: str
    allocation_reason: str
    direction_permission: str
    capital_ceiling_pct: float
    execution_readiness: str
    recommended_action: str
    recommended_action_v2: str = "no_trade"
    entry_confirmation_required: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    data_quality: ChipStructureDataQualityRead
    missing_inputs: list[str] = Field(default_factory=list)
    evidence: list[ChipStructureEvidenceRead] = Field(default_factory=list)
    risk_gates: list[str] = Field(default_factory=list)
    components: dict = Field(default_factory=dict)
    explain: list[str] = Field(default_factory=list)
    timeframes: list[ChipStructureTimeframeRead] = Field(default_factory=list)
    generated_at: datetime


class RiskEvaluationRequest(BaseModel):
    instrument_id: str
    timeframe: str = "1h"
    entry_price: Decimal
    equity: Decimal
    leverage: Decimal = Decimal("1")
    requested_notional: Decimal = Decimal("0")
    current_total_exposure: Decimal = Decimal("0")
    liquidation_price: Decimal | None = None
    data_quality_ok: bool = True


class RiskEvaluationRead(BaseModel):
    recommended_position_notional: Decimal
    recommended_stop_distance: Decimal
    allowed_to_trade: bool
    reasons: list[str] = Field(default_factory=list)
    reduce_size: bool
    pause_trading: bool


class MacroOverviewIndicatorRead(BaseModel):
    indicator_key: str
    label: str
    display_code: str | None = None
    display_label: str | None = None
    unit: str = ""
    tooltip: str
    region: str = "global"
    source_provider: str | None = None
    value_num: Decimal | None = None
    value_text: str | None = None
    observation_ts: datetime | None = None
    signal_state: str | None = None
    status: str = "missing"
    fallback_level: str | None = None
    is_scored: bool = False
    score_block_reason: str | None = None
    status_reason: str | None = None
    insight: str
    event_title: str | None = None
    event_status: str | None = None
    scheduled_at: datetime | None = None
    actual_value_num: Decimal | None = None
    consensus_value_num: Decimal | None = None
    previous_value_num: Decimal | None = None
    surprise_num: Decimal | None = None


class MacroOverviewEventRead(BaseModel):
    event_id: str
    event_key: str
    title: str
    country_code: str
    importance: str
    status: str
    scheduled_at: datetime
    actual_value_num: Decimal | None = None
    consensus_value_num: Decimal | None = None
    previous_value_num: Decimal | None = None
    surprise_num: Decimal | None = None
    window_label: str
    summary: str


class MacroOverviewLayerRead(BaseModel):
    layer_key: str
    label_cn: str
    score: int
    bias: str
    summary: str
    effective_count: int = 0
    total_count: int = 0
    missing_count: int = 0
    stale_count: int = 0
    cached_count: int = 0
    is_scored: bool = True
    not_scored_reason: str | None = None
    indicators: list[MacroOverviewIndicatorRead] = []
    contribution: float = 0


class MacroOverviewResponse(BaseModel):
    regime_key: str
    regime_label_cn: str
    regime_summary: str
    policy_score: int
    inflation_score: int
    growth_score: int
    liquidity_score: int
    total_score: int = 0
    score_scale: str = "0 ~ 100"
    score_band: str = "中性震荡"
    score_explanation: str = ""
    confidence: str = "low"
    data_completeness: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    layer_contributions: dict[str, float] = Field(default_factory=dict)
    operation_bias: str = "observe"
    event_window_status: str = ""
    event_window_summary: str = ""
    next_event_title: str | None = None
    next_event_at: datetime | None = None
    event_items: list[MacroOverviewEventRead] = []
    layers: list[MacroOverviewLayerRead] = []


class BundleMetaRead(BaseModel):
    status: str = "missing"
    cache_state: str = "missing"
    snapshot_at: datetime | None = None
    data_ts: datetime | None = None
    source_updated_at: datetime | None = None
    expires_at: datetime | None = None
    source_version: str = "v2"
    cost_ms: int | None = None
    refreshed: bool = False
    status_message: str | None = None


class AnalysisBundleRead(BundleMetaRead):
    instrument_id: str
    timeframe: str
    view_window: str
    candles: list[CandleRead] = Field(default_factory=list)
    mark: MarkPriceRead | None = None
    contract_snapshot: dict = Field(default_factory=dict)
    core_indicator_series: dict = Field(default_factory=dict)
    secondary_indicator_series: dict = Field(default_factory=dict)
    final_decision: dict = Field(default_factory=dict)


class AlertsBundleRead(BundleMetaRead):
    instrument_id: str
    timeframe: str
    chip_structure: ChipStructureRead | None = None
    divergence_summary: DivergenceSummaryRead | None = None
    alert_events: list[AlertEventRead] = Field(default_factory=list)
    final_decision: dict = Field(default_factory=dict)
    contract_snapshot: dict = Field(default_factory=dict)


class MonitoringDashboardRead(BundleMetaRead):
    instrument_id: str
    timeframe: str
    macro_overview: MacroOverviewResponse | None = None
    terminal_summary: dict[str, Any] | None = None
    technical_observations: list[IndicatorObservationRead] = Field(default_factory=list)
    technical_indicator_count: int = 0
    alert_events: list[AlertEventRead] = Field(default_factory=list)
    cross_asset: list[dict] = Field(default_factory=list)
    source_status: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PrecomputeHintRequest(BaseModel):
    current_page: str
    instrument_id: str | None = None
    timeframe: str | None = None
    view_window: str | None = None
    reason: str | None = None
    visible: bool = True
    candidates: list[str] = Field(default_factory=list)
    priority: int = 5


class PrecomputeHintResponse(BaseModel):
    status: str
    accepted: int = 0
    queued: int = 0
    deduped: int = 0
    queue_depth: int = 0
    queued_keys: list[str] = Field(default_factory=list)


class PrecomputeStatusRead(BaseModel):
    queue_depth: int
    running_task: dict | None = None
    lane_counters: dict = Field(default_factory=dict)
    recent_failures: list[dict] = Field(default_factory=list)


class PrecomputeTaskRead(BaseModel):
    task_key: str
    status: str
    lane: str | None = None
    priority_level: str | None = None
    score: int | None = None
    cache_key: str | None = None
    task_type: str | None = None
    instrument_id: str | None = None
    timeframe: str | None = None
    reason: str | None = None
    visible: bool | None = None
    current_page: str | None = None
    last_error: str | None = None
