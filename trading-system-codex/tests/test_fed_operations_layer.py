"""Tests for the V1.7.3 Fed Balance Sheet Operations layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_scoring_registry_covers_fed_operations_indicators():
    """Every new fed_operations indicator must have a scoring entry."""
    scoring_path = ROOT / "app" / "monitoring" / "configs" / "macro_scoring_registry.v1.json"
    data = json.loads(scoring_path.read_text(encoding="utf-8"))
    scored_keys = {entry["indicator_key"] for entry in data["indicators"]}
    required = {
        "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window", "fed_soma_avg_duration",
        "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
    }
    missing = required - scored_keys
    assert not missing, f"missing scoring entries: {missing}"


def test_macro_overview_has_fed_operations_layer():
    """LAYER_LABELS must include fed_operations as a 7th layer; indicators must be wired via MODULE_TO_LAYER + JSON config."""
    from app.services.macro_overview import LAYER_LABELS, MODULE_TO_LAYER

    assert "fed_operations" in LAYER_LABELS, (
        "LAYER_LABELS must register fed_operations as a top-level layer"
    )
    # LAYER_LABELS is flat dict[str, str]: key -> Chinese label
    assert isinstance(LAYER_LABELS["fed_operations"], str)
    assert LAYER_LABELS["fed_operations"]

    # Indicators per layer come from JSON config module -> MODULE_TO_LAYER mapping.
    assert MODULE_TO_LAYER.get("fed_operations") == "fed_operations"

    api_map_path = ROOT / "app" / "monitoring" / "configs" / "macro_indicator_api_map.v1.json"
    api_map = json.loads(api_map_path.read_text(encoding="utf-8"))
    by_module: dict[str, set[str]] = {}
    for key, item in api_map.get("indicators", {}).items():
        if not isinstance(item, dict):
            continue
        by_module.setdefault(str(item.get("module") or ""), set()).add(key)

    moved_indicators = {"fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"}
    new_indicators = {
        "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window", "fed_soma_avg_duration",
        "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
    }
    fed_indicators = by_module.get("fed_operations", set())
    missing_moved = moved_indicators - fed_indicators
    missing_new = new_indicators - fed_indicators
    assert not missing_moved, f"moved BS indicators missing from fed_operations module: {missing_moved}"
    assert not missing_new, f"new fed_operations indicators missing: {missing_new}"


def test_liquidity_credit_no_longer_contains_bs_indicators():
    """The 4 BS indicators should have moved from liquidity_credit to fed_operations."""
    api_map_path = ROOT / "app" / "monitoring" / "configs" / "macro_indicator_api_map.v1.json"
    api_map = json.loads(api_map_path.read_text(encoding="utf-8"))
    indicators = api_map.get("indicators", {})

    liquidity_keys = {
        key
        for key, item in indicators.items()
        if isinstance(item, dict) and item.get("module") == "liquidity_credit"
    }
    for removed in ("fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"):
        assert removed not in liquidity_keys, (
            f"{removed} should no longer be in liquidity_credit module"
        )