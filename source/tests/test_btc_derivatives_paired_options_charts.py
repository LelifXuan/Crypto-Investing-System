"""Static guards for the paired key-level and strike-surface chart row."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "btc_derivatives.js").read_text(encoding="utf-8")


def test_key_levels_and_strike_surface_are_prioritized_as_a_pair() -> None:
    assert '["key_levels_history", "strike_surface", "options_risk_premium_history"]' in PAGE
    assert 'chartId === "key_levels_history" || chartId === "strike_surface"' in PAGE
    assert '{ ...layout, span: 6, density: "surface" }' in PAGE


def test_chart_cards_expose_chart_identity_for_layout_verification() -> None:
    assert 'data-chart-id="${escapeHtml(chartId)}"' in PAGE
