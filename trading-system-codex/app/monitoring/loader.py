from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.monitoring.defaults import CONFIG_DIR


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache
def load_indicator_catalog() -> list[dict]:
    return list(_load_yaml(CONFIG_DIR / "indicator_catalog.yaml").get("indicators", []))


@lru_cache
def load_refresh_policies() -> list[dict]:
    raw = _load_yaml(CONFIG_DIR / "refresh_policies.yaml").get("refresh_policies", {})
    items: list[dict] = []
    for category, rows in raw.items():
        for row in rows or []:
            enriched = dict(row)
            enriched.setdefault("category", category)
            items.append(enriched)
    return items


@lru_cache
def load_alert_rules() -> list[dict]:
    return list(_load_yaml(CONFIG_DIR / "alert_rules.yaml").get("alert_rules", []))
