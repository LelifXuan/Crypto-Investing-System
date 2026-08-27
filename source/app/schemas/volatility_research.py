from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VolatilityFeatureRead(BaseModel):
    feature_key: str
    value: str | None = None
    unit: str
    quality_status: str
    missing_reason: str | None = None
    parameters: dict = Field(default_factory=dict)


class VolatilityResearchSnapshotRead(BaseModel):
    snapshot_id: str
    instrument_id: str
    timeframe: str
    event_time: datetime
    available_at: datetime
    calculated_at: datetime
    formula_version: str
    integration_status: str
    price_volatility: dict = Field(default_factory=dict)
    options_expectations: dict = Field(default_factory=dict)
    tail_pricing: dict = Field(default_factory=dict)
    leverage_crowding: dict = Field(default_factory=dict)
    liquidation_pressure: dict = Field(default_factory=dict)
    basis_funding_structure: dict = Field(default_factory=dict)
    quality: dict = Field(default_factory=dict)
    timestamp_contract: dict = Field(default_factory=dict)
    features: list[VolatilityFeatureRead] = Field(default_factory=list)
