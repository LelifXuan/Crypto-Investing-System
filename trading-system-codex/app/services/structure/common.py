from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

LOOKBACK_BY_TIMEFRAME = {"1h": 240, "4h": 180, "1d": 180, "1w": 120, "30d": 120}
STRUCTURE_DETECTOR_VERSION = "structure-v8-stable"
SYSTEMS = ("swing", "classic", "profile")


def clamp(value: float | None, lower: float = 0.0, upper: float = 100.0) -> float:
    if value is None or value != value:
        return lower
    return max(lower, min(upper, float(value)))


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(to_float(value)))


def direction_from_score(score: float) -> str:
    if score > 0.08:
        return "bullish"
    if score < -0.08:
        return "bearish"
    return "neutral"


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def normalize_weights(
    weights: dict[str, float],
    min_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    result = dict(weights)
    if min_weights:
        for key, value in min_weights.items():
            result[key] = max(result.get(key, 0.0), value)
    total = sum(abs(value) for value in result.values())
    if total <= 0:
        return {key: 1.0 / len(result) for key in result} if result else {}
    return {key: value / total for key, value in result.items()}


def parse_timeframe_hours(timeframe: str) -> int:
    value = str(timeframe or "1d").lower()
    mapping = {"1h": 1, "4h": 4, "1d": 24, "1w": 168, "30d": 720}
    return mapping.get(value, 24)


def isoformat(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def event_name(*parts: str | None) -> str:
    suffix = ".".join(str(part) for part in parts if part)
    return f"market.structure.{suffix}" if suffix else "market.structure"


def build_structure_id(*parts: Any) -> str:
    text = ":".join(str(part) for part in parts if part is not None)
    return f"structure:{uuid5(NAMESPACE_URL, text).hex[:24]}"


def build_structure_dedupe_key(*parts: Any) -> str:
    return ":".join(str(part) for part in parts if part is not None)


@dataclass(slots=True)
class Pivot:
    ts: datetime
    price: float
    kind: str
    index: int

    @property
    def pivot_type(self) -> str:
        return self.kind


@dataclass(slots=True)
class ScoreBundle:
    system: str
    direction: str
    direction_score: float
    confidence: float
    quality: float
    freshness: float
    evidence_count: int = 0
    top_reasons: list[str] = field(default_factory=list)
    conflict_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_score(self) -> float:
        return self.direction_score * self.confidence


@dataclass(slots=True)
class StructureActiveItem:
    structure_id: str
    instrument_id: str
    timeframe: str
    snapshot_version: str
    system: str
    structure_type: str
    display_name: str
    lifecycle_status: str
    directional_bias: str
    confidence: Decimal
    event_ts: datetime
    confirmation_ts: datetime | None
    invalidation_ts: datetime | None
    summary: str
    reasoning_json: list[str]
    key_levels_json: dict[str, Any]
    payload_json: dict[str, Any]
    is_active: bool = True


@dataclass(slots=True)
class StructureGeometry:
    geometry_id: str
    instrument_id: str
    timeframe: str
    snapshot_version: str
    system: str
    kind: str
    status: str
    visible: bool
    points_json: list[dict[str, Any]]
    labels_json: list[str]
    meta_json: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class StructureEvent:
    event_id: str
    instrument_id: str
    timeframe: str
    system: str
    event_name: str
    structure_id: str | None
    bias: str
    status: str
    confidence: Decimal
    anchor_bar_ts: datetime
    confirmation_bar_ts: datetime | None
    event_ts: datetime
    detection_ts: datetime
    dedupe_key: str
    payload_json: dict[str, Any]


@dataclass(slots=True)
class StructureAlert:
    alert_id: str
    instrument_id: str
    timeframe: str
    snapshot_version: str
    event_id: str | None
    rule_key: str
    alert_name: str
    severity: str
    status: str
    dedupe_key: str
    title: str
    message: str
    triggered_at: datetime
    resolved_at: datetime | None
    event_payload_json: dict[str, Any]


@dataclass(slots=True)
class DetectionBundle:
    score: ScoreBundle
    active_items: list[StructureActiveItem] = field(default_factory=list)
    geometry: list[StructureGeometry] = field(default_factory=list)
    events: list[StructureEvent] = field(default_factory=list)
    alerts: list[StructureAlert] = field(default_factory=list)


@dataclass(slots=True)
class ScoringConfig:
    bullish_threshold: float = 0.25
    bearish_threshold: float = -0.25
    weak_bullish_threshold: float = 0.08
    weak_bearish_threshold: float = -0.08
    freshness_windows: dict[str, int] = field(
        default_factory=lambda: {"1h": 12, "4h": 12, "1d": 10, "1w": 8, "30d": 6}
    )
    base_weights: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "1h": {"swing": 0.35, "classic": 0.25, "profile": 0.40},
            "4h": {"swing": 0.35, "classic": 0.25, "profile": 0.40},
            "1d": {"swing": 0.40, "classic": 0.20, "profile": 0.40},
            "1w": {"swing": 0.45, "classic": 0.15, "profile": 0.40},
            "30d": {"swing": 0.45, "classic": 0.15, "profile": 0.40},
        }
    )
    regime_deltas: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "trend": {"swing": 0.05, "classic": 0.0, "profile": -0.05},
            "balance": {"swing": -0.05, "classic": 0.0, "profile": 0.05},
            "transition": {"swing": 0.0, "classic": 0.05, "profile": -0.05},
        }
    )
    min_weights: dict[str, float] = field(
        default_factory=lambda: {"swing": 0.15, "classic": 0.10, "profile": 0.20}
    )


@dataclass(slots=True)
class FusionResult:
    overall_bias: str
    overall_score: float
    overall_confidence: float
    evidence_density: float
    regime: str
    weight_template: str
    weights: dict[str, float]
    contribution_breakdown: dict[str, float]
    conflict_state: bool
    conflict_type: str | None
    dominant_side: str | None
    opposing_side: str | None
    meaning: str | None
    risk: str | None
    need_confirmation: str | None
    invalidation: str | None
    suggested_mode: str | None
    suggested_action: str | None
    invalidation_details: dict | None = None
    primary_drivers: list[str] = field(default_factory=list)
    opposing_factors: list[str] = field(default_factory=list)
    top_reasons: list[str] = field(default_factory=list)
