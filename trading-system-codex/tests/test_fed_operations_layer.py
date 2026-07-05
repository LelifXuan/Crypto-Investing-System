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
    """LAYER_LABELS must include fed_operations as a 7th layer with 4 moved BS indicators."""
    from app.services.macro_overview import LAYER_LABELS
    assert "fed_operations" in LAYER_LABELS
    layer = LAYER_LABELS["fed_operations"]
    assert "label_cn" in layer
    assert "indicators" in layer
    for required in ("fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"):
        assert required in layer["indicators"]
    for required in (
        "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window", "fed_soma_avg_duration",
        "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
    ):
        assert required in layer["indicators"]


def test_liquidity_credit_no_longer_contains_bs_indicators():
    """The 4 BS indicators should have moved to fed_operations."""
    from app.services.macro_overview import LAYER_LABELS
    if "liquidity_credit" in LAYER_LABELS:
        for removed in ("fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"):
            assert removed not in LAYER_LABELS["liquidity_credit"]["indicators"]