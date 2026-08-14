"""ETF history NAV adapter.

Pulls daily-frequency NAV / kline data from Eastmoney's historical endpoint
(`push2his.eastmoney.com/api/qt/stock/kline/get`), with a Sina Finance
fallback (`money.finance.sina.com.cn/quotes_service/api/json_v2.php/...`)
for when the Eastmoney CDN is unreachable from the current network.

Notes
-----
- Eastmoney `fqt=1` returns forward-adjusted (前复权) prices, which is the
  standard for NAV backtests because split/dividend events are baked into
  the series. Sina returns raw daily close without forward-adjustment; we
  keep them as-is and surface that distinction in the cache schema.
- `klt=101` selects daily frequency (Eastmoney). Sina `scale=240` is daily.
- The Eastmoney endpoint frequently drops connections (`Server disconnected
  without sending a response`) from non-mainland-China IPs. The adapter
  retries with backoff across the same base URLs used by
  `EastmoneyDirectETFClient`, then falls through to Sina. Sina's history
  is capped at ~1024 bars (~4 trading years) but that's enough for the
  HALO 252-day rolling covariance window plus monthly DCA + rebalance.

This module is intentionally small and synchronous-friendly; the cache
layer in `app.services.ashare_etf_history` is responsible for incremental
fetch and persistence.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.ashare_etf_quotes import (
    EASTMONEY_BACKUP_BASE_URLS,
    market_for_code,
    secid_for_code,
    to_float_or_none,
)
from app.services.network.http_client_factory import client_for_source

logger = logging.getLogger(__name__)

UTC = timezone.utc

# Default request window (years of history to backfill on first call).
DEFAULT_HISTORY_YEARS = 5

# Fields for the kline payload. f51=date, f52=open, f53=close, f54=high,
# f55=low, f56=volume, f57=amount, f58=amplitude_pct.
DEFAULT_FIELDS_1 = "f1,f2,f3,f4,f5,f6"
DEFAULT_FIELDS_2 = "f51,f52,f53,f54,f55,f56,f57,f58"


@dataclass(slots=True)
class EtfKlinePoint:
    """One bar of ETF NAV history."""

    trade_date: date
    open: float | None
    close: float  # We treat close as NAV end-of-day for equity-curve math.
    high: float | None
    low: float | None
    volume: float | None
    amount: float | None
    amplitude_pct: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.trade_date.isoformat(),
            "open": self.open,
            "close": self.close,
            "high": self.high,
            "low": self.low,
            "volume": self.volume,
            "amount": self.amount,
            "amplitude_pct": self.amplitude_pct,
        }


@dataclass(slots=True)
class EtfHistoryFetchResult:
    """Result of a single Eastmoney kline fetch."""

    code: str
    market: str
    secid: str
    name: str | None
    total_bars: int  # dktotal from the upstream response
    points: list[EtfKlinePoint]
    fetched_at: datetime


class EastmoneyFundKlineClient:
    """Async client for Eastmoney's ETF kline endpoint.

    Designed to be tolerant of transient connection drops: it retries with
    a small backoff and falls back across the same backup base URLs used
    by the live quote client. If every Eastmoney URL fails, it falls through
    to ``SinaFundKlineClient`` so the strategy simulation still gets NAV
    data when the Eastmoney CDN is unreachable from the current network.
    """

    provider_id = "eastmoney_kline"

    def __init__(
        self,
        *,
        base_urls: tuple[str, ...] = EASTMONEY_BACKUP_BASE_URLS,
        timeout_seconds: float = 20.0,
        max_attempts_per_url: int = 2,
        sina_fallback: SinaFundKlineClient | None = None,
    ) -> None:
        self.base_urls = tuple(base_urls)
        self.timeout_seconds = timeout_seconds
        self.max_attempts_per_url = max_attempts_per_url
        self.sina_fallback = sina_fallback or SinaFundKlineClient(
            timeout_seconds=timeout_seconds
        )
        self.last_success_at: datetime | None = None
        self.last_success_source: str | None = None
        self.last_error: str | None = None

    async def fetch_history(
        self,
        code: str,
        *,
        beg: date | None = None,
        end: date | None = None,
        klt: int = 101,
        fqt: int = 1,
    ) -> EtfHistoryFetchResult:
        """Fetch daily kline bars for the given ETF.

        Tries Eastmoney first, falls through to Sina if every Eastmoney URL
        fails. ``beg`` defaults to ``today - DEFAULT_HISTORY_YEARS``; ``end``
        defaults to today (UTC).
        """
        normalized = str(code).strip()
        market = market_for_code(normalized)
        secid = secid_for_code(normalized)

        if end is None:
            end = datetime.now(tz=UTC).date()
        if beg is None:
            beg = end - timedelta(days=365 * DEFAULT_HISTORY_YEARS)

        em_errors: list[str] = []
        for url in self.base_urls:
            for attempt in range(self.max_attempts_per_url):
                try:
                    async with client_for_source(
                        self.provider_id,
                        timeout=self.timeout_seconds,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124 Safari/537.36"
                            ),
                            "Referer": "https://quote.eastmoney.com/",
                            "Accept": "application/json,text/plain,*/*",
                        },
                    ) as client:
                        response = await client.get(
                            f"{url.rstrip('/')}/api/qt/stock/kline/get",
                            params={
                                "secid": secid,
                                "fields1": DEFAULT_FIELDS_1,
                                "fields2": DEFAULT_FIELDS_2,
                                "klt": klt,
                                "fqt": fqt,
                                "beg": beg.strftime("%Y%m%d"),
                                "end": end.strftime("%Y%m%d"),
                            },
                        )
                        response.raise_for_status()
                        payload = response.json()
                    points, name, total = self._parse_payload(payload)
                    if not points:
                        em_errors.append(f"{url}:empty_payload")
                        await asyncio.sleep(0.35 * (attempt + 1))
                        continue
                    self.last_success_at = datetime.now(tz=UTC)
                    self.last_success_source = "eastmoney_kline"
                    self.last_error = None
                    return EtfHistoryFetchResult(
                        code=normalized,
                        market=market,
                        secid=secid,
                        name=name,
                        total_bars=total,
                        points=points,
                        fetched_at=self.last_success_at,
                    )
                except Exception as exc:  # noqa: BLE001
                    em_errors.append(f"{url}:{type(exc).__name__}:{exc}")
                    await asyncio.sleep(0.35 * (attempt + 1))

        # All Eastmoney URLs failed or returned empty — fall through to Sina.
        try:
            result = await self.sina_fallback.fetch_history(
                normalized, beg=beg, end=end
            )
            self.last_success_at = result.fetched_at
            self.last_success_source = "sina_kline"
            self.last_error = None
            return result
        except Exception as exc:  # noqa: BLE001
            em_msg = "; ".join(em_errors) or "eastmoney_kline_unavailable"
            msg = f"eastmoney:[{em_msg}] sina:{type(exc).__name__}:{exc}"
            self.last_error = msg
            logger.warning("ETF kline fetch failed for %s: %s", code, msg)
            raise RuntimeError(msg) from exc

    @staticmethod
    def _parse_payload(
        payload: dict[str, Any] | None,
    ) -> tuple[list[EtfKlinePoint], str | None, int]:
        data = (payload or {}).get("data") or {}
        name = data.get("name")
        total = int(data.get("dktotal") or 0)
        raw_klines = data.get("klines") or []
        points: list[EtfKlinePoint] = []
        for line in raw_klines:
            point = _parse_kline_line(line)
            if point is not None:
                points.append(point)
        return points, name, total


def _parse_kline_line(line: str | None) -> EtfKlinePoint | None:
    """Parse one kline CSV row from the Eastmoney response.

    Format: ``YYYY-MM-DD,open,close,high,low,volume,amount,amplitude_pct``.
    """
    if not line or not isinstance(line, str):
        return None
    parts = line.split(",")
    if len(parts) < 8:
        return None
    try:
        trade_date = datetime.strptime(parts[0], "%Y-%m-%d").date()
    except ValueError:
        return None
    close = to_float_or_none(parts[2])
    if close is None:
        return None
    return EtfKlinePoint(
        trade_date=trade_date,
        open=to_float_or_none(parts[1]),
        close=close,
        high=to_float_or_none(parts[3]),
        low=to_float_or_none(parts[4]),
        volume=to_float_or_none(parts[5]),
        amount=to_float_or_none(parts[6]),
        amplitude_pct=to_float_or_none(parts[7]),
    )


# ---------------------------------------------------------------------------
# Sina Finance fallback adapter
# ---------------------------------------------------------------------------

SINA_KLINE_BASE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)


class SinaFundKlineClient:
    """Async client for Sina Finance's daily kline endpoint.

    Used as a fallback when Eastmoney's CDN is unreachable. Returns at most
    ~1024 bars (~4 trading years) but that's enough for the HALO 252-day
    rolling covariance window plus monthly DCA + rebalance simulation.
    Sina's payload has no forward-adjustment and no amount/amplitude fields;
    we coerce None where the Eastmoney schema requires them.
    """

    provider_id = "sina_kline"
    MAX_BARS = 1024

    def __init__(
        self,
        *,
        base_url: str = SINA_KLINE_BASE_URL,
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    async def fetch_history(
        self,
        code: str,
        *,
        beg: date | None = None,
        end: date | None = None,
    ) -> EtfHistoryFetchResult:
        normalized = str(code).strip()
        market = market_for_code(normalized)
        secid = secid_for_code(normalized)
        # Sina's symbol format: sh561560 for SH ETFs, sz159201 for SZ ETFs.
        sina_symbol = (
            f"sh{normalized}" if market == "SH" else f"sz{normalized}"
        )

        errors: list[str] = []
        for attempt in range(self.max_attempts):
            try:
                async with client_for_source(
                    self.provider_id,
                    timeout=self.timeout_seconds,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124 Safari/537.36"
                        ),
                        "Referer": "https://finance.sina.com.cn/",
                        "Accept": "application/json,text/plain,*/*",
                    },
                ) as client:
                    response = await client.get(
                        self.base_url,
                        params={
                            "symbol": sina_symbol,
                            "scale": 240,
                            "ma": "no",
                            "datalen": self.MAX_BARS,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                points = _parse_sina_payload(payload)
                if not points:
                    errors.append(
                        f"{self.base_url}:empty_payload({sina_symbol})"
                    )
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue
                self.last_success_at = datetime.now(tz=UTC)
                self.last_error = None
                return EtfHistoryFetchResult(
                    code=normalized,
                    market=market,
                    secid=secid,
                    name=None,
                    total_bars=len(points),
                    points=points,
                    fetched_at=self.last_success_at,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{self.base_url}:{type(exc).__name__}:{exc}"
                )
                await asyncio.sleep(0.35 * (attempt + 1))

        msg = "; ".join(errors) or "sina_kline_unavailable"
        self.last_error = msg
        logger.warning("Sina ETF kline fetch failed for %s: %s", code, msg)
        raise RuntimeError(msg)


def _parse_sina_payload(payload: Any) -> list[EtfKlinePoint]:
    """Parse Sina's daily kline JSON array.

    Schema: ``[{"day":"YYYY-MM-DD","open":"1.234","high":"1.234","low":"...",
    "close":"1.234","volume":"12345"}, ...]`` (most-recent LAST).
    """
    if not isinstance(payload, list):
        return []
    points: list[EtfKlinePoint] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        day = row.get("day")
        if not day:
            continue
        try:
            trade_date = datetime.strptime(str(day), "%Y-%m-%d").date()
        except ValueError:
            continue
        close = to_float_or_none(row.get("close"))
        if close is None:
            continue
        points.append(
            EtfKlinePoint(
                trade_date=trade_date,
                open=to_float_or_none(row.get("open")),
                close=close,
                high=to_float_or_none(row.get("high")),
                low=to_float_or_none(row.get("low")),
                volume=to_float_or_none(row.get("volume")),
                amount=None,
                amplitude_pct=None,
            )
        )
    points.sort(key=lambda p: p.trade_date)
    return points


def decimal_to_float(value: Any) -> float | None:
    """Coerce Decimal/str/number to float without lossy scientific notation."""
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


__all__ = [
    "DEFAULT_HISTORY_YEARS",
    "EastmoneyFundKlineClient",
    "EtfHistoryFetchResult",
    "EtfKlinePoint",
    "SINA_KLINE_BASE_URL",
    "SinaFundKlineClient",
]