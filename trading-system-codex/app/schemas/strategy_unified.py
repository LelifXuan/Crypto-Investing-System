from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyUnifiedRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    instrument_id: str
    generated_at: datetime | str | None = None
    status: str = "ready"
    refresh_state: str | None = None
    refresh_limitations: list[str] = Field(default_factory=list)
    snapshot_key: str | None = None
    payload_hash: str | None = None
    unified_state: dict[str, Any] = Field(default_factory=dict)
    horizon_views: dict[str, Any] = Field(default_factory=dict)
    horizon_governance: dict[str, Any] = Field(default_factory=dict)
    market_operation: dict[str, Any] = Field(default_factory=dict)
    timeframe_stack: list[dict[str, Any]] = Field(default_factory=list)
    trade_plans: list[dict[str, Any]] = Field(default_factory=list)
    risk_alerts: list[dict[str, Any]] = Field(default_factory=list)
    monitoring_focus: list[dict[str, Any]] = Field(default_factory=list)
    event_watch: list[dict[str, Any]] = Field(default_factory=list)
    evidence_trace: list[dict[str, Any]] = Field(default_factory=list)
    narrative: dict[str, Any] = Field(default_factory=dict)
