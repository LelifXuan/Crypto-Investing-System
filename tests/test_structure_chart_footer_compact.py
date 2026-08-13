"""Guards the compact combined footer below the structure chart."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "structure.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_layer_controls_and_snapshot_meta_share_one_footer() -> None:
    render_start = PAGE.index("function renderChart(")
    render_end = PAGE.index("\nfunction renderSummary(", render_start)
    block = PAGE[render_start:render_end]
    footer_start = block.index('<div class="structure-chart-footer">')
    footer = block[footer_start:]
    assert "${buildLayerToggleMarkup()}" in footer
    assert '<div class="structure-chart-meta">' in footer
    assert footer.index("${buildLayerToggleMarkup()}") < footer.index('<div class="structure-chart-meta">')


def test_chart_footer_is_one_compact_flex_row() -> None:
    selector = 'body[data-page="market-structure"] .structure-chart-footer {'
    block = CSS[CSS.index(selector):]
    block = block[:block.index("}")]
    assert "display: flex" in block
    assert "justify-content: space-between" in block
    assert "min-height: 34px" in block
    assert "border-top: 1px solid var(--border)" in block
