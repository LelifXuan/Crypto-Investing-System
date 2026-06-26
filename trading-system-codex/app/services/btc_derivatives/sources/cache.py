from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.paths import app_paths


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class LiveSourceCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or app_paths.cache_dir / "btc_derivatives_live"
        self.raw_root = self.root / "raw"
        self.snapshot_path = self.root / "normalized_snapshot.json"
        self.health_path = self.root / "provider_health.json"
        self.history_path = self.root / "daily_history.json"

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _read(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default

    def write_raw(self, provider: str, endpoint: str, payload: Any) -> None:
        self._write(
            self.raw_root / provider / f"{endpoint}.json",
            {"fetched_at": _now_iso(), "payload": payload},
        )

    def read_raw(self, provider: str, endpoint: str, ttl_seconds: int) -> Any | None:
        cached = self._read(self.raw_root / provider / f"{endpoint}.json", None)
        if not cached:
            return None
        fetched_at = _parse(cached.get("fetched_at"))
        if fetched_at is None:
            return None
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        return cached.get("payload") if age <= ttl_seconds else None

    def write_snapshot(self, payload: dict[str, Any]) -> None:
        self._write(self.snapshot_path, payload)

    def read_snapshot(self, max_age_seconds: int) -> dict[str, Any] | None:
        cached = self._read(self.snapshot_path, None)
        if not cached:
            return None
        timestamp = _parse(cached.get("data_timestamp"))
        if timestamp is None:
            return None
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return cached if age <= max_age_seconds else None

    def write_health(self, payload: list[dict[str, Any]]) -> None:
        self._write(self.health_path, {"updated_at": _now_iso(), "providers": payload})

    def read_health(self) -> list[dict[str, Any]]:
        return self._read(self.health_path, {}).get("providers", [])

    def append_daily(self, point: dict[str, Any]) -> list[dict[str, Any]]:
        history = self._read(self.history_path, [])
        day = str(point.get("timestamp", ""))[:10]
        history = [item for item in history if str(item.get("timestamp", ""))[:10] != day]
        history.append(point)
        history.sort(key=lambda item: str(item.get("timestamp", "")))
        history = history[-400:]
        self._write(self.history_path, history)
        return history

    def read_history(self) -> list[dict[str, Any]]:
        return self._read(self.history_path, [])
