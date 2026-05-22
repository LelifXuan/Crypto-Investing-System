from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from statistics import mean
from uuid import uuid4

from fastapi import APIRouter

from app.db.models.market import (
    StructureActiveItem,
    StructureAlert,
    StructureEvent,
    StructureGeometry,
)

UTC = timezone.utc
STRUCTURE_DETECTOR_VERSION = "v2-scored-structure"
LOOKBACK_BY_TIMEFRAME = {"1h": 220, "4h": 240, "1d": 260, "1w": 260, "1M": 260}
SYSTEMS = ("swing", "classic", "profile")


@dataclass(slots=True)
class Pivot:
    ts: datetime
    price: float
    kind: str
    index: int


@dataclass(slots=True)
class ScoreBundle:
    system: str
    direction: str
    direction_score: float
    confidence: float
    quality: float
    freshness: float
    evidence_count: int
    top_reasons: list[str] = field(default_factory=list)
    conflict_flags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def effective_score(self) -> float:
        score = self.direction_score * self.confidence * self.quality * self.freshness
        if self.confidence < 0.40:
            score *= 0.6
        return clamp(score, -1.0, 1.0)


@dataclass(slots=True)
class DetectionBundle:
    score: ScoreBundle
    active_items: list[StructureActiveItem] = field(default_factory=list)
    geometry: list[StructureGeometry] = field(default_factory=list)
    events: list[StructureEvent] = field(default_factory=list)
    alerts: list[StructureAlert] = field(default_factory=list)


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
    primary_drivers: list[str]
    opposing_factors: list[str]
    top_reasons: list[str]


@dataclass(slots=True)
class ScoringConfig:
    bullish_threshold: float = 0.35
    weak_bullish_threshold: float = 0.15
    weak_bearish_threshold: float = -0.15
    bearish_threshold: float = -0.35
    freshness_windows: dict[str, int] = field(
        default_factory=lambda: {"1h": 24, "4h": 18, "1d": 12, "1w": 10, "1M": 8}
    )
    base_weights: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "1h": {"swing": 0.35, "classic": 0.25, "profile": 0.40},
            "4h": {"swing": 0.40, "classic": 0.25, "profile": 0.35},
            "1d": {"swing": 0.50, "classic": 0.20, "profile": 0.30},
            "1w": {"swing": 0.55, "classic": 0.15, "profile": 0.30},
            "1M": {"swing": 0.60, "classic": 0.10, "profile": 0.30},
        }
    )
    regime_deltas: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "trend": {"swing": 0.10, "classic": -0.05, "profile": -0.05},
            "balance": {"swing": -0.05, "classic": -0.05, "profile": 0.10},
            "transition": {"swing": -0.10, "classic": 0.05, "profile": 0.05},
        }
    )
    min_weights: dict[str, float] = field(
        default_factory=lambda: {"swing": 0.20, "classic": 0.10, "profile": 0.20}
    )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def to_decimal(value: float) -> Decimal:
    return Decimal(f"{value:.4f}")


def normalize_weights(weights: dict[str, float], minimums: dict[str, float]) -> dict[str, float]:
    adjusted = {key: max(value, minimums.get(key, 0.0)) for key, value in weights.items()}
    total = sum(adjusted.values()) or 1.0
    normalized = {key: value / total for key, value in adjusted.items()}
    return normalized


def direction_from_score(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def event_name(system: str, key: str, status: str) -> str:
    return f"market.structure.{system}.{key}.{status}"


def isoformat(dt: datetime | None) -> str:
    return dt.astimezone(UTC).isoformat() if dt is not None else ""


def parse_timeframe_hours(timeframe: str) -> float:
    mapping = {"1h": 1.0, "4h": 4.0, "1d": 24.0, "1w": 24.0 * 7, "1M": 24.0 * 30}
    return mapping.get(timeframe, 24.0)


def build_structure_id(system: str, timeframe: str, suffix: str) -> str:
    return f"{system}:{timeframe}:{suffix}:{uuid4().hex[:10]}"


def _normalize_token(value: str | None) -> str:
    if not value:
        return "na"
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value))


def build_structure_dedupe_key(*parts: str | None) -> str:
    return ":".join(_normalize_token(part) for part in parts if part is not None)


router = APIRouter(tags=["Signals"])
