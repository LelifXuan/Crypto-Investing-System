"""Gold V3 schemas — simplified two-layer page model."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GoldSignalLight(BaseModel):
    """A single macro signal in the top panel."""
    key: str
    label: str
    code: str
    value: Optional[float] = None
    unit: str = ""
    bias: str  # strong_bullish/bullish/neutral/bearish/strong_bearish/missing
    bias_label: str
    bias_reason: str
    source: str = ""


class GoldIndicatorConfirmation(BaseModel):
    """One indicator in the 5-indicator confirmation gate."""
    label: str
    value: Optional[float] = None
    display: str
    condition: str
    passed: bool


class GoldSpotDca(BaseModel):
    """Spot DCA left column."""
    current_weight: float
    target_min: float
    target_max: float
    weight_state: str  # underweight / within_range / overweight / at_min / at_max
    base_amount: float  # x
    dip_multiplier: float  # n
    macro_gate_passed: bool
    macro_gate_reason: str
    drawdown_triggered: bool
    drawdown_60d: Optional[float] = None
    drawdown_threshold: float = 0.08
    indicator_confirmations: list[GoldIndicatorConfirmation] = Field(default_factory=list)
    confirmations_passed: int = 0
    confirmations_required: int = 3
    recommended_amount: float
    recommendation_reason: str


class GoldContractRef(BaseModel):
    """Contract reference right column."""
    price: Optional[float] = None
    above_ma50: Optional[bool] = None
    ma50_value: Optional[float] = None
    above_ma200: Optional[bool] = None
    ma200_value: Optional[float] = None
    drawdown_60d: Optional[float] = None
    natr_14: Optional[float] = None
    volume_zscore: Optional[float] = None
    oi_change_4w: Optional[float] = None
    funding_rate: Optional[float] = None
    cot_net_spec_percentile: Optional[float] = None
    derivatives_note: str = ""
    updated_at: str = ""


class GoldV3AllocationResponse(BaseModel):
    """V3 allocation endpoint response."""
    signals: list[GoldSignalLight]  # always 3: TIPS, DXY, VIX
    spot_summary: str  # one-line macro direction judgment
    liquidity_shock_detected: bool = False
    spot: GoldSpotDca
    contract: GoldContractRef
