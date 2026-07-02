from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


def movement_label(previous: float | None, current: float | None) -> str:
    if previous is None or current is None:
        return "data_insufficient"
    if current > previous:
        return "rising"
    if current < previous:
        return "falling"
    return "stable"


def movement_summary(points: Sequence[dict[str, Any]], key: str) -> str:
    usable = [point.get(key) for point in points if point.get(key) is not None]
    if len(usable) < 2:
        return "data_insufficient"
    return movement_label(float(usable[-2]), float(usable[-1]))


class JsonSnapshotStore:
    def __init__(self, path: Path, *, max_entries: int = 180) -> None:
        self.path = path
        self.max_entries = max_entries

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def append(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        history = self.load()
        if history and history[-1].get("timestamp") == snapshot.get("timestamp"):
            history[-1] = snapshot
        else:
            history.append(snapshot)
        history = history[-self.max_entries :]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return history
