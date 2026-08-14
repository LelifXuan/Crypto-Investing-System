"""Guards the monitoring macro panel's editorial, non-card-wall treatment."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
MONITORING = (ROOT / "app" / "static" / "pages" / "monitoring.js").read_text(encoding="utf-8")


def test_macro_score_uses_brand_surface_instead_of_legacy_green_gradient() -> None:
    selector = 'body[data-page="monitoring-overview"] .macro-score-block {'
    block = EDITORIAL[EDITORIAL.index(selector):]
    block = block[:block.index("}")]
    assert "background: var(--accent-soft)" in block
    assert "linear-gradient" not in block


def test_macro_layers_form_a_two_column_ledger() -> None:
    assert 'body[data-page="monitoring-overview"] .macro-layer-strip {' in EDITORIAL
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in EDITORIAL
    assert 'body[data-page="monitoring-overview"] .macro-layer-card {' in EDITORIAL
    assert "border-radius: 0" in EDITORIAL
    assert "box-shadow: none" in EDITORIAL


def test_terminal_summary_votes_are_bound_into_one_definition_grid() -> None:
    selector = 'body[data-page="monitoring-overview"] .terminal-summary-votes {'
    block = EDITORIAL[EDITORIAL.index(selector):]
    block = block[:block.index("}")]
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in block
    assert "gap: 0" in block
    assert "border: 1px solid var(--border)" in block
    assert 'body[data-page="monitoring-overview"] .terminal-summary-vote {' in EDITORIAL


def test_terminal_summary_drops_redundant_short_execution_caveat() -> None:
    assert '.replace("追空质量取决于反弹失败或前低跌破确认。", "")' in MONITORING


def test_macro_indicator_cards_have_a_small_consistent_gap() -> None:
    selector = 'body[data-page="monitoring-overview"] .macro-indicator-grid {'
    block = EDITORIAL[EDITORIAL.index(selector):]
    block = block[:block.index("}")]
    assert "gap: var(--space-inline)" in block
    assert "border: 0" in block

    assert """body[data-page="monitoring-overview"] .macro-indicator-card {
  min-height: 122px;
  margin: 0;
  border: 1px solid var(--border);
  background: var(--surface-elevated);
}""" in EDITORIAL
