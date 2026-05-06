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


class PortfolioRotationEngine:
    def assess(
        self,
        *,
        relative_strength: float,
        beta_hint: float,
        sector_leadership: str,
        volatility_adjusted_momentum: float,
        correlation: float,
    ) -> RotationAssessment:
        correlation_risk = (
            "high" if correlation >= 0.8 else "moderate" if correlation >= 0.5 else "low"
        )
        notes = []
        if relative_strength < 0:
            notes.append("相对强弱不足，适合降低优先级。")
        if volatility_adjusted_momentum < 0:
            notes.append("波动率调整后动量偏弱，追涨胜率下降。")
        if correlation_risk == "high":
            notes.append("相关性偏高，组合分散效果有限。")
        return RotationAssessment(
            relative_strength=relative_strength,
            beta_hint=beta_hint,
            sector_leadership=sector_leadership,
            volatility_adjusted_momentum=volatility_adjusted_momentum,
            correlation_risk=correlation_risk,
            notes=notes,
        )
