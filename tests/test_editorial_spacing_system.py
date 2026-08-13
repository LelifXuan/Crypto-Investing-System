"""Static guards for the editorial spacing hierarchy and ETF action group."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
ETF = (ROOT / "app" / "static" / "pages" / "ashare_etf.js").read_text(encoding="utf-8")


def test_shared_spacing_roles_are_defined_and_used_by_component_groups() -> None:
    for token in (
        "--space-inline: 6px",
        "--space-action: 8px",
        "--space-control: 12px",
        "--space-card: 16px",
        "--space-section: 24px",
    ):
        assert token in EDITORIAL

    assert ".etf-mode-inline" in EDITORIAL
    assert "gap: var(--space-action)" in EDITORIAL
    assert "gap: var(--space-control)" in EDITORIAL
    assert "gap: var(--space-card)" in EDITORIAL
    assert "gap: var(--space-section)" in EDITORIAL


def test_etf_execution_actions_have_no_redundant_mode_label() -> None:
    assert '<span class="etf-mode-label">执行模式</span>' not in ETF
    assert 'id="etf-refresh-button"' in ETF
    assert 'data-dropdown-id="etf-mode"' in ETF


def test_compact_dropdown_matches_compact_action_height() -> None:
    compact = EDITORIAL[EDITORIAL.index('.dropdown[data-dropdown-size="compact"]'):]
    assert "min-height: 38px" in compact
    assert "height: 38px" in compact
    assert "border-radius: 6px" in compact
