"""Static guards for the combined structure context toolbar."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "structure.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_status_sits_below_the_chart_annotation() -> None:
    toolbar_start = PAGE.index('class="hero-card structure-toolbar-card"')
    toolbar_end = PAGE.index('<section class="structure-overview-grid">', toolbar_start)
    toolbar = PAGE[toolbar_start:toolbar_end]
    chart_start = PAGE.index('class="card structure-main-card"', toolbar_end)
    chart_end = PAGE.index('id="structure-chart-panel"', chart_start)
    chart_header = PAGE[chart_start:chart_end]

    assert 'id="structure-statusbar"' not in toolbar
    assert chart_header.index('id="structure-chart-state"') < chart_header.index('id="structure-statusbar"')
    assert 'class="structure-chart-status"' in chart_header
    assert PAGE.count('id="structure-statusbar"') == 1


def test_structure_context_toolbar_is_compact_and_sticky() -> None:
    assert 'body[data-page="market-structure"] .structure-toolbar-card' in EDITORIAL
    assert "position: sticky" in EDITORIAL
    assert "top: calc(var(--topbar-height) + 8px)" in EDITORIAL
    assert "padding: 12px 16px" in EDITORIAL
    assert ".structure-chart-status:empty" in EDITORIAL
