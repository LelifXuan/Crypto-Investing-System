"""CFTC Commitments of Traders (COT) provider — gold futures speculative positioning."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.decimal_utils import D
from app.core.paths import app_paths
from app.services.macro.providers.base import MacroFetchResult
from app.services.network.http_client_factory import client_for_source

UTC = timezone.utc

# CFTC Disaggregated Futures+Options COT report (current week)
_COT_URL = "https://www.cftc.gov/dea/newcot/c_disagg.txt"

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
_CACHE_MAX_POINTS = 156  # ~3 years of weekly data
_HISTORY_FILE = "gold_history.json"
_HISTORY_ROOT = app_paths.cache_dir / "cftc"


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


def _parse_cot_csv(text: str, contract_name: str = _GOLD_CONTRACT_NAME) -> Optional[CotSnapshot]:
    """Parse the CFTC COT CSV text and extract the target contract row."""
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
        return CotSnapshot(
            report_date=report_date,
            oi_total=_parse_int(row[_COL_OI]),
            managed_money_long=_parse_int(row[_COL_MM_LONG]),
            managed_money_short=_parse_int(row[_COL_MM_SHORT]),
        )
    return None


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

    def __init__(self, history_cache: Optional[CftcHistoryCache] = None):
        # Default disk-backed cache so percentile history survives across
        # process restarts. Tests can inject a tmpdir-backed cache.
        self._history_cache = history_cache or CftcHistoryCache(
            path=_HISTORY_ROOT / _HISTORY_FILE,
        )

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind == "raw_series"

    async def _fetch_cot_text(self) -> str:
        async with client_for_source("cftc", timeout=20) as client:
            resp = await client.get(_COT_URL)
        resp.raise_for_status()
        return resp.text

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
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
