from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx

UTC = timezone.utc

ETF_GROUPS: dict[str, dict[str, Any]] = {
    "halo": {
        "group_label": "HALO",
        "items": [
            {"code": "563010", "name": "电信ETF", "market": "SH", "order": 20},
            {"code": "512660", "name": "军工ETF", "market": "SH", "order": 30},
            {"code": "516950", "name": "基建ETF", "market": "SH", "order": 40},
            {"code": "512400", "name": "有色金属ETF", "market": "SH", "order": 50},
            {"code": "159930", "name": "能源ETF", "market": "SZ", "order": 60},
            {"code": "561560", "name": "电力ETF", "market": "SH", "order": 70},
        ],
    },
    "cashflow": {
        "group_label": "现金流",
        "items": [
            {"code": "159201", "name": "现金流ETF", "market": "SZ", "order": 10},
        ],
    },
}

EASTMONEY_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f20,f21,f8,f10,f13,f124"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def secid_for_code(code: str) -> str:
    normalized = str(code).strip()
    return f"1.{normalized}" if normalized.startswith(("5", "6")) else f"0.{normalized}"


def market_for_code(code: str) -> str:
    return "SH" if str(code).startswith(("5", "6")) else "SZ"


def to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def ts_to_datetime_or_none(value: Any) -> datetime | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return datetime.fromtimestamp(int(float(value)), tz=UTC)
    except (ValueError, TypeError, OSError):
        return None


@dataclass(slots=True)
class AShareETFQuote:
    code: str
    name: str
    source_name: str | None
    group: str
    group_label: str
    market: str
    secid: str
    last_price: float | None
    change_pct: float | None
    change_amount: float | None
    volume: float | None
    amount: float | None
    high: float | None
    low: float | None
    open: float | None
    prev_close: float | None
    turnover_rate: float | None
    volume_ratio: float | None
    quote_time: datetime | None
    source: str | None
    status: Literal["ok", "missing", "unavailable"] = "ok"
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EastmoneyDirectETFClient:
    provider_id = "eastmoney_direct"

    def __init__(self, *, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    async def fetch_quotes(self, requested_items: list[dict[str, Any]]) -> list[AShareETFQuote]:
        by_code = {str(item["code"]): item for item in requested_items}
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": EASTMONEY_FIELDS,
            "secids": ",".join(secid_for_code(code) for code in by_code),
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers) as client:
                response = await client.get(f"{self.base_url}/api/qt/ulist.np/get", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self.last_error) from exc

        rows = ((payload or {}).get("data") or {}).get("diff") or []
        if not rows:
            self.last_error = "empty_eastmoney_diff"
            raise RuntimeError(self.last_error)

        quote_by_code: dict[str, AShareETFQuote] = {}
        for row in rows:
            code = str(row.get("f12") or "").strip()
            if not code or code not in by_code:
                continue
            item = by_code[code]
            quote_by_code[code] = AShareETFQuote(
                code=code,
                name=str(item.get("name") or code),
                source_name=row.get("f14"),
                group=str(item.get("group") or ""),
                group_label=str(item.get("group_label") or ""),
                market=market_for_code(code),
                secid=secid_for_code(code),
                last_price=to_float_or_none(row.get("f2")),
                change_pct=to_float_or_none(row.get("f3")),
                change_amount=to_float_or_none(row.get("f4")),
                volume=to_float_or_none(row.get("f5")),
                amount=to_float_or_none(row.get("f6")),
                high=to_float_or_none(row.get("f15")),
                low=to_float_or_none(row.get("f16")),
                open=to_float_or_none(row.get("f17")),
                prev_close=to_float_or_none(row.get("f18")),
                turnover_rate=to_float_or_none(row.get("f8")),
                volume_ratio=to_float_or_none(row.get("f10")),
                quote_time=ts_to_datetime_or_none(row.get("f124")),
                source=self.provider_id,
                status="ok",
            )

        quotes: list[AShareETFQuote] = []
        for code, item in by_code.items():
            if code in quote_by_code:
                quotes.append(quote_by_code[code])
                continue
            quotes.append(
                self._unavailable_quote(item, "provider_missing_symbol", status="missing")
            )

        self.last_success_at = utc_now()
        self.last_error = None
        return quotes

    @staticmethod
    def _unavailable_quote(
        item: dict[str, Any],
        error_message: str,
        *,
        status: Literal["missing", "unavailable"] = "unavailable",
    ) -> AShareETFQuote:
        code = str(item["code"])
        return AShareETFQuote(
            code=code,
            name=str(item.get("name") or code),
            source_name=None,
            group=str(item.get("group") or ""),
            group_label=str(item.get("group_label") or ""),
            market=market_for_code(code),
            secid=secid_for_code(code),
            last_price=None,
            change_pct=None,
            change_amount=None,
            volume=None,
            amount=None,
            high=None,
            low=None,
            open=None,
            prev_close=None,
            turnover_rate=None,
            volume_ratio=None,
            quote_time=None,
            source=None,
            status=status,
            error_message=error_message,
        )


class AShareETFQuoteService:
    def __init__(
        self,
        *,
        providers: list[EastmoneyDirectETFClient],
        ttl_seconds: int,
        stale_cache_seconds: int,
    ) -> None:
        self.providers = providers
        self.ttl_seconds = ttl_seconds
        self.stale_cache_seconds = stale_cache_seconds
        self._cache: dict[str, Any] | None = None
        self._cache_written_monotonic = 0.0

    def catalog(self) -> dict[str, Any]:
        return {
            "groups": [
                {"group": group, "group_label": config["group_label"]}
                for group, config in ETF_GROUPS.items()
            ],
            "items": self.list_items("all"),
        }

    def list_items(self, group: str = "all") -> list[dict[str, Any]]:
        selected = group or "all"
        if selected != "all" and selected not in ETF_GROUPS:
            raise ValueError(f"unsupported_group:{selected}")
        groups = ETF_GROUPS.items() if selected == "all" else [(selected, ETF_GROUPS[selected])]
        items: list[dict[str, Any]] = []
        for group_id, group_config in groups:
            group_items = sorted(
                group_config["items"],
                key=lambda item: int(item.get("order") or 0),
            )
            for item in group_items:
                enriched = dict(item)
                enriched["group"] = group_id
                enriched["group_label"] = group_config["group_label"]
                enriched["secid"] = secid_for_code(enriched["code"])
                items.append(enriched)
        return items

    async def get_quotes(self, *, group: str = "all", force: bool = False) -> dict[str, Any]:
        cache_key = group or "all"
        now = time.monotonic()
        if (
            not force
            and self._cache
            and self._cache.get("cache_key") == cache_key
            and now - self._cache_written_monotonic <= self.ttl_seconds
        ):
            cached = dict(self._cache["payload"])
            cached["cache_status"] = "hit"
            return cached

        requested_items = self.list_items(cache_key)
        errors: list[str] = []
        for provider in self.providers:
            try:
                quotes = await provider.fetch_quotes(requested_items)
                payload = self._format_response(
                    quotes=quotes,
                    source=provider.provider_id,
                    source_status="ok" if all(q.status == "ok" for q in quotes) else "partial",
                    cache_status="live",
                    warnings=[q.error_message for q in quotes if q.error_message],
                )
                self._cache = {"cache_key": cache_key, "payload": payload}
                self._cache_written_monotonic = time.monotonic()
                return payload
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.provider_id}: {type(exc).__name__}: {exc}")

        if self._cache and now - self._cache_written_monotonic <= self.stale_cache_seconds:
            cached = dict(self._cache["payload"])
            cached["source_status"] = "stale"
            cached["cache_status"] = "stale"
            cached["warnings"] = [*cached.get("warnings", []), *errors]
            return cached

        unavailable = [
            EastmoneyDirectETFClient._unavailable_quote(item, "行情源暂不可用")
            for item in requested_items
        ]
        return self._format_response(
            quotes=unavailable,
            source=None,
            source_status="error",
            cache_status="empty",
            warnings=errors or ["all_providers_failed"],
        )

    def sources_health(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now(),
            "providers": [
                {
                    "id": provider.provider_id,
                    "enabled": True,
                    "last_success_at": provider.last_success_at,
                    "last_error": provider.last_error,
                    "priority": index + 1,
                }
                for index, provider in enumerate(self.providers)
            ],
        }

    def _format_response(
        self,
        *,
        quotes: list[AShareETFQuote],
        source: str | None,
        source_status: Literal["ok", "partial", "stale", "error"],
        cache_status: Literal["live", "hit", "stale", "empty"],
        warnings: list[str | None],
    ) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for quote in quotes:
            groups.setdefault(
                quote.group,
                {"group": quote.group, "group_label": quote.group_label, "items": []},
            )["items"].append(quote.to_dict())
        ordered_groups = [groups[group] for group in ETF_GROUPS if group in groups]
        return {
            "generated_at": utc_now(),
            "source_status": source_status,
            "source": source,
            "cache_status": cache_status,
            "ttl_seconds": self.ttl_seconds,
            "groups": ordered_groups,
            "warnings": [warning for warning in warnings if warning],
        }
