from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AShareEtfCatalogItem(BaseModel):
    code: str
    name: str
    group: str
    group_label: str
    market: str
    secid: str
    order: int


class AShareEtfCatalogResponse(BaseModel):
    groups: list[dict]
    items: list[AShareEtfCatalogItem]


class AShareEtfQuoteRead(BaseModel):
    code: str
    name: str
    group: str
    group_label: str
    market: str
    secid: str
    source_name: str | None = None
    last_price: float | None = None
    change_pct: float | None = None
    change_amount: float | None = None
    volume: float | None = None
    amount: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None
    quote_time: datetime | None = None
    source: str | None = None
    status: Literal["ok", "missing", "unavailable"] = "unavailable"
    error_message: str | None = None


class AShareEtfQuoteGroup(BaseModel):
    group: str
    group_label: str
    items: list[AShareEtfQuoteRead] = Field(default_factory=list)


class AShareEtfQuoteResponse(BaseModel):
    generated_at: datetime
    source_status: Literal["ok", "partial", "stale", "error"]
    source: str | None = None
    cache_status: Literal["live", "hit", "stale", "empty"] = "empty"
    ttl_seconds: int
    groups: list[AShareEtfQuoteGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AShareEtfProviderHealth(BaseModel):
    id: str
    enabled: bool
    last_success_at: datetime | None = None
    last_error: str | None = None
    priority: int = 1


class AShareEtfSourceHealthResponse(BaseModel):
    generated_at: datetime
    providers: list[AShareEtfProviderHealth]
