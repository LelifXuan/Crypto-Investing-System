from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.monitoring.defaults import CONFIG_DIR

SOURCE_CATALOG_PATH = CONFIG_DIR / "market_event_source_catalog.yaml"
NORMALIZATION_RULES_PATH = CONFIG_DIR / "market_event_normalization_rules.yaml"


@dataclass(slots=True)
class MarketEventSource:
    source_id: str
    provider_name: str
    entry_url: str
    category: str
    access_mode: str = "rss"
    reliability: str = "medium"
    official_priority: str = "media"
    access_confidence: str = "medium"
    enabled: bool = True
    item_limit: int = 20
    poll_interval_sec: int = 1800
    tags: list[str] = field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache
def load_market_event_sources() -> list[MarketEventSource]:
    raw = _load_yaml(SOURCE_CATALOG_PATH).get("sources", [])
    items: list[MarketEventSource] = []
    for row in raw:
        items.append(
            MarketEventSource(
                source_id=row["source_id"],
                provider_name=row["provider_name"],
                entry_url=row["entry_url"],
                category=row.get("category", "news"),
                access_mode=row.get("access_mode", "rss"),
                reliability=row.get("reliability", "medium"),
                official_priority=row.get("official_priority", "media"),
                access_confidence=row.get("access_confidence", "medium"),
                enabled=bool(row.get("enabled", True)),
                item_limit=int(row.get("item_limit", 20)),
                poll_interval_sec=int(row.get("poll_interval_sec", 1800)),
                tags=list(row.get("tags", [])),
            )
        )
    return items


@lru_cache
def load_market_event_normalization_rules() -> dict:
    return _load_yaml(NORMALIZATION_RULES_PATH)
