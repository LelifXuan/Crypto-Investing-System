"""Static guards for explicit and accessible month navigation controls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "macro_calendar.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_month_navigation_uses_svg_and_visible_labels() -> None:
    assert 'class="calendar-month-button"' in PAGE
    assert 'aria-label="查看上个月"' in PAGE
    assert 'aria-label="查看下个月"' in PAGE
    assert '<span>上个月</span>' in PAGE
    assert '<span>下个月</span>' in PAGE
    assert '>←</button>' not in PAGE
    assert '>→</button>' not in PAGE


def test_month_navigation_has_secondary_button_styling() -> None:
    assert ".calendar-head .calendar-month-button" in STYLES
    assert "stroke: currentColor" in STYLES
    assert "background: var(--surface-elevated)" in STYLES
    assert ".calendar-head .calendar-month-button:focus-visible" in STYLES


def test_month_navigation_is_excluded_from_global_primary_button_fill() -> None:
    editorial = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
    assert ":not(.calendar-month-button)" in editorial
