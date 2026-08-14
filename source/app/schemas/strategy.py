from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyPositionInput(BaseModel):
    side: str = Field(default="flat")


class StrategySnapshotRequest(BaseModel):
    instrument_id: str = "btc-usdt-perp"
    timeframe: str = "1d"
    position: StrategyPositionInput = Field(default_factory=StrategyPositionInput)


class StrategyPlanRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    pattern_type: str | None = None
    pattern_label: str | None = None
    direction: str = "neutral"
    entry_condition: str | None = None
    entry_zone: list[float] | None = None
    entry_price_range: list[float] | None = None
    entry_price: float | None = None
    stop_loss_rule: str | None = None
    take_profit_rule: str | None = None
    stop_price: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    risk_reward_ratio: float | None = None
    risk_reward_1: float | None = None
    risk_reward_label: str | None = None
    capital_pct: float = 0.0
    max_leverage: float = 0.0
    strategy_logic: str | None = None
    entry_conditions: list[str] = Field(default_factory=list)
    invalidation_rules: list[str] = Field(default_factory=list)
    invalidation_criteria: list[str] = Field(default_factory=list)
    confirmation_criteria: list[str] = Field(default_factory=list)


class StrategyGateRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    severity: str
    message: str


class StrategyDecisionRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    strategy_state: str
    strategy_state_label: str | None = None
    strategy_permission: str
    strategy_permission_label: str | None = None
    strategy_bias: str
    strategy_bias_label: str | None = None
    pattern_type: str | None = None
    pattern_label: str | None = None
    long_score: float
    short_score: float
    neutral_score: float
    dominant_direction: str
    direction_confidence: float
    confidence_score: float
    execution_score: float
    risk_score: float
    data_quality_score: float
    conflict_score: float = 0.0
    components: dict[str, float] = Field(default_factory=dict)
    risk_reward: dict[str, Any] = Field(default_factory=dict)
    long_plan: StrategyPlanRead
    short_plan: StrategyPlanRead
    primary_strategy: StrategyPlanRead
    alternative_strategy: StrategyPlanRead | None = None
    backup_strategy: StrategyPlanRead | None = None
    entry_checklist: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[StrategyGateRead] = Field(default_factory=list)
    no_trade_reasons: list[str] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)
    evidence_matrix: list[dict[str, Any]] = Field(default_factory=list)
    review_tags: list[str] = Field(default_factory=list)
    explain: list[str] = Field(default_factory=list)
    generated_at: str | None = None


class StrategyBundleRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    instrument_id: str
    timeframe: str
    generated_at: datetime
    current_price: Decimal | None = None
    status: str = "ready"
    cache_state: str = "fresh"
    status_message: str = "策略信号已就绪"
    refresh_enqueued: bool = False
    snapshot_at: datetime | None = None
    data_ts: datetime | None = None
    expires_at: datetime | None = None
    source_version: str | None = None
    dependency_state: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    decision: StrategyDecisionRead
    review_summary: dict[str, Any] = Field(default_factory=dict)
    iteration_proposals: list[dict[str, Any]] = Field(default_factory=list)


class StrategySignalSaveRead(BaseModel):
    signal_key: str
    input_hash: str
    model_version: str
    config_version: str
    payload: StrategyBundleRead


class StrategySnapshotSaveRead(BaseModel):
    decision_id: str
    input_hash: str
    model_version: str
    config_version: str
    payload: StrategyBundleRead


class StrategyReviewRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    instrument_id: str | None = None
    timeframe: str | None = None
    generated_at: datetime
    total_signals: int = 0
    total_decisions: int = 0
    state_counts: dict[str, Any] = Field(default_factory=dict)
    action_counts: dict[str, Any] = Field(default_factory=dict)
    direction_counts: dict[str, Any] = Field(default_factory=dict)
    outcome_counts: dict[str, Any] = Field(default_factory=dict)
    outcome_windows: dict[str, Any] = Field(default_factory=dict)
    confidence_buckets: dict[str, Any] = Field(default_factory=dict)
    latest_signals: list[dict[str, Any]] = Field(default_factory=list)
    latest_decisions: list[dict[str, Any]] = Field(default_factory=list)
