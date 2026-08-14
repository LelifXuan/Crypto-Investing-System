from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from html import unescape

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc
US_BONDS_URL = "https://zh.tradingeconomics.com/united-states/5-year-tips-yield"
SUPPORTED_ROWS = {"US 5Y TIPS"}


@dataclass(slots=True)
class TradingEconomicsBondRow:
    label: str
    yield_value: Decimal
    day_change_pct: Decimal | None
    month_change_pct: Decimal | None
    year_change_pct: Decimal | None
    date: datetime


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _decimal(value: str) -> Decimal | None:
    cleaned = value.replace("%", "").replace(",", "").strip()
    if cleaned in {"", "-", "—"}:
        return None
    return D(cleaned)


def parse_us_bond_table(html: str, label: str) -> TradingEconomicsBondRow:
    if label not in SUPPORTED_ROWS:
        raise ValueError(f"Unsupported Trading Economics bond row: {label}")
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    for row_html in rows:
        cells = re.findall(
            r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        values = [_strip_tags(cell) for cell in cells]
        if not values or values[0].upper() != label.upper():
            continue
        if len(values) < 6:
            raise ValueError(f"Trading Economics row is incomplete: {label}")
        yield_value = _decimal(values[1])
        if yield_value is None:
            raise ValueError(f"Trading Economics row has no yield value: {label}")
        tail = [value for value in values[2:] if value]
        if len(tail) < 4:
            raise ValueError(f"Trading Economics row is incomplete: {label}")
        try:
            date_value = datetime.fromisoformat(tail[-1]).replace(tzinfo=UTC)
        except ValueError as exc:
            raise ValueError(f"Trading Economics row has invalid date: {label}") from exc
        changes = tail[:-1]
        return TradingEconomicsBondRow(
            label=label,
            yield_value=yield_value,
            day_change_pct=_decimal(changes[0]) if len(changes) > 0 else None,
            month_change_pct=_decimal(changes[1]) if len(changes) > 1 else None,
            year_change_pct=_decimal(changes[2]) if len(changes) > 2 else None,
            date=date_value,
        )
    raise ValueError(f"Trading Economics row not found: {label}")


class TradingEconomicsWebProvider:
    provider_key = "tradingeconomics_web"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "raw_series"

    async def _fetch_us_bond_html(self) -> str:
        if self.cache:
            cached = self.cache.get(self.provider_key, "us_bond_table", {"url": US_BONDS_URL})
            if cached is not None:
                return str(cached)
        async with client_for_source("tradingeconomics_web", timeout=20) as client:
            resp = await client.get(US_BONDS_URL)
        resp.raise_for_status()
        text = resp.text
        if self.cache:
            self.cache.set(self.provider_key, "us_bond_table", {"url": US_BONDS_URL}, text, 21600)
        return text

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        row = parse_us_bond_table(await self._fetch_us_bond_html(), source_key)
        return MacroFetchResult(
            observation_ts=row.date,
            value=row.yield_value,
            source_ref=f"{self.provider_key}:{row.label}",
            source_granularity="1d",
            metadata={
                "label": row.label,
                "day_change_pct": (
                    str(row.day_change_pct) if row.day_change_pct is not None else None
                ),
                "month_change_pct": str(row.month_change_pct)
                if row.month_change_pct is not None
                else None,
                "year_change_pct": (
                    str(row.year_change_pct) if row.year_change_pct is not None else None
                ),
                "url": US_BONDS_URL,
            },
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            await self.fetch_latest("US 5Y TIPS")
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)
