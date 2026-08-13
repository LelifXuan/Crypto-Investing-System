"""Guards the public-facing fields in the structure summary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "structure.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_internal_weight_template_is_not_rendered() -> None:
    render_start = PAGE.index("function renderSummary(")
    render_end = PAGE.index("\nfunction ", render_start + 1)
    block = PAGE[render_start:render_end]
    assert "权重模板" not in block
    assert "overall.weight_template" not in block


def test_market_state_occupies_the_full_metric_row() -> None:
    assert 'class="metric-box structure-market-state"' in PAGE
    assert """body[data-page="market-structure"] .structure-summary-metrics .structure-market-state {
  grid-column: 1 / -1;
}""" in EDITORIAL
