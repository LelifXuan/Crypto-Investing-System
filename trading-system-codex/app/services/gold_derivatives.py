"""Gold derivatives data — Gate.io OI/funding rate + COT local cache."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.core.paths import app_paths

_CACHE_DIR = app_paths.data_dir
_CACHE_FILE = "xaut_oi_cache.json"
_COT_FILE = "cot_snapshot.json"
_MAX_OI_SNAPSHOTS = 5
_WEEKS_FOR_OI_CHANGE = 4


@dataclass(slots=True)
class OISnapshot:
    timestamp: str
    oi_value: float


class OICache:
    """Persist OI snapshots to compute 4-week change."""

    def __init__(self, cache_dir: Optional[Path] = None, max_snapshots: int = _MAX_OI_SNAPSHOTS) -> None:
        self.cache_path = (cache_dir or _CACHE_DIR) / _CACHE_FILE
        self.max_snapshots = max_snapshots

    def read_latest(self) -> Optional[OISnapshot]:
        all_snaps = self._read_all()
        return all_snaps[-1] if all_snaps else None

    def write(self, snapshot: OISnapshot) -> None:
        all_snaps = self._read_all()
        all_snaps.append(snapshot)
        seen: set[str] = set()
        unique: list[OISnapshot] = []
        for snap in reversed(all_snaps):
            if snap.timestamp not in seen:
                seen.add(snap.timestamp)
                unique.append(snap)
        unique.reverse()
        unique = unique[-self.max_snapshots:]
        raw = [{"timestamp": s.timestamp, "oi_value": s.oi_value} for s in unique]
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def oi_change_4w(self) -> Optional[float]:
        all_snaps = self._read_all()
        if len(all_snaps) < 2:
            return None
        latest = all_snaps[-1]
        try:
            latest_dt = datetime.fromisoformat(latest.timestamp)
        except ValueError:
            return None
        target = latest_dt.replace(tzinfo=None)
        best: Optional[OISnapshot] = None
        best_diff = float("inf")
        for snap in all_snaps[:-1]:
            try:
                snap_dt = datetime.fromisoformat(snap.timestamp)
            except ValueError:
                continue
            diff = abs(((target - snap_dt.replace(tzinfo=None)).total_seconds() / 86400) - (_WEEKS_FOR_OI_CHANGE * 7))
            if diff < best_diff:
                best_diff = diff
                best = snap
        if best is None or best.oi_value == 0:
            return None
        return (latest.oi_value - best.oi_value) / best.oi_value

    def _read_all(self) -> list[OISnapshot]:
        if not self.cache_path.exists():
            return []
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        result: list[OISnapshot] = []
        for item in raw:
            if isinstance(item, dict) and "timestamp" in item and "oi_value" in item:
                try:
                    result.append(OISnapshot(
                        timestamp=str(item["timestamp"]),
                        oi_value=float(item["oi_value"]),
                    ))
                except (TypeError, ValueError):
                    continue
        return result


class COTCache:
    """Read COT snapshot from local goldhub file."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or app_paths.resource_root / "data" / "goldhub"
        self.cot_path = self.data_dir / _COT_FILE

    def read(self) -> Optional[dict]:
        if not self.cot_path.exists():
            return None
        try:
            return json.loads(self.cot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def read_percentile(self) -> Optional[float]:
        data = self.read()
        if not data:
            return None
        for key in ("cot_net_spec_percentile", "cot_percentile"):
            value = data.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None


class GoldDerivativesService:
    """Fetch Gate.io OI/funding rate and load local COT data."""

    GATEIO_CONTRACT_URL = "https://api.gateio.ws/api/v4/futures/usdt/contracts/XAUT_USDT"

    def __init__(self) -> None:
        self.oi_cache = OICache()

    async def build_snapshot(self) -> dict:
        oi_value: Optional[float] = None
        funding_rate: Optional[float] = None
        gateio_error: Optional[str] = None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.GATEIO_CONTRACT_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_oi = data.get("open_interest")
                    if raw_oi is not None:
                        try:
                            oi_value = float(raw_oi)
                        except (TypeError, ValueError):
                            pass
                    raw_fr = data.get("funding_rate")
                    if raw_fr is not None:
                        try:
                            funding_rate = float(raw_fr)
                        except (TypeError, ValueError):
                            pass
        except Exception as exc:
            gateio_error = str(exc)[:200]

        if oi_value is not None:
            now = datetime.now(timezone.utc).isoformat()
            self.oi_cache.write(OISnapshot(timestamp=now, oi_value=oi_value))

        oi_change = self.oi_cache.oi_change_4w()
        cot_pct = COTCache().read_percentile()

        notes: list[str] = []
        if gateio_error:
            notes.append("Gate.io 请求异常")
        if oi_change is None:
            oi_count = len(self.oi_cache._read_all())
            notes.append(f"OI 数据积累中（{oi_count}/{_MAX_OI_SNAPSHOTS} 周）")
        if cot_pct is None:
            notes.append("COT 数据待录入")

        return {
            "oi_change_4w": oi_change,
            "funding_rate": funding_rate,
            "cot_net_spec_percentile": cot_pct,
            "derivatives_note": "；".join(notes) if notes else "数据可用",
        }
