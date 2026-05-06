from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScenarioResult:
    primary_scenario: str
    alternative_scenarios: list[str] = field(default_factory=list)
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    confirmation: str = ""
    invalidation: str = ""
    suggested_action: str = ""
    risk_notes: list[str] = field(default_factory=list)


class ScenarioEngine:
    def build(
        self,
        *,
        primary_scenario: str,
        evidence_for: list[str],
        evidence_against: list[str],
        confirmation: str,
        invalidation: str,
        suggested_action: str,
        alternative_scenarios: list[str] | None = None,
        risk_notes: list[str] | None = None,
    ) -> ScenarioResult:
        return ScenarioResult(
            primary_scenario=primary_scenario,
            alternative_scenarios=list(alternative_scenarios or []),
            evidence_for=list(evidence_for),
            evidence_against=list(evidence_against),
            confirmation=confirmation,
            invalidation=invalidation,
            suggested_action=suggested_action,
            risk_notes=list(risk_notes or []),
        )
