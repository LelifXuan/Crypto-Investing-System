from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MarketContextRead(BaseModel):
    instrument_id: str
    timeframe: str
    market_data: dict[str, Any] = Field(default_factory=dict)
    indicator_features: dict[str, Any] = Field(default_factory=dict)
    vwap_features: dict[str, Any] = Field(default_factory=dict)
    structure_features: dict[str, Any] = Field(default_factory=dict)
    derivatives_features: dict[str, Any] = Field(default_factory=dict)
    macro_features: dict[str, Any] = Field(default_factory=dict)
    event_features: dict[str, Any] = Field(default_factory=dict)
    onchain_features: dict[str, Any] = Field(default_factory=dict)
    execution_features: dict[str, Any] = Field(default_factory=dict)
    chip_structure: dict[str, Any] = Field(default_factory=dict)
    macro_overview: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    cache_meta: dict[str, Any] = Field(default_factory=dict)
