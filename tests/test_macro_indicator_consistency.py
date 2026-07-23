from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest
import yaml


REPO = Path(__file__).resolve().parents[1]
API_MAP_PATH = REPO / "app" / "monitoring" / "configs" / "macro_indicator_api_map.v1.json"
CATALOG_PATH = REPO / "app" / "monitoring" / "configs" / "indicator_catalog.yaml"


def _load_api_map() -> dict:
    raw = json.loads(API_MAP_PATH.read_text(encoding="utf-8"))
    # The API map is a dict with an 'indicators' sub-dict (newer format)
    # or a bare dict keyed by indicator_key (older format). Handle both.
    if isinstance(raw, dict) and "indicators" in raw:
        return raw["indicators"]
    return raw


def _load_catalog() -> list[dict]:
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    # The catalog is a dict with an 'indicators' list (newer format) or a
    # bare list (older format). Handle both.
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "indicators" in raw:
        items = raw["indicators"]
        assert isinstance(items, list), "catalog 'indicators' must be a list"
        return items
    raise AssertionError(f"Unexpected catalog top-level type: {type(raw).__name__}")


def _find_catalog_entry(catalog: list[dict], indicator_key: str) -> dict:
    for entry in catalog:
        if entry.get("indicator_key") == indicator_key:
            return entry
    raise KeyError(f"indicator_key {indicator_key!r} not found in catalog")


def test_fed_soma_mbs_symbol_consistent() -> None:
    """fed_soma_mbs must use the same FRED series ID in both the API map
    and the indicator catalog. The canonical series is WSHOMCB
    (Securities Held Outright: Mortgage-Backed Securities, weekly, USD M).
    If a future maintainer changes one file but not the other, this test
    fails."""
    api_map = _load_api_map()
    catalog = _load_catalog()

    api_entry = api_map["fed_soma_mbs"]
    api_symbol = api_entry["sources"][0]["symbol"]
    assert api_symbol == "WSHOMCB", (
        f"macro_indicator_api_map.v1.json fed_soma_mbs.sources[0].symbol "
        f"is {api_symbol!r}; expected 'WSHOMCB'"
    )

    catalog_entry = _find_catalog_entry(catalog, "fed_soma_mbs")
    catalog_symbol = catalog_entry["calc_params"]["external_symbol"]
    assert catalog_symbol == "WSHOMCB", (
        f"indicator_catalog.yaml fed_soma_mbs.calc_params.external_symbol "
        f"is {catalog_symbol!r}; expected 'WSHOMCB'"
    )

    assert api_symbol == catalog_symbol, (
        f"Symbol drift: API map says {api_symbol!r}, catalog says "
        f"{catalog_symbol!r}. They must agree."
    )
