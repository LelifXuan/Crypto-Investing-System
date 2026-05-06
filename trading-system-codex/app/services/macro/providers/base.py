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


class MacroProvider(Protocol):
    provider_key: str

    def supports(self, source_provider: str, source_kind: str) -> bool: ...

    async def fetch_latest(self, source_key: str) -> MacroFetchResult: ...

    async def healthcheck(self) -> tuple[str, str | None]: ...
