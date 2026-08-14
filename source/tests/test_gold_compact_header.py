from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app" / "static" / "pages" / "gold_v5.js"
CSS = ROOT / "app" / "static" / "editorial.css"


def test_gold_header_groups_title_decision_and_reference() -> None:
    source = PAGE.read_text(encoding="utf-8")
    start = source.index('<section class="gold-cockpit-header"')
    end = source.index("${hasChartSeries ? renderChartGrid()", start)
    header = source[start:end]

    assert header.index("renderHero(data)") < header.index("renderSpotDca(data)")
    assert header.index("renderSpotDca(data)") < header.index("renderContractRef(data)")


def test_gold_header_uses_one_compact_surface() -> None:
    css = CSS.read_text(encoding="utf-8")

    assert 'body[data-page="gold-allocation"] .gold-cockpit-header {' in css
    assert "gap: 0;" in css
    assert "padding: 16px 22px 14px;" in css
    assert "padding: 13px 18px 14px;" in css
