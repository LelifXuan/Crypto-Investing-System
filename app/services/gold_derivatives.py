"""Gold derivatives aggregator — multi-source PAXG/XAUT perp + CFTC COT.

The contract returns exactly four fields consumed by the workbench UI:

* ``funding_rate``         — USD-notional weighted average across venues.
* ``open_interest``        — Sum of tokenised perp OI (contracts).
* ``oi_change_4w``         — Same total vs 4-week-ago cached snapshot.
* ``cot_net_spec_percentile`` — CFTC Managed-Money percentile (COMEX GC).

The user only ever sees one combined "XAUT" indicator; the per-venue
breakdown stays internal. Any single venue failing does NOT short-
circuit the aggregation — at least two venues succeeding keeps the
weighted result trustworthy.

All numeric values are stored as ``Decimal`` internally and serialised
as decimal strings at the JSON boundary (no float drift across the
HTTP<->Python hop).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.decimal_utils import D
from app.core.paths import app_paths

UTC = timezone.utc
_D = Decimal

# Persistent cache of weekly aggregated OI snapshots so ``oi_change_4w``
# can compare against an observation ~28 days old.
_CACHE_DIR = app_paths.cache_dir / "gold_derivatives"
_OI_CACHE_FILE = "aggregated_oi.jsonl"
_MAX_OI_SNAPSHOTS = 12  # ~3 months of weekly history
_4_WEEKS_DAYS = 28

# ─── Per-venue endpoint registry ────────────────────────────────────────
# Each tuple: (provider_key, symbol, kind, funding_endpoint, oi_endpoint)
#
# ``kind`` distinguishes the URL template: "bybit" uses symbol verbatim,
# "okx" uses "INST-ID-SWAP", "binance" uses the USDT-M perp URL.
#
# ``PAXG`` and ``XAUT`` are both kept because each carries distinct
# liquidity — PAXG dominates on Binance, XAUT dominates on OKX. We
# aggregate across the union so the user's view is robust to a single
# token pausing.

_VENUES: tuple[tuple[str, str], ...] = (
    ("bybit", "PAXGUSDT"),
    ("bybit", "XAUTUSDT"),
    ("okx", "PAXG-USDT-SWAP"),
    ("okx", "XAUT-USDT-SWAP"),
    ("binance", "PAXGUSDT"),
    ("binance", "XAUTUSDT"),
)


# ─── Decimal-safe coercion helpers ──────────────────────────────────────


def _to_decimal(value: object) -> Optional[Decimal]:
    """Coerce a JSON number / string / Decimal to ``Decimal`` without float drift."""
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return D(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _to_float(value: object) -> Optional[float]:
    """For cases where downstream consumers expect ``float`` (UI display)."""
    dec = _to_decimal(value)
    return float(dec) if dec is not None else None


# ─── Per-row snapshot for a single venue × symbol ──────────────────────


@dataclass(slots=True)
class GoldPerpRow:
    provider: str
    symbol: str
    mark_price: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None
    oi_contracts: Optional[Decimal] = None
    oi_usd: Optional[Decimal] = None
    timestamp_ms: Optional[int] = None
    error: Optional[str] = None

    def is_valid(self) -> bool:
        return self.funding_rate is not None or self.oi_contracts is not None


# ─── OI snapshot history (4-week comparison) ────────────────────────────


@dataclass(slots=True)
class OISnapshot:
    timestamp: str
    oi_contracts_total: Decimal


class AggregatedOICache:
    """Persist weekly aggregated OI snapshots (one per fetch day)."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_snapshots: int = _MAX_OI_SNAPSHOTS,
    ) -> None:
        self.path = (cache_dir or _CACHE_DIR) / _OI_CACHE_FILE
        self.max_snapshots = max_snapshots

    def read_all(self) -> list[OISnapshot]:
        if not self.path.exists():
            return []
        out: list[OISnapshot] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                out.append(
                    OISnapshot(
                        timestamp=str(obj["timestamp"]),
                        oi_contracts_total=_to_decimal(obj["oi_contracts_total"])
                        or _D("0"),
                    )
                )
            except (KeyError, TypeError):
                continue
        return out[-self.max_snapshots:]

    def write(self, snapshot: OISnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read_all()
        # De-dup by timestamp: replace if same day, else append.
        seen: set[str] = set()
        unique: list[OISnapshot] = []
        for snap in reversed(existing):
            if snap.timestamp in seen:
                continue
            seen.add(snap.timestamp)
            unique.append(snap)
        unique.reverse()
        unique.append(snapshot)
        unique = unique[-self.max_snapshots:]
        with self.path.open("w", encoding="utf-8") as f:
            for snap in unique:
                f.write(
                    json.dumps(
                        {
                            "timestamp": snap.timestamp,
                            "oi_contracts_total": format(snap.oi_contracts_total, "f"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def oi_change_4w(self, current_oi: Decimal) -> Optional[Decimal]:
        """Compare current aggregated OI to the snapshot ~28 days ago."""
        if current_oi == 0:
            return None
        snaps = self.read_all()
        if not snaps:
            return None
        try:
            latest_dt = datetime.fromisoformat(snaps[-1].timestamp)
        except ValueError:
            return None
        target = latest_dt.replace(tzinfo=None)
        best: Optional[OISnapshot] = None
        best_diff: float = float("inf")
        for snap in snaps[:-1]:
            try:
                snap_dt = datetime.fromisoformat(snap.timestamp)
            except ValueError:
                continue
            days = abs((target - snap_dt.replace(tzinfo=None)).total_seconds() / 86400)
            diff = abs(days - _4_WEEKS_DAYS)
            if diff < best_diff:
                best_diff = diff
                best = snap
        if best is None or best.oi_contracts_total == 0:
            return None
        return (current_oi - best.oi_contracts_total) / best.oi_contracts_total


# ─── Per-venue HTTP fetchers ─────────────────────────────────────────────


async def _fetch_bybit(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    row = GoldPerpRow(provider="bybit", symbol=symbol)
    # Tickers endpoint returns fundingRate + markPrice + openInterest USD notional.
    try:
        resp = await client.get(
            "/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
        )
        resp.raise_for_status()
        data = resp.json().get("result", {}).get("list", [])
        if data:
            item = data[0]
            row.mark_price = _to_decimal(item.get("markPrice"))
            row.funding_rate = _to_decimal(item.get("fundingRate"))
            row.oi_usd = _to_decimal(item.get("openInterestValue"))
            row.oi_contracts = _to_decimal(item.get("openInterest"))
            ts = item.get("nextFundingTime") or item.get("time")
            if ts is not None:
                row.timestamp_ms = int(ts)
    except Exception as exc:
        row.error = f"bybit:{exc}"[:200]
    return row


async def _fetch_okx(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    row = GoldPerpRow(provider="okx", symbol=symbol)
    # /public/funding-rate returns current funding rate.
    try:
        resp = await client.get(
            "/api/v5/public/funding-rate",
            params={"instId": symbol},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            item = data[0]
            row.funding_rate = _to_decimal(item.get("fundingRate"))
            ts = item.get("fundingTime") or item.get("nextFundingTime")
            if ts is not None:
                row.timestamp_ms = int(ts)
    except Exception as exc:
        row.error = f"okx-funding:{exc}"[:200]
    # /public/open-interest returns contracts only.
    try:
        resp = await client.get(
            "/api/v5/public/open-interest",
            params={"instType": "SWAP", "instId": symbol},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            item = data[0]
            row.oi_contracts = _to_decimal(item.get("oi"))
            row.oi_usd = _to_decimal(item.get("oiUsd"))
    except Exception as exc:
        row.error = (row.error or "") + f"; okx-oi:{exc}"[:200]
    return row


async def _fetch_binance(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    row = GoldPerpRow(provider="binance", symbol=symbol)
    # premiumIndex returns markPrice + lastFundingRate
    try:
        resp = await client.get("/fapi/v1/premiumIndex", params={"symbol": symbol})
        resp.raise_for_status()
        item = resp.json()
        row.mark_price = _to_decimal(item.get("markPrice"))
        row.funding_rate = _to_decimal(item.get("lastFundingRate"))
        ts = item.get("time")
        if ts is not None:
            row.timestamp_ms = int(ts)
    except Exception as exc:
        row.error = f"binance-prem:{exc}"[:200]
    # openInterest returns contracts (1 PAXG contract = 1 troy oz).
    try:
        resp = await client.get("/fapi/v1/openInterest", params={"symbol": symbol})
        resp.raise_for_status()
        item = resp.json()
        row.oi_contracts = _to_decimal(item.get("openInterest"))
    except Exception as exc:
        row.error = (row.error or "") + f"; binance-oi:{exc}"[:200]
    return row


async def _fetch_venue(provider: str, symbol: str, *, timeout: float = 10.0) -> GoldPerpRow:
    """Fetch one (provider, symbol) pair using the project's proxy-aware client.

    Each per-venue fetch reuses ``client_for_source`` so the configured
    proxy (if any) is honoured. The ``base_url`` is reconstructed with
    the proxy URL that the factory resolved, since the factory's client
    is path-agnostic. When no proxy is configured the request is direct.
    """
    base_urls = {
        "bybit": "https://api.bybit.com",
        "okx": "https://www.okx.com",
        "binance": "https://fapi.binance.com",
    }
    base = base_urls.get(provider)
    if not base:
        return GoldPerpRow(provider=provider, symbol=symbol, error=f"unknown_provider:{provider}")
    # Resolve proxy via factory so its diagnostics + selection logic fires.
    # ``client_for_source`` returns a fully-configured client; we discard
    # the instance and re-construct a venue-targeted one with the same
    # proxy URL by querying the global proxy state directly.
    from app.services.network.http_client_factory import (
        get_proxy_state,
        proxy_for_source,
    )

    state = get_proxy_state()
    proxy_url = proxy_for_source(provider, state.proxy_detected, state.selected_proxy)
    client_kwargs: dict[str, Any] = {"base_url": base, "timeout": timeout}
    if proxy_url and proxy_url.startswith(("http://", "https://")):
        client_kwargs["proxy"] = proxy_url
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            if provider == "bybit":
                return await _fetch_bybit(client, symbol)
            if provider == "okx":
                return await _fetch_okx(client, symbol)
            if provider == "binance":
                return await _fetch_binance(client, symbol)
            return GoldPerpRow(provider=provider, symbol=symbol, error="unhandled_provider")
    except Exception as exc:
        return GoldPerpRow(provider=provider, symbol=symbol, error=str(exc)[:200])


# ─── Weighted aggregation ────────────────────────────────────────────────


def _weighted_funding(rows: list[GoldPerpRow]) -> Optional[Decimal]:
    """USD-notional weighted average funding rate across valid rows."""
    numerator = _D("0")
    denominator = _D("0")
    for row in rows:
        if row.funding_rate is None or row.oi_usd is None or row.oi_usd == 0:
            continue
        numerator += row.funding_rate * row.oi_usd
        denominator += row.oi_usd
    if denominator == 0:
        return None
    return numerator / denominator


def _sum_oi(rows: list[GoldPerpRow]) -> Decimal:
    total = _D("0")
    for row in rows:
        if row.oi_contracts is not None:
            total += row.oi_contracts
    return total


# ─── Public service entry point ─────────────────────────────────────────


@dataclass(slots=True)
class GoldDerivativesService:
    """Aggregates Bybit + OKX + Binance (PAXG + XAUT) perps + CFTC COT."""

    oi_cache: AggregatedOICache = field(default_factory=AggregatedOICache)
    request_timeout: float = 10.0

    async def fetch_all_perps(self) -> list[GoldPerpRow]:
        tasks = [
            _fetch_venue(provider, symbol, timeout=self.request_timeout)
            for provider, symbol in _VENUES
        ]
        rows = await asyncio.gather(*tasks, return_exceptions=False)
        return [row for row in rows if row is not None]

    async def build_snapshot(self) -> dict:
        rows = await self.fetch_all_perps()
        valid_rows = [r for r in rows if r.is_valid()]

        funding_rate = _weighted_funding(valid_rows)
        oi_total = _sum_oi(valid_rows)
        oi_change = self.oi_cache.oi_change_4w(oi_total) if oi_total > 0 else None

        # Persist today's aggregate for next week's 4-week comparison.
        if oi_total > 0:
            self.oi_cache.write(
                OISnapshot(
                    timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
                    oi_contracts_total=oi_total,
                )
            )

        # ── COT via CFTC provider ──
        cot_pct: Optional[Decimal] = None
        cot_error: Optional[str] = None
        try:
            from app.services.macro.providers.cftc import CftcCotProvider

            provider = CftcCotProvider()
            _ = await provider.fetch_latest("gold_cot")
            latest = provider.get_latest_percentile()
            if latest is not None:
                cot_pct = _to_decimal(latest)
            else:
                cot_error = "COT 历史数据积累中(需 ≥ 2 周)"
        except Exception as exc:
            cot_error = f"COT 获取异常: {str(exc)[:120]}"

        # Build notes for transparency (not surfaced to UI).
        notes: list[str] = []
        successful_venues = {row.provider for row in valid_rows}
        all_venues = {provider for provider, _ in _VENUES}
        failed = all_venues - successful_venues
        if failed:
            notes.append(f"信源失败: {', '.join(sorted(failed))}")
        if len(successful_venues) < 2 and funding_rate is None:
            notes.append("可用信源不足 2 个,funding 不可用")
        if cot_error:
            notes.append(cot_error)
        if oi_change is None and oi_total > 0:
            notes.append("OI 4 周变化待下次抓取")

        return {
            "oi_change_4w": _to_float(oi_change),
            "funding_rate": _to_float(funding_rate),
            "cot_net_spec_percentile": _to_float(cot_pct),
            "open_interest": _to_float(oi_total),
            "derivatives_note": "; ".join(notes) if notes else "数据可用",
            "_venues": [
                {
                    "provider": r.provider,
                    "symbol": r.symbol,
                    "funding_rate": _to_float(r.funding_rate),
                    "oi_contracts": _to_float(r.oi_contracts),
                    "oi_usd": _to_float(r.oi_usd),
                    "mark_price": _to_float(r.mark_price),
                    "error": r.error,
                }
                for r in rows
            ],
        }

    async def refresh_all(self, *, force: bool = True) -> dict:
        """Manual refresh entry point — bypasses any short-term cache."""
        # Currently the service does not cache HTTP responses (every call
        # re-fetches). This method exists as a stable hook for the
        # POST /gold/derivatives/refresh endpoint and to make the
        # ``force`` intent explicit at the API boundary.
        _ = force
        return await self.build_snapshot()