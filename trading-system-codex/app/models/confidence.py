from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StructureConfidenceInput:
    available: bool = False
    overall_score: float = 0.0
    overall_confidence: float = 0.0
    overall_bias: str = "neutral"
    conflict_state: bool = False
    evidence_density: float = 0.0
    direction_agreement: float = 0.0
    suggested_action: str | None = None
    top_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConfidenceEngineInput:
    instrument_id: str
    timeframe: str
    data_quality_status: str
    data_quality_score: float
    missing_inputs: list[str]
    evidence_quality: str
    conflict_level: int
    state: str
    direction_score: float
    timeframe_biases: dict[str, str]
    primary_regime: str
    h4_adx: float = 0.0
    h4_bb_width: float = 0.0
    h1_bb_width: float = 0.0
    h4_obv_slope: float = 0.0
    h1_obv_slope: float = 0.0
    breakout_up: bool = False
    breakout_down: bool = False
    false_breakout: bool = False
    false_breakdown: bool = False
    funding_rate: float | None = None
    funding_zscore: float | None = None
    basis_rate: float | None = None
    basis_zscore: float | None = None
    cvd_delta: float | None = None
    open_interest_notional: float | None = None
    depth_liquidity: float | None = None
    spread_bps: float | None = None
    slippage_bps: float | None = None
    price_to_mark_deviation_bps: float | None = None
    price_to_index_deviation_bps: float | None = None
    execution_readiness: str = "blocked"
    risk_pause_trading: bool = False
    risk_reduce_size: bool = False
    structure: StructureConfidenceInput = field(default_factory=StructureConfidenceInput)


@dataclass(slots=True)
class ConfidenceComponentScore:
    raw: float
    weighted: float
    detail: dict[str, float | str | bool] = field(default_factory=dict)


@dataclass(slots=True)
class ConfidenceEngineReport:
    direction_score: float
    direction_label: str
    confidence_score: float
    confidence_label: str
    execution_score: float
    execution_label: str
    risk_score: float
    risk_label: str
    confidence_cap: float
    conflict_level: int
    evidence_quality: str
    position_multiplier: float
    recommended_action: str
    explain: list[str] = field(default_factory=list)
    components: dict[str, ConfidenceComponentScore] = field(default_factory=dict)
    risk_gates: list[str] = field(default_factory=list)
    hard_veto_triggered: bool = False

    def component_payload(self) -> dict[str, dict[str, float | str | bool]]:
        return {
            key: {
                "raw": round(item.raw, 4),
                "weighted": round(item.weighted, 4),
                **item.detail,
            }
            for key, item in self.components.items()
        }
