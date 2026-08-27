"""CFTC Commitments of Traders (COT) provider — gold futures speculative positioning."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.core.decimal_utils import D
from app.services.macro.providers.base import MacroFetchResult
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc
logger = logging.getLogger(__name__)

# CFTC Disaggregated Futures+Options COT report (current week)
_COT_URL = "https://www.cftc.gov/dea/newcot/c_disagg.txt"
_COT_HISTORY_URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Gold futures contract identifiers
_GOLD_CONTRACT_NAME = "GOLD - COMMODITY EXCHANGE INC."
_GOLD_CFTC_CODE = "088691"

# Columns in the disaggregated COT CSV
_COL_MARKET = 0
_COL_DATE = 2
_COL_CFTC_CODE = 3
_COL_OI = 7  # Total Open Interest
_COL_MM_LONG = 11  # Managed Money Long
_COL_MM_SHORT = 12  # Managed Money Short

# Percentile cache file (stores historical net positions for percentile calc).
# Persisted to disk so percentile history survives across process restarts.
#
# 2026-08-13: cache root moved from runtime/ (gitignored) to a git-tracked
# ``data/cftc/`` directory so the CFTC weekly report (a public, ~weekly
# dataset) ships with the repo. A cloned checkout gets the same COT baseline
# on first run instead of blocking on a live download; refreshes update the
# file in place (commit the update to share the newer baseline).
_CACHE_MAX_POINTS = 156  # ~3 years of weekly data
_MIN_HISTORY_POINTS = 52
_HISTORY_FILE = "gold_history.json"
_RAW_COT_FILE = "cot_raw.txt"
_REPO_ROOT = Path(__file__).resolve().parents[4]  # app/services/macro/providers/ -> repo root
_COT_DATA_ROOT = _REPO_ROOT / "data" / "cftc"
# The COT report is weekly — re-download at most once per 7 days. Env var
# override keeps tests/operators in control without code edits.
_COT_TTL_SECONDS = float(__import__("os").environ.get("CFTC_COT_TTL_SECONDS", str(7 * 24 * 3600)))


@dataclass(slots=True)
class CftcHistoryCache:
    """Append-only disk-backed ring buffer of weekly ``net_pct_of_oi`` values.

    Each entry is keyed by the report date so re-fetching the same week
    is idempotent. The cache survives process restarts so percentile
    history does not reset every time the workbench endpoint is hit
    with a freshly-constructed provider.
    """

    path: Path
    max_points: int = _CACHE_MAX_POINTS
    _points: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._points = self._load()

    def _load(self) -> list[tuple[str, float]]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        out: list[tuple[str, float]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            date = item.get("date")
            value = item.get("net_pct_of_oi")
            if not isinstance(date, str):
                continue
            try:
                out.append((date, float(value)))
            except (TypeError, ValueError):
                continue
        return out[-self.max_points:]

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"date": d, "net_pct_of_oi": v} for d, v in self._points]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def append(self, report_date: datetime, net_pct_of_oi: float) -> None:
        """Append a new weekly observation, idempotent on date."""
        key = report_date.astimezone(UTC).date().isoformat()
        # Replace existing entry for this week (in case the same week is
        # re-fetched with a revised value).
        self._points = [(d, v) for d, v in self._points if d != key]
        self._points.append((key, float(net_pct_of_oi)))
        if len(self._points) > self.max_points:
            self._points = self._points[-self.max_points:]
        self._flush()

    def extend(self, snapshots: list[CotSnapshot]) -> None:
        """Merge historical observations and flush once, keyed by report date."""

        merged = {date: value for date, value in self._points}
        for snapshot in snapshots:
            key = snapshot.report_date.astimezone(UTC).date().isoformat()
            merged[key] = float(snapshot.net_pct_of_oi)
        self._points = sorted(merged.items())[-self.max_points :]
        self._flush()

    def history(self) -> list[float]:
        """Return net_pct_of_oi history excluding the latest entry.

        Used to compute percentile rank of the current observation
        against its prior peers.
        """
        return [v for _, v in self._points[:-1]]

    def latest(self) -> Optional[float]:
        return self._points[-1][1] if self._points else None

    def __len__(self) -> int:
        return len(self._points)


@dataclass(slots=True)
class CotSnapshot:
    """Parsed COT data for a single contract on a single date."""
    report_date: datetime
    oi_total: int
    managed_money_long: int
    managed_money_short: int

    @property
    def managed_money_net(self) -> int:
        return self.managed_money_long - self.managed_money_short

    @property
    def net_pct_of_oi(self) -> float:
        if self.oi_total <= 0:
            return 0.0
        return self.managed_money_net / self.oi_total


def _parse_int(value: str) -> int:
    return int(value.strip().replace(",", "") or "0")


def _parse_cot_history_csv(
    text: str, contract_name: str = _GOLD_CONTRACT_NAME
) -> list[CotSnapshot]:
    """Parse every matching weekly row from a current or annual CFTC report."""

    snapshots: list[CotSnapshot] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < max(_COL_OI, _COL_MM_LONG, _COL_MM_SHORT) + 1:
            continue
        market = row[_COL_MARKET].strip().strip('"')
        if market.upper() != contract_name.upper():
            continue
        # Double-check CFTC code matches gold
        if row[_COL_CFTC_CODE].strip().strip('"') != _GOLD_CFTC_CODE:
            continue
        try:
            report_date = datetime.strptime(row[_COL_DATE].strip(), "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        try:
            snapshots.append(
                CotSnapshot(
                    report_date=report_date,
                    oi_total=_parse_int(row[_COL_OI]),
                    managed_money_long=_parse_int(row[_COL_MM_LONG]),
                    managed_money_short=_parse_int(row[_COL_MM_SHORT]),
                )
            )
        except ValueError:
            continue
    return sorted(snapshots, key=lambda item: item.report_date)


def _parse_cot_csv(
    text: str, contract_name: str = _GOLD_CONTRACT_NAME
) -> Optional[CotSnapshot]:
    """Parse the latest matching contract row from a CFTC report."""

    snapshots = _parse_cot_history_csv(text, contract_name)
    return snapshots[-1] if snapshots else None


def _parse_cot_history_zip(content: bytes) -> list[CotSnapshot]:
    """Extract all gold observations from an official annual CFTC archive."""

    snapshots: dict[str, CotSnapshot] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".txt", ".csv")):
                continue
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            for snapshot in _parse_cot_history_csv(text):
                snapshots[snapshot.report_date.date().isoformat()] = snapshot
    return sorted(snapshots.values(), key=lambda item: item.report_date)


def _compute_percentile(history: list[float], current: float) -> Optional[float]:
    """Compute the percentile rank of current within history (0.0 to 1.0)."""
    if not history or current is None:
        return None
    below = sum(1 for v in history if v <= current)
    return below / len(history)


class CftcCotProvider:
    """Fetches CFTC COT data for gold futures and computes net speculative positioning.

    Returns the Managed Money net position as a fraction of total open interest.
    Also maintains a percentile history for the ``cot_net_spec_percentile`` metric,
    persisted to disk so the percentile does not reset every request.
    """

    provider_key = "cftc"

    def __init__(
        self,
        history_cache: Optional[CftcHistoryCache] = None,
        *,
        raw_cache_dir: Optional[Path] = None,
    ):
        # Default disk-backed cache so percentile history survives across
        # process restarts. Tests can inject a tmpdir-backed cache.
        self._history_cache = history_cache or CftcHistoryCache(
            path=_COT_DATA_ROOT / _HISTORY_FILE,
        )
        # Raw COT report cache lives in the git-tracked data/ dir so a cloned
        # checkout starts from the shipped baseline (weekly TTL) instead of a
        # 10-20s live download on first request. Tests inject a tmpdir.
        self._raw_cache_dir = raw_cache_dir or _COT_DATA_ROOT
        self._raw_cache_path = self._raw_cache_dir / _RAW_COT_FILE

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "raw_series"

    def _read_raw_cached(self) -> Optional[str]:
        """Return the disk-cached COT text if fresh, else None."""
        if not self._raw_cache_path.exists():
            return None
        try:
            mtime = self._raw_cache_path.stat().st_mtime
            if (time.time() - mtime) >= _COT_TTL_SECONDS:
                return None
            return self._raw_cache_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _write_raw_cache(self, text: str) -> None:
        """Persist fresh COT text to the git-tracked data dir (tmp+replace)."""
        try:
            self._raw_cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._raw_cache_path.with_suffix(".txt.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self._raw_cache_path)
        except OSError:
            # Cache is an optimization — a failed write must not fail the fetch.
            pass

    async def _fetch_cot_text(self) -> str:
        cached = self._read_raw_cached()
        if cached is not None:
            return cached
        async with client_for_source("cftc", timeout=20) as client:
            resp = await client.get(_COT_URL)
        resp.raise_for_status()
        self._write_raw_cache(resp.text)
        return resp.text

    async def _bootstrap_history_if_needed(self) -> None:
        """Rebuild a missing percentile baseline from official annual archives."""

        if len(self._history_cache) >= _MIN_HISTORY_POINTS:
            return
        current_year = datetime.now(UTC).year
        years = range(current_year - 2, current_year + 1)
        try:
            async with client_for_source("cftc", timeout=45) as client:
                responses = await asyncio.gather(
                    *(
                        client.get(_COT_HISTORY_URL.format(year=year))
                        for year in years
                    ),
                    return_exceptions=True,
                )
            snapshots: list[CotSnapshot] = []
            for year, response in zip(years, responses, strict=True):
                if isinstance(response, Exception):
                    logger.warning("CFTC history %s unavailable: %s", year, response)
                    continue
                try:
                    response.raise_for_status()
                    snapshots.extend(_parse_cot_history_zip(response.content))
                except (httpx.HTTPError, ValueError, zipfile.BadZipFile) as exc:
                    logger.warning("CFTC history %s invalid: %s", year, exc)
            if snapshots:
                self._history_cache.extend(snapshots)
        except Exception as exc:  # latest weekly report must remain available
            logger.warning("CFTC history bootstrap failed: %s", exc)

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        await self._bootstrap_history_if_needed()
        text = await self._fetch_cot_text()
        snapshot = _parse_cot_csv(text)
        if snapshot is None:
            raise ValueError(f"Gold COT data not found in CFTC report (key={source_key})")

        net_pct = snapshot.net_pct_of_oi

        # Update on-disk percentile history (idempotent on report date).
        self._history_cache.append(snapshot.report_date, net_pct)
        history = self._history_cache.history()
        percentile = _compute_percentile(history, net_pct)

        return MacroFetchResult(
            observation_ts=snapshot.report_date,
            value=D(str(round(net_pct, 6))),
            source_ref=f"{self.provider_key}:{_GOLD_CFTC_CODE}",
            source_granularity="1w",
            metadata={
                "contract": _GOLD_CONTRACT_NAME,
                "oi_total": snapshot.oi_total,
                "managed_money_long": snapshot.managed_money_long,
                "managed_money_short": snapshot.managed_money_short,
                "managed_money_net": snapshot.managed_money_net,
                "net_pct_of_oi": net_pct,
                "percentile": percentile,
                "history_points": len(self._history_cache),
            },
        )

    def get_latest_percentile(self) -> Optional[float]:
        """Return the percentile of the most recent net position.

        Computed from the on-disk history cache. Returns None when fewer
        than 2 weekly observations exist (percentile undefined).
        """
        if len(self._history_cache) < 2:
            return None
        latest = self._history_cache.latest()
        if latest is None:
            return None
        return _compute_percentile(self._history_cache.history(), latest)

    async def healthcheck(self) -> tuple[str, Optional[str]]:
        try:
            text = await self._fetch_cot_text()
            if _parse_cot_csv(text) is None:
                return "degraded", "Gold contract not found in COT report"
            return "healthy", None
        except Exception as exc:
            return "unhealthy", str(exc)
