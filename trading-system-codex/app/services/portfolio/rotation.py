from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RotationAssessment:
    relative_strength: float
    beta_hint: float
    sector_leadership: str
    volatility_adjusted_momentum: float
    correlation_risk: str
    notes: list[str] = field(default_factory=list)
