"""Cached ETF history NAV service.

Reads/writes per-symbol history JSON files under ``runtime/cache/fund_history``.
A single symbol's history is stored as::

    {
      "code": "563010",
      "market": "SH",
      "secid": "1.563010",
      "name": "...",
      "source": "eastmoney_kline",
      "coverage_start": "2020-08-12",
      "coverage_end": "2026-08-04",
      "last_updated": "2026-08-04T16:00:00Z",
      "points": [{"date": "...", "close": 1.234, ...}, ...]
    }

The service supports incremental fetch: when the caller asks for a window
that extends past the cached ``coverage_end``, only the missing tail is
pulled. Conversely, missing leading history (cold start) triggers a full
backfill from the configured ``default_beg`` (defaults to 5 years back).

The cache is intentionally append-only-with-replace: we never mutate a
historical bar in place. New bars always extend the series; if a cached
bar's date appears again in the upstream payload it is replaced (this is
the only way to correct a previously mis-pulled bar).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from app.core.paths import app_paths
from app.integrations.cn_etf_history import (
    DEFAULT_HISTORY_YEARS,
    EastmoneyFundKlineClient,
    EtfHistoryFetchResult,
    EtfKlinePoint,
)

logger = logging.getLogger(__name__)

UTC = timezone.utc

CACHE_SUBDIR = "fund_history"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def cache_dir() -> Path:
    """Return the per-symbol history cache directory, creating it lazily."""

    root = app_paths.cache_dir / CACHE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_path_for_code(code: str) -> Path:
    return cache_dir() / f"{code}.json"


@dataclass(slots=True)
class EtfHistorySnapshot:
    """Resolved view of cached history for one ETF symbol."""

    code: str
    market: str
    secid: str
    name: str | None
    source: str
    coverage_start: date
    coverage_end: date
    last_updated: datetime
    points: list[EtfKlinePoint]

    @property
    def nav_by_date(self) -> dict[date, float]:
        return {p.trade_date: p.close for p in self.points}


class EtfHistoryService:
    """Async service for read-through cached ETF NAV history."""

    def __init__(
        self,
        *,
        client: EastmoneyFundKlineClient | None = None,
        default_beg: date | None = None,
    ) -> None:
        self.client = client or EastmoneyFundKlineClient()
        self.default_beg = default_beg

    async def get_snapshot(
        self,
        code: str,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        force_refresh: bool = False,
    ) -> EtfHistorySnapshot:
        """Return the cached snapshot, fetching from upstream if necessary.

        ``from_date`` / ``to_date`` only narrow the returned ``points``;
        they do not shrink the underlying cache. If either side of the
        requested window extends past cached coverage, an incremental
        fetch is triggered.
        """
        normalized = str(code).strip()
        today = utc_now().date()

        if to_date is None:
            to_date = today
        if from_date is None:
            from_date = self.default_beg or (today - timedelta(days=365 * DEFAULT_HISTORY_YEARS))

        existing = self._read_cache(normalized)
        needs_fetch = force_refresh or existing is None or self._window_extends(
            existing, from_date, to_date
        )

        if needs_fetch:
            await self._fetch_and_merge(normalized, from_date, to_date, existing)
            existing = self._read_cache(normalized)

        if existing is None:
            raise FileNotFoundError(
                f"etf_history_empty:{normalized}"
            )

        # Narrow points to the requested window (inclusive on both sides).
        narrowed = [
            p for p in existing.points if from_date <= p.trade_date <= to_date
        ]
        return EtfHistorySnapshot(
            code=existing.code,
            market=existing.market,
            secid=existing.secid,
            name=existing.name,
            source=existing.source,
            coverage_start=existing.coverage_start,
            coverage_end=existing.coverage_end,
            last_updated=existing.last_updated,
            points=narrowed,
        )

    async def prefetch_universe(self, codes: Iterable[str]) -> None:
        """Cold-start helper: prefetch all HALO + cashflow symbols.

        Runs sequentially to avoid hammering the upstream endpoint.
        """
        for code in codes:
            try:
                await self.get_snapshot(code)
            except Exception as exc:  # noqa: BLE001
                logger.warning("etf_history_prefetch_failed code=%s err=%s", code, exc)

    # --- internals ------------------------------------------------------

    @staticmethod
    def _window_extends(
        snapshot: EtfHistorySnapshot, from_date: date, to_date: date
    ) -> bool:
        return from_date < snapshot.coverage_start or to_date > snapshot.coverage_end

    def _read_cache(self, code: str) -> EtfHistorySnapshot | None:
        path = cache_path_for_code(code)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("etf_history_cache_corrupt code=%s err=%s", code, exc)
            return None
        return _snapshot_from_dict(raw)

    async def _fetch_and_merge(
        self,
        code: str,
        from_date: date,
        to_date: date,
        existing: EtfHistorySnapshot | None,
    ) -> None:
        # Cold start: full backfill. Otherwise incremental from coverage_end+1.
        if existing is None:
            fetch_beg = from_date
            fetch_end = to_date
        else:
            fetch_beg = min(from_date, existing.coverage_start)
            fetch_end = to_date
        try:
            result = await self.client.fetch_history(code, beg=fetch_beg, end=fetch_end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("etf_history_fetch_failed code=%s err=%s", code, exc)
            if existing is None:
                raise
            # Stale-but-readable: keep cache.
            return
        merged = _merge_points(existing, result)
        self._write_cache(code, merged, result)

    def _write_cache(
        self, code: str, snapshot: EtfHistorySnapshot, latest: EtfHistoryFetchResult
    ) -> None:
        payload = {
            "code": snapshot.code,
            "market": snapshot.market,
            "secid": snapshot.secid,
            "name": snapshot.name or latest.name,
            "source": self.client.provider_id,
            "coverage_start": snapshot.coverage_start.isoformat(),
            "coverage_end": snapshot.coverage_end.isoformat(),
            "last_updated": snapshot.last_updated.isoformat(),
            "points": [p.to_dict() for p in snapshot.points],
        }
        path = cache_path_for_code(code)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


# --- pure helpers (no I/O, easy to unit test) ---------------------------


def _snapshot_from_dict(raw: dict[str, Any]) -> EtfHistorySnapshot:
    coverage_start = date.fromisoformat(raw["coverage_start"])
    coverage_end = date.fromisoformat(raw["coverage_end"])
    last_updated = datetime.fromisoformat(raw["last_updated"])
    points = [_point_from_dict(p) for p in raw.get("points", [])]
    return EtfHistorySnapshot(
        code=raw["code"],
        market=raw["market"],
        secid=raw["secid"],
        name=raw.get("name"),
        source=raw.get("source") or "eastmoney_kline",
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        last_updated=last_updated,
        points=points,
    )


def _point_from_dict(d: dict[str, Any]) -> EtfKlinePoint:
    return EtfKlinePoint(
        trade_date=date.fromisoformat(d["date"]),
        open=d.get("open"),
        close=float(d["close"]),
        high=d.get("high"),
        low=d.get("low"),
        volume=d.get("volume"),
        amount=d.get("amount"),
        amplitude_pct=d.get("amplitude_pct"),
    )


def _merge_points(
    existing: EtfHistorySnapshot | None,
    latest: EtfHistoryFetchResult,
) -> EtfHistorySnapshot:
    if existing is None:
        coverage_start = latest.points[0].trade_date if latest.points else utc_now().date()
        coverage_end = latest.points[-1].trade_date if latest.points else utc_now().date()
        return EtfHistorySnapshot(
            code=latest.code,
            market=latest.market,
            secid=latest.secid,
            name=latest.name,
            source="eastmoney_kline",
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            last_updated=latest.fetched_at,
            points=list(latest.points),
        )

    by_date: dict[date, EtfKlinePoint] = {p.trade_date: p for p in existing.points}
    for p in latest.points:
        by_date[p.trade_date] = p  # newer fetch overrides stale bars.
    merged = sorted(by_date.values(), key=lambda p: p.trade_date)
    return EtfHistorySnapshot(
        code=existing.code,
        market=existing.market,
        secid=existing.secid,
        name=existing.name or latest.name,
        source=existing.source,
        coverage_start=merged[0].trade_date,
        coverage_end=merged[-1].trade_date,
        last_updated=latest.fetched_at,
        points=merged,
    )


def run_async(coro: Any) -> Any:
    """Helper for tests: run a coroutine in a fresh event loop."""

    return asyncio.get_event_loop().run_until_complete(coro)


def point_close_decimal(point: EtfKlinePoint) -> Decimal:
    """Return close price as Decimal to avoid float drift in equity math."""
    return Decimal(str(point.close))


__all__ = [
    "CACHE_SUBDIR",
    "EtfHistoryService",
    "EtfHistorySnapshot",
    "cache_dir",
    "cache_path_for_code",
    "point_close_decimal",
    "run_async",
    "utc_now",
]