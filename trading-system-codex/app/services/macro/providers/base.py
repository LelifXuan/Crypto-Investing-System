from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(slots=True)
class MacroFetchResult:
    observation_ts: datetime
    value: Decimal
    source_ref: str
    source_granularity: str = "1d"
    metadata: dict | None = None


@dataclass(slots=True)
class MacroFetchPoint:
    """A single point in a provider's history series.

    Providers that can return more than one observation implement
    ``fetch_history``. The point's ``status`` field is a free-form string
    (``"ok"`` / ``"missing"`` / ``"placeholder"``) — callers filter on it.
    """

    observation_ts: datetime
    value: Decimal | None
    status: str = "ok"
    metadata: dict | None = None


class MacroProvider(Protocol):
    provider_key: str

    def supports(self, source_provider: str, source_kind: str) -> bool: ...

    async def fetch_latest(self, source_key: str) -> MacroFetchResult: ...

    async def healthcheck(self) -> tuple[str, str | None]: ...


class HistoryNotSupported(NotImplementedError):
    """Raised by providers that do not implement ``fetch_history``."""
