from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_JS = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"
EDITORIAL_CSS = ROOT / "app" / "static" / "editorial.css"


def test_derivatives_header_groups_summary_decisions_and_controls() -> None:
    source = PAGE_JS.read_text(encoding="utf-8")
    header_start = source.index('<section class="btc-cockpit-header"')
    header_end = source.index("</section>", header_start)
    header = source[header_start:header_end]

    assert header.index("renderHero") < header.index("renderDecisionCards")
    assert header.index("renderDecisionCards") < header.index("renderChartToolbar")


def test_derivatives_header_removes_stacked_card_weight() -> None:
    css = EDITORIAL_CSS.read_text(encoding="utf-8")

    assert 'body[data-page="btc-derivatives"] .btc-cockpit-header' in css
    assert "min-height: 0;" in css
    assert "padding: 13px 18px 12px;" in css
    assert "padding: 11px 18px 12px;" in css
