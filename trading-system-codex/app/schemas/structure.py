from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.market import CandleRead

SUPPORTED_STRUCTURE_TIMEFRAMES = ["1h", "4h", "1d", "1w", "1M", "30d"]


class StructurePoint(BaseModel):
    ts: datetime
    price: float
    label: str | None = None


class StructureOverallJudgementRead(BaseModel):
    overall_bias: str
    score: float
    confidence: float
    overall_score: float | None = None
    overall_confidence: float | None = None
    regime: str | None = None
    weight_template: str | None = None
    weights: dict[str, float] = Field(default_factory=dict)
    conflict_state: bool = False
    conflict_type: str | None = None
    dominant_side: str | None = None
    opposing_side: str | None = None
    meaning: str | None = None
    risk: str | None = None
    mode: str | None = None
    need_confirmation: str | None = None
    invalidation: str | None = None
    suggested_mode: str | None = None
    suggested_action: str | None = None
    contribution_breakdown: dict[str, float] = Field(default_factory=dict)
    primary_drivers: list[str] = Field(default_factory=list)
    opposing_factors: list[str] = Field(default_factory=list)
    text_decision: dict | None = None
    last_updated_at: datetime
    detection_latency_ms: int = 0
    timeframe: str


class StructureSystemJudgementRead(ORMModel):
    system: str
    bias: str
    score: float
    confidence: float
    direction: str | None = None
    direction_score: float | None = None
    quality: float | None = None
    freshness: float | None = None
    effective_score: float | None = None
    evidence_count: int = 0
    weight: float | None = None
    weighted_contribution: float | None = None
    top_reasons: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    status: str
    drivers_json: list[str]
    opposing_factors_json: list[str]
    active_structures_json: list[str]
    generated_at: datetime


class StructureActiveItemRead(ORMModel):
    structure_id: str
    system: str
    structure_type: str
    display_name: str
    lifecycle_status: str
    directional_bias: str
    confidence: float
    event_ts: datetime
    confirmation_ts: datetime | None = None
    invalidation_ts: datetime | None = None
    summary: str | None = None
    reasoning_json: list[str]
    key_levels_json: dict
    payload_json: dict
    is_active: bool


class StructureGeometryRead(ORMModel):
    geometry_id: str
    system: str
    kind: str
    status: str
    visible: bool
    points_json: list[dict]
    labels_json: list[str] | None = None
    meta_json: dict | None = None
    created_at: datetime


class StructureEventRead(ORMModel):
    event_id: str
    system: str
    event_name: str
    structure_id: str | None = None
    bias: str
    status: str
    confidence: float
    anchor_bar_ts: datetime | None = None
    confirmation_bar_ts: datetime | None = None
    event_ts: datetime
    detection_ts: datetime
    payload_json: dict


class StructureAlertRead(ORMModel):
    alert_id: str
    rule_key: str
    alert_name: str
    severity: str
    status: str
    title: str
    message: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    event_payload_json: dict


class StructureDiagnosticsRead(BaseModel):
    detector_version: str
    compute_mode: str
    candles_loaded: int
    profile_precision: str
    geometry_count: int
    event_count: int
    alert_count: int
    latest_event_name: str | None = None
    generated_at: datetime
    notes: list[str] = Field(default_factory=list)


class StructureTabSnapshotRead(BaseModel):
    instrument_id: str
    timeframe: str
    snapshot_version: str
    detector_version: str
    generated_at: datetime
    overall: StructureOverallJudgementRead
    systems: list[StructureSystemJudgementRead] = Field(default_factory=list)
    active_items: list[StructureActiveItemRead] = Field(default_factory=list)
    geometry: list[StructureGeometryRead] = Field(default_factory=list)
    diagnostics: StructureDiagnosticsRead | None = None
    classic_patterns: dict | None = None


class StructureRefreshResponse(BaseModel):
    instrument_id: str
    timeframe: str
    snapshot_version: str
    generated_at: datetime
    refreshed: bool = True
    systems: list[str] = Field(default_factory=list)


class StructureTabBundleRead(BaseModel):
    snapshot: StructureTabSnapshotRead | None = None
    candles: list[CandleRead] = Field(default_factory=list)
    events: list[StructureEventRead] = Field(default_factory=list)
    alerts: list[StructureAlertRead] = Field(default_factory=list)
    diagnostics: StructureDiagnosticsRead | None = None
    cache_state: str = "ready"
    is_stale: bool = False
    status_message: str | None = None
    last_candle_ts: datetime | None = None
    freshness_lag_seconds: int | None = None
    freshness_state: str = "unknown"
    freshness_message: str | None = None
