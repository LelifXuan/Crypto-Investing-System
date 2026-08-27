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
import copy
import json
import os
import time
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

# Short-TTL in-memory cache for ``build_snapshot()`` (single-flight).
# The workbench endpoint (GET /gold/workbench) previously blocked ~5-6s per
# page load re-fetching all 6 perp venues + CFTC; the UI only needs the
# aggregated view at interactive speed. AGENTS.md §九.2: keep a bounded
# staleness window — 120s is ≪ the 28-day OI comparison horizon, so the
# weekly aggregate stays trustworthy. ``refresh_all()`` (POST
# /gold/derivatives/refresh) bypasses this cache explicitly.
_SNAPSHOT_TTL_SECONDS = float(os.environ.get("GOLD_SNAPSHOT_TTL_SECONDS", "120"))
_snapshot_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_snapshot_fetch_lock = asyncio.Lock()

# Disk-persisted last-known-good layer below the in-memory cache. Perp OI /
# funding are minute-level live data, so this lives under ``runtime/cache``
# (gitignored) rather than the tracked ``data/`` dir — unlike the CFTC weekly
# baseline, venue snapshots are private per-machine fetch results that must
# not ship with the repo. A cold process reads yesterday's aggregate in
# milliseconds instead of blocking on 6 venue HTTP calls; stale-on-fetch
# failure keeps the last good values (AGENTS.md §九.2 stale_revalidating).
_SNAPSHOT_DISK_TTL_SECONDS = float(os.environ.get("GOLD_SNAPSHOT_DISK_TTL_SECONDS", str(6 * 3600)))
_SNAPSHOT_DISK_FILE = _CACHE_DIR / "snapshot.json"


def _read_snapshot_disk() -> dict | None:
    """Return the disk snapshot if fresh (<6h), else None (stale or absent)."""
    if not _SNAPSHOT_DISK_FILE.exists():
        return None
    try:
        mtime = _SNAPSHOT_DISK_FILE.stat().st_mtime
        if (time.time() - mtime) >= _SNAPSHOT_DISK_TTL_SECONDS:
            return None
        data = json.loads(_SNAPSHOT_DISK_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_snapshot_disk_allow_stale() -> dict | None:
    """Return the disk snapshot regardless of age (last-known-good fallback)."""
    if not _SNAPSHOT_DISK_FILE.exists():
        return None
    try:
        data = json.loads(_SNAPSHOT_DISK_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_snapshot_disk(payload: dict) -> None:
    """Persist a fresh snapshot (tmp + replace so a crash never truncates)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _SNAPSHOT_DISK_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_SNAPSHOT_DISK_FILE)
    except OSError:
        # Cache is an optimization — a failed write must not fail the fetch.
        pass

# ─── Per-venue endpoint registry ────────────────────────────────────────
# Each tuple: (provider_key, symbol, kind, funding_endpoint, oi_endpoint)
#
# ``PAXG`` and ``XAUT`` are both kept because each carries distinct
# liquidity. Gate.io and Bitget are the currently verified sources; Bybit
# and Binance remain as optional breadth when the deployment region permits
# them. Invalid OKX instrument ids were removed after the live API returned
# 51001 for both gold contracts.

_VENUES: tuple[tuple[str, str], ...] = (
    ("gateio", "PAXG_USDT"),
    ("gateio", "XAUT_USDT"),
    ("bitget", "PAXGUSDT"),
    ("bitget", "XAUTUSDT"),
    ("bybit", "PAXGUSDT"),
    ("bybit", "XAUTUSDT"),
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
    # OKX exposes funding rate + OI on two distinct endpoints; issue them
    # concurrently so a slow OI response does not add to funding latency.
    async def _funding() -> dict | None:
        try:
            resp = await client.get(
                "/api/v5/public/funding-rate",
                params={"instId": symbol},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0] if data else None
        except Exception as exc:
            row.error = f"okx-funding:{exc}"[:200]
            return None

    async def _open_interest() -> dict | None:
        try:
            resp = await client.get(
                "/api/v5/public/open-interest",
                params={"instType": "SWAP", "instId": symbol},
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0] if data else None
        except Exception as exc:
            row.error = (row.error or "") + f"; okx-oi:{exc}"[:200]
            return None

    funding_item, oi_item = await asyncio.gather(_funding(), _open_interest())
    if funding_item:
        row.funding_rate = _to_decimal(funding_item.get("fundingRate"))
        ts = funding_item.get("fundingTime") or funding_item.get("nextFundingTime")
        if ts is not None:
            row.timestamp_ms = int(ts)
    if oi_item:
        row.oi_contracts = _to_decimal(oi_item.get("oi"))
        row.oi_usd = _to_decimal(oi_item.get("oiUsd"))
    return row


async def _fetch_binance(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    row = GoldPerpRow(provider="binance", symbol=symbol)
    # Binance exposes markPrice + fundingRate on /premiumIndex and OI on
    # /openInterest; run both concurrently so the per-venue wall time is
    # bounded by the slowest of the two endpoints.
    async def _premium() -> dict | None:
        try:
            resp = await client.get("/fapi/v1/premiumIndex", params={"symbol": symbol})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            row.error = f"binance-prem:{exc}"[:200]
            return None

    async def _open_interest() -> dict | None:
        try:
            resp = await client.get("/fapi/v1/openInterest", params={"symbol": symbol})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            row.error = (row.error or "") + f"; binance-oi:{exc}"[:200]
            return None

    prem_item, oi_item = await asyncio.gather(_premium(), _open_interest())
    if prem_item:
        row.mark_price = _to_decimal(prem_item.get("markPrice"))
        row.funding_rate = _to_decimal(prem_item.get("lastFundingRate"))
        ts = prem_item.get("time")
        if ts is not None:
            row.timestamp_ms = int(ts)
    if oi_item:
        row.oi_contracts = _to_decimal(oi_item.get("openInterest"))
    return row


async def _fetch_gateio(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    """Fetch one Gate.io contract and normalize OI to token quantity."""
    row = GoldPerpRow(provider="gateio", symbol=symbol)
    try:
        resp = await client.get(f"/api/v4/futures/usdt/contracts/{symbol}")
        resp.raise_for_status()
        item = resp.json()
        row.mark_price = _to_decimal(item.get("mark_price"))
        row.funding_rate = _to_decimal(item.get("funding_rate"))
        position_size = _to_decimal(item.get("position_size"))
        multiplier = _to_decimal(item.get("quanto_multiplier"))
        # Gate reports integer contracts. Other venues report base-token OI,
        # so normalize before aggregating PAXG/XAUT quantities.
        if position_size is not None and multiplier is not None:
            row.oi_contracts = position_size * multiplier
        if row.oi_contracts is not None and row.mark_price is not None:
            row.oi_usd = row.oi_contracts * row.mark_price
        funding_next = item.get("funding_next_apply")
        if funding_next is not None:
            row.timestamp_ms = int(funding_next) * 1000
    except Exception as exc:
        row.error = f"gateio:{exc}"[:200]
    return row


async def _fetch_bitget(client: httpx.AsyncClient, symbol: str) -> GoldPerpRow:
    """Fetch Bitget funding, mark price and base-token OI from one ticker."""
    row = GoldPerpRow(provider="bitget", symbol=symbol)
    try:
        resp = await client.get(
            "/api/v2/mix/market/ticker",
            params={"symbol": symbol, "productType": "USDT-FUTURES"},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != "00000":
            raise RuntimeError(
                f"Bitget API {payload.get('code')}: {payload.get('msg', 'unknown error')}"
            )
        data = payload.get("data") or []
        if data:
            item = data[0]
            row.mark_price = _to_decimal(item.get("markPrice"))
            row.funding_rate = _to_decimal(item.get("fundingRate"))
            row.oi_contracts = _to_decimal(item.get("holdingAmount"))
            if row.oi_contracts is not None and row.mark_price is not None:
                row.oi_usd = row.oi_contracts * row.mark_price
            ts = item.get("ts") or payload.get("requestTime")
            if ts is not None:
                row.timestamp_ms = int(ts)
    except Exception as exc:
        row.error = f"bitget:{exc}"[:200]
    return row


async def _fetch_venue(provider: str, symbol: str, *, timeout: float = 10.0) -> GoldPerpRow:
    """Fetch one (provider, symbol) pair using the project's proxy-aware client.

    Each per-venue fetch reuses ``client_for_source`` so the configured
    proxy (if any) is honoured. The ``base_url`` is reconstructed with
    the proxy URL that the factory resolved, since the factory's client
    is path-agnostic. When no proxy is configured the request is direct.
    """
    base_urls = {
        "gateio": "https://api.gateio.ws",
        "bitget": "https://api.bitget.com",
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
            if provider == "gateio":
                return await _fetch_gateio(client, symbol)
            if provider == "bitget":
                return await _fetch_bitget(client, symbol)
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
    """Aggregate multi-venue PAXG/XAUT perps and the official CFTC COT."""

    oi_cache: AggregatedOICache = field(default_factory=AggregatedOICache)
    request_timeout: float = 10.0

    async def fetch_all_perps(self) -> list[GoldPerpRow]:
        tasks = [
            _fetch_venue(provider, symbol, timeout=self.request_timeout)
            for provider, symbol in _VENUES
        ]
        rows = await asyncio.gather(*tasks, return_exceptions=False)
        return [row for row in rows if row is not None]

    def read_cached_snapshot(self) -> dict:
        """Return memory/disk LKG without performing any network I/O.

        The workbench's spot price and technical summary must never wait for
        the six-venue derivatives fan-out. The dedicated derivatives endpoint
        remains responsible for refreshing this optional enhancement.
        """
        now = time.monotonic()
        cached = _snapshot_cache["payload"]
        if cached is not None and (now - _snapshot_cache["ts"]) < _SNAPSHOT_TTL_SECONDS:
            return copy.deepcopy(cached)
        disk = _read_snapshot_disk() or _read_snapshot_disk_allow_stale()
        if disk is None:
            return {}
        _snapshot_cache["ts"] = now
        _snapshot_cache["payload"] = disk
        return copy.deepcopy(disk)

    async def build_snapshot(self) -> dict:
        """Cached entry point — memory → disk (last-known-good) → live.

        Concurrent callers (workbench + derivatives endpoints) share one
        HTTP fan-out instead of each re-fetching 6 perp venues + CFTC.
        Returns a deep copy so callers cannot mutate the cache.
        Use ``refresh_all(force=True)`` to bypass.
        """
        now = time.monotonic()
        async with _snapshot_fetch_lock:
            cached = _snapshot_cache["payload"]
            if cached is not None and (now - _snapshot_cache["ts"]) < _SNAPSHOT_TTL_SECONDS:
                return copy.deepcopy(cached)
            # Cold process / expired memory → disk last-known-good (ms, no HTTP).
            disk = _read_snapshot_disk()
            if disk is not None:
                _snapshot_cache["ts"] = now
                _snapshot_cache["payload"] = disk
                return copy.deepcopy(disk)
            payload = await self._build_snapshot_uncached()
            # Live fetch returned no usable venue data (e.g. regional blocks /
            # network flake) but a stale disk copy exists → keep last-known-good
            # instead of degrading the UI to zeros (AGENTS.md §九.2). Do NOT
            # re-write the stale payload (would refresh its TTL); it only backs
            # the in-memory copy until the next live fetch succeeds.
            if not payload.get("open_interest"):
                stale = _read_snapshot_disk_allow_stale()
                if stale is not None:
                    stale["derivatives_note"] = "实时抓取不可用，展示磁盘缓存(可能过期)"
                    payload = stale
            else:
                _write_snapshot_disk(payload)
            _snapshot_cache["ts"] = now
            _snapshot_cache["payload"] = payload
            return copy.deepcopy(payload)

    async def _build_snapshot_uncached(self) -> dict:
        rows = await self.fetch_all_perps()
        valid_rows = [r for r in rows if r.is_valid()]
        successful_venues = {row.provider for row in valid_rows}

        funding_rate = _weighted_funding(valid_rows)
        # A single provider is useful diagnostically but must not determine a
        # cross-venue funding signal. Preserve the documented two-source gate.
        if len(successful_venues) < 2:
            funding_rate = None
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
        all_venues = {provider for provider, _ in _VENUES}
        failed = all_venues - successful_venues
        if failed:
            notes.append(f"信源失败: {', '.join(sorted(failed))}")
        if len(successful_venues) < 2:
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
        """Manual refresh entry point — bypasses the short-TTL cache.

        Fetches fresh perp + COT data unconditionally (when ``force``) and
        replaces both the in-memory and disk caches, so the UI's refresh
        button and the POST /gold/derivatives/refresh endpoint get live data
        instead of a ≤120s-old snapshot.
        """
        if not force:
            return await self.build_snapshot()
        payload = await self._build_snapshot_uncached()
        if payload.get("open_interest"):
            _write_snapshot_disk(payload)
        else:
            # A manual refresh must not replace a valid last-known-good file
            # with an all-failed payload. Keep the old market observation and
            # surface the refresh failure explicitly.
            stale = _read_snapshot_disk_allow_stale()
            if stale is not None:
                stale["derivatives_note"] = "实时刷新失败，保留磁盘缓存(可能过期)"
                payload = stale
        _snapshot_cache["ts"] = time.monotonic()
        _snapshot_cache["payload"] = payload
        return copy.deepcopy(payload)
