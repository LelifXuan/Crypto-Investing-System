"""Static guards for the macro-calendar default collapsed state."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app/static/pages/macro_calendar.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")


def test_calendar_defaults_to_collapsed_and_exposes_an_accessible_toggle() -> None:
    assert "let isCalendarCollapsed = true;" in PAGE
    assert 'id: "macro-calendar-toggle"' in PAGE
    assert 'controls: "macro-calendar-body"' in PAGE
    assert "renderDisclosureToggle" in PAGE
    assert 'id="macro-calendar-body"' in PAGE
    assert 'isCalendarCollapsed ? "hidden" : ""' in PAGE


def test_calendar_toggle_updates_the_existing_dom_without_rerendering_page() -> None:
    assert "isCalendarCollapsed = !isCalendarCollapsed;" in PAGE
    assert "body.hidden = isCalendarCollapsed" in PAGE
    assert "setDisclosureState(button, !isCalendarCollapsed)" in PAGE


def test_calendar_hidden_body_overrides_its_grid_display() -> None:
    selector = 'body[data-page="macro-calendar"] .macro-calendar-body[hidden] {'
    start = STYLES.index(selector)
    block = STYLES[start : STYLES.index("}", start)]
    assert "display: none !important" in block
