from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class FuturesSnapshot:
    exchange: str
    instrument: str
    timestamp: str
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    funding_rate_7d_avg: float | None = None
    open_interest_usd: float | None = None
    open_interest_usd_prev: float | None = None
    volume_24h_usd: float | None = None
    expiry: str | None = None
    basis_pct: float | None = None
    annualized_basis_pct: float | None = None


@dataclass(frozen=True)
class OptionQuote:
    expiry: str
    strike: float
    option_type: OptionType
    bid: float | None = None
    ask: float | None = None
    mark: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: float | None = None
    volume_24h: float | None = None
    timestamp: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class OptionChainRow:
    expiry: str
    strike: float
    call: OptionQuote | None = None
    put: OptionQuote | None = None


@dataclass(frozen=True)
class DerivativesSnapshot:
    timestamp: str
    spot_price: float
    option_quotes: tuple[OptionQuote, ...] = field(default_factory=tuple)
    futures_rows: tuple[FuturesSnapshot, ...] = field(default_factory=tuple)
    metrics: dict[str, Any] = field(default_factory=dict)
