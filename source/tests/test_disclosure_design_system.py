"""Static guards for the canonical cross-page disclosure component."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "app/static/ui/disclosure.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

ACTIVE_PAGES = {
    "monitoring": ROOT / "app/static/pages/monitoring.js",
    "macro-calendar": ROOT / "app/static/pages/macro_calendar.js",
    "market-events": ROOT / "app/static/pages/market_events.js",
    "btc-derivatives": ROOT / "app/static/pages/btc_derivatives.js",
    "knowledge": ROOT / "app/static/pages/knowledge.js",
}


def test_disclosure_helper_owns_anatomy_and_state_updates() -> None:
    assert "export function renderDisclosureToggle" in UI
    assert "export function setDisclosureState" in UI
    assert 'class="disclosure-toggle__label"' in UI
    assert 'class="disclosure-toggle__chevron"' in UI
    assert 'setAttribute("aria-expanded"' in UI
    assert "data-disclosure-expand-label" in UI
    assert "data-disclosure-collapse-label" in UI


def test_active_pages_render_section_disclosures_through_shared_helper() -> None:
    for page_name, path in ACTIVE_PAGES.items():
        source = path.read_text(encoding="utf-8")
        assert "renderDisclosureToggle" in source, page_name
        assert '../ui/disclosure.js' in source, page_name


def test_component_tokens_and_all_three_variants_are_documented_in_css() -> None:
    for token in (
        "--disclosure-bg",
        "--disclosure-height",
        "--disclosure-min-width",
        "--disclosure-radius",
        "--disclosure-icon-size",
    ):
        assert token in EDITORIAL
    for variant in (
        ".disclosure-toggle--section",
        ".disclosure-toggle--section-compact",
        ".disclosure-toggle--inline",
    ):
        assert variant in EDITORIAL or variant in UI


def test_private_page_toggle_classes_no_longer_own_visual_blocks() -> None:
    forbidden = (
        ".macro-group-toggle {",
        ".monitoring-missing-toggle {",
        ".btc-protection-toggle {",
        ".btc-audit-toggle {",
        'body[data-page="macro-calendar"] .macro-calendar-toggle {',
        'body[data-page="market-events"] .supply-calendar-toggle {',
        'body[data-page="knowledge-base"] .knowledge-section-toggle {',
    )
    combined = f"{STYLES}\n{EDITORIAL}"
    for selector in forbidden:
        assert selector not in combined, selector


def test_disclosure_accessibility_and_motion_contract_is_present() -> None:
    assert '.disclosure-toggle:focus-visible' in EDITORIAL
    assert 'outline: 2px solid var(--accent-strong)' in EDITORIAL
    assert '.disclosure-toggle[aria-expanded="false"]' in EDITORIAL
    assert "rotate(-90deg)" in EDITORIAL
    assert "@media (pointer: coarse)" in EDITORIAL
    assert "@media (prefers-reduced-motion: reduce)" in EDITORIAL


def test_monitoring_missing_detail_has_a_real_toggle_binding() -> None:
    source = ACTIVE_PAGES["monitoring"].read_text(encoding="utf-8")
    assert "function bindMonitoringMissingToggle" in source
    assert 'document.querySelector("[data-missing-toggle]")' in source
    assert "body.hidden = !nextExpanded" in source
    assert "setDisclosureState(button, nextExpanded)" in source
