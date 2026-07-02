from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProviderStatus(BaseModel):
    provider: str
    status: Literal[
        "ok", "partial", "failed", "circuit_open", "disabled", "unknown"
    ] = "unknown"
    capabilities: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    circuit_open_until: datetime | None = None
    endpoint_success: int = 0
    endpoint_total: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    cache_state: str | None = None


class EndpointProbeResult(BaseModel):
    provider: str
    endpoint: str
    capability: str
    ok: bool
    latency_ms: float | None = None
    status_code: int | None = None
    checked_at: datetime
    error: str | None = None
    cache_hit: bool = False


class NormalizedOptionQuote(BaseModel):
    provider: str
    instrument: str
    expiry: str
    strike: float
    option_type: Literal["call", "put"]
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    mark_price: float | None = None
    native_bid: float | None = None
    native_ask: float | None = None
    native_mark: float | None = None
    premium_currency: str | None = None
    underlying_price: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: float | None = None
    volume_24h: float | None = None
    provider_timestamp: datetime | None = None
    collected_at: datetime
    conversion: str | None = None
    quality_notes: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    raw_units: dict[str, str] = Field(default_factory=dict)


class NormalizedPerpSnapshot(BaseModel):
    provider: str
    instrument: str
    instrument_type: Literal["perpetual", "future"] = "perpetual"
    expiry: str | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest_contracts: float | None = None
    open_interest_usd: float | None = None
    volume_24h_usd: float | None = None
    basis_pct: float | None = None
    annualized_basis_pct: float | None = None
    provider_timestamp: datetime | None = None
    collected_at: datetime
    conversion: str | None = None
    quality_notes: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    raw_units: dict[str, str] = Field(default_factory=dict)


class SourceProbeResponse(BaseModel):
    generated_at: datetime
    providers: list[ProviderStatus] = Field(default_factory=list)
    endpoints: list[EndpointProbeResult] = Field(default_factory=list)


class LiveSnapshotEnvelope(BaseModel):
    snapshot_state: Literal["live", "stale", "data_insufficient"]
    data_timestamp: datetime | None = None
    options: list[NormalizedOptionQuote] = Field(default_factory=list)
    perps: list[NormalizedPerpSnapshot] = Field(default_factory=list)
    price_history: list[dict[str, Any]] = Field(default_factory=list)
    key_level_history: list[dict[str, Any]] = Field(default_factory=list)
    source_status: list[ProviderStatus] = Field(default_factory=list)
    primary_option_provider: str | None = None
    missing_reasons: list[str] = Field(default_factory=list)
