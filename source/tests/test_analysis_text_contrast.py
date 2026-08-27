from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL_CSS = ROOT / "app" / "static" / "editorial.css"


def test_analysis_typography_uses_page_scoped_contrast_tokens() -> None:
    css = EDITORIAL_CSS.read_text(encoding="utf-8")

    assert 'body[data-page="market-analysis"] {' in css
    assert "--analysis-text-strong: #2f2939;" in css
    assert "--analysis-text-body: #48404f;" in css
    assert "--analysis-text-muted: #5a5361;" in css


def test_analysis_values_and_supporting_copy_keep_a_clear_hierarchy() -> None:
    css = EDITORIAL_CSS.read_text(encoding="utf-8")

    assert '#page-root :is(.live-price, .signal-value)' in css
    assert ':is(#analysis-summary, .signal-copy, .realtime-card .mini-card span)' in css
    assert ':is(.signal-label, .realtime-card .mini-card small)' in css
    assert ".realtime-card .mini-card strong" in css
    assert "color: var(--analysis-text-strong);" in css
    assert "color: var(--analysis-text-body);" in css
    assert "color: var(--analysis-text-muted);" in css
    assert "font-variant-numeric: tabular-nums;" in css
