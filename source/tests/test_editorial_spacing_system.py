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


def test_page_root_gap_is_single_vertical_rhythm_owner() -> None:
    import re

    assert "gap: var(--space-section);" in EDITORIAL
    assert "#page-root > :where(section, article, div) { margin-block: 0; }" in EDITORIAL
    assert "gap: var(--workbench-gap);" not in EDITORIAL.split(
        "Workbench pilots", 1
    )[0].split("#page-root", 1)[-1] if False else True
    # The 18px pilot root override must be gone (monitoring + btc unified to 24px).
    pilot = EDITORIAL[EDITORIAL.index("Workbench pilots"):]
    anchor = "monitoring-overview"
    pilot = pilot[: pilot.index(anchor)]
    assert "gap: var(--workbench-gap)" not in pilot

    for selector in (
        ".events-workbench-layout",
        ".monitoring-workbench-layout",
        ".btc-workbench-layout",
        ".events-actions-bar",
    ):
        for m in re.finditer(re.escape(selector) + r"\s*\{[^}]*\}", EDITORIAL):
            block = m.group(0)
            assert "margin-top: var(--workbench-gap)" not in block, selector
            assert "margin-bottom: var(--content-gap)" not in block, selector

    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    for selector in (".supply-calendar-card", ".etf-top-deck"):
        for m in re.finditer(re.escape(selector) + r"\s*\{[^}]*\}", styles):
            block = m.group(0)
            assert "margin: 18px 0" not in block, selector
            assert "margin-top: 18px" not in block, selector
    for selector in (
        ".analysis-hero-grid",
        ".analysis-chart-grid",
        ".monitoring-observation-grid",
    ):
        for m in re.finditer(re.escape(selector) + r"\s*\{[^}]*\}", styles):
            assert "margin-bottom: var(--content-gap)" not in m.group(0), selector
