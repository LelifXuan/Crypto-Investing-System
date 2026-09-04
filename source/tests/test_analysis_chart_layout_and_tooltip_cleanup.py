"""Guards the six-chart order and the editorial floating-surface theme."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_analysis_page_title_has_no_unrelated_knowledge_tooltip() -> None:
    title_line = next(line for line in PAGE.splitlines() if "行情与指标一体视图" in line)
    assert "knowledgeTooltip" not in title_line


def test_six_charts_use_the_requested_three_by_two_reading_order() -> None:
    expected = {
        "analysis-chart-ema": (1, 1),
        "analysis-chart-vegas": (2, 1),
        "analysis-chart-macd": (1, 2),
        "analysis-chart-volume": (2, 2),
        "analysis-chart-boll": (1, 3),
        "analysis-chart-rsi": (2, 3),
    }
    for class_name, (column, row) in expected.items():
        assert f"analysis-chart-card {class_name}" in PAGE
        assert f".{class_name} {{ grid-column: {column}; grid-row: {row}; }}" in EDITORIAL


def test_floating_surfaces_use_editorial_paper_tokens() -> None:
    block = EDITORIAL[EDITORIAL.index("/* Floating surfaces use"):]
    assert ".tooltip-bubble," in block
    assert ".page-guide-panel" in block
    assert "background: var(--surface-elevated)" in block
    assert "color: var(--text-primary)" in block
    assert ".dropdown-popover {" in block
    dropdown_block = block[block.index(".dropdown-popover {"):]
    dropdown_block = dropdown_block[:dropdown_block.index("}")]
    assert "background: var(--surface)" in dropdown_block


def test_market_regime_rail_uses_shared_section_spacing() -> None:
    root_rule = (
        'body[data-page="market-analysis"] #page-root '
        '{ display: grid; gap: var(--space-section); }'
    )
    assert root_rule in EDITORIAL
    assert ':is(.analysis-hero-grid, #analysis-signal-cards) { margin-bottom: 0; }' in EDITORIAL
    assert '.status-mode-badge { margin-block: 0; }' in EDITORIAL


def test_mark_snapshot_returns_to_compact_right_rail_proportion() -> None:
    assert (
        '.analysis-hero-grid { grid-template-columns: minmax(620px, 1fr) '
        'minmax(300px, 0.34fr);'
    ) in EDITORIAL
    assert (
        '@media (max-width: 1180px)' in EDITORIAL
        and '.analysis-hero-grid { grid-template-columns: 1fr; }' in EDITORIAL
    )


def test_indicator_cards_use_balanced_rows_and_aligned_content_tracks() -> None:
    assert "grid-template-columns: repeat(20, minmax(0, 1fr))" in EDITORIAL
    assert "#analysis-signal-cards > :nth-child(n + 6) { grid-column: span 5; }" in EDITORIAL
    assert "grid-template-rows: auto minmax(52px, auto)" in EDITORIAL


def test_vwap_interpretation_uses_formula_not_prose_comparison() -> None:
    assert "现价 > VWAP50 > VWAP100；VWAP50 斜率 > 0" in PAGE
    assert "现价 < VWAP50 < VWAP100；VWAP50 斜率 < 0" in PAGE
    assert "价格位于 VWAP50 上方" not in PAGE


def test_analysis_status_does_not_render_inert_regime_buttons() -> None:
    assert "analysis-regime-objects" not in PAGE
    assert "analysis-regime-objects" not in EDITORIAL
    assert 'analysis:volatility-phase' not in PAGE
    assert 'analysis:directional-bias' not in PAGE
