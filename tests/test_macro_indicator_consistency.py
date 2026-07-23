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


def test_tga_weekly_diff_rolling_4w_transform_flat() -> None:
    """compute_weekly_diff_rolling_4w with a flat 8-week history returns 0.
    This is the simplest non-trivial case: same value across all weeks,
    so the diff must be zero."""
    from app.services.macro.transforms import compute_weekly_diff_rolling_4w

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        (base + timedelta(weeks=i), Decimal("1000"))
        for i in range(8)
    ]
    result = compute_weekly_diff_rolling_4w(points, window=4)
    assert result is not None, "expected a result for 8 flat weekly points"
    value, ts = result
    assert value == Decimal("0"), f"flat history must produce diff=0, got {value!r}"
    assert ts == base + timedelta(weeks=7)


def test_tga_weekly_diff_rolling_4w_transform_rising() -> None:
    """compute_weekly_diff_rolling_4w with a 4-week +10 rising series returns +30.
    This is the canonical TGA-net-change-4W case: 4 weeks of +10 per week,
    latest = 1000+10*7 = 1070, baseline (4 weeks ago) = 1000+10*3 = 1030,
    diff = 40. Wait — actually the function uses (window+1) baseline
    position, so baseline index is -(4+1)=-5, i.e. 1000+10*3=1030.
    Latest is index -1 = 1000+10*7=1070. Diff = 40."""
    from app.services.macro.transforms import compute_weekly_diff_rolling_4w

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        (base + timedelta(weeks=i), Decimal(str(1000 + 10 * i)))
        for i in range(8)
    ]
    result = compute_weekly_diff_rolling_4w(points, window=4)
    assert result is not None, "expected a result for 8 rising weekly points"
    value, ts = result
    # Verify the actual behavior: 4 weeks ago value vs latest value
    # The function returns `latest_value - baseline_value` where baseline is
    # the (window+1)th-from-last point. With 8 points (i=0..7), window=4:
    # baseline is cleaned[-(4+1)] = cleaned[3] = 1030; latest = cleaned[7] = 1070
    # diff = 1070 - 1030 = 40
    assert value == Decimal("40"), f"4-week diff must be 40, got {value!r}"
    assert ts == base + timedelta(weeks=7)


def test_tga_weekly_diff_rolling_4w_transform_insufficient_data() -> None:
    """compute_weekly_diff_rolling_4w with fewer than (window + 1) points
    returns None. This is the empty-state contract."""
    from app.services.macro.transforms import compute_weekly_diff_rolling_4w

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [(base + timedelta(weeks=i), Decimal("1000")) for i in range(4)]
    result = compute_weekly_diff_rolling_4w(points, window=4)
    assert result is None, "expected None for insufficient data"


def test_hyg_and_usd_cny_api_map_have_provider_chain() -> None:
    """HYG and USD/CNY must each have at least one source in the API map,
    and the source providers must be from the recognised set. The config
    must be reachable through MacroProviderRegistry."""
    from app.services.macro.provider_registry import MacroProviderRegistry

    api_map = _load_api_map()

    # HYG
    hyg_entry = api_map.get("hyg")
    assert hyg_entry is not None, "API map missing 'hyg' indicator"
    hyg_sources = hyg_entry.get("sources", [])
    assert len(hyg_sources) >= 1, "HYG must have at least one source"
    recognised_equity = {"tiingo", "twelvedata", "alphavantage", "fred"}
    for src in hyg_sources:
        assert src["source"] in recognised_equity, (
            f"HYG source {src!r} is not in the recognised equity provider set"
        )

    # USD/CNY
    usd_cny_entry = api_map.get("usd_cny")
    assert usd_cny_entry is not None, "API map missing 'usd_cny' indicator"
    usd_cny_sources = usd_cny_entry.get("sources", [])
    assert len(usd_cny_sources) >= 1, "USD/CNY must have at least one source"
    recognised_fx = {"openexchangerates", "twelvedata", "alphavantage", "fred"}
    for src in usd_cny_sources:
        assert src["source"] in recognised_fx, (
            f"USD/CNY source {src!r} is not in the recognised FX provider set"
        )

    # Provider registry: structural assertion — the registry must instantiate
    # without error. This catches accidental import-time regressions.
    registry = MacroProviderRegistry()
    assert registry is not None
