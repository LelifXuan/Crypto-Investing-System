"""Static guard for macro-calendar event table alignment.

The `<table>` rendered by `renderCalendarTable()` in
`app/static/pages/macro_calendar.js` has no class. Its `<th>` headers
(事件 / 时间 / 实际 / 预期 / 前值 / 差值 / 状态) and per-row `<td>`
cells live inside `<div class="table-wrap">`, which sits inside
`<section id="macro-calendar-detail">`.

2026-08-18: the table previously inherited browser-default
`text-align: start` (LTR = left), which left the `事件` column
visually inconsistent with the short numeric columns. Style now
explicitly centers every cell; the first column (事件 title) stays
left-aligned because its body is a stacked `<strong>` + `<small>`
block that benefits from anchoring to the leading edge.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app" / "static" / "pages" / "macro_calendar.js"
EDITORIAL = ROOT / "app" / "static" / "editorial.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_macro_calendar_table_headers_are_present() -> None:
    source = _read(PAGE)
    for label in ("事件", "时间", "实际", "预期", "前值", "差值", "状态"):
        assert f"<th>{label}</th>" in source, (
            f"macro-calendar event table missing header column {label!r}"
        )


def test_macro_calendar_headers_are_center_aligned() -> None:
    css = _read(EDITORIAL)
    # Locate the table-wrap th block under #macro-calendar-detail
    selector = "body[data-page=\"macro-calendar\"] #macro-calendar-detail .table-wrap th"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    assert "text-align: center" in block, (
        "macro-calendar table headers must be center-aligned "
        "(see docs/design-guidelines.md §7 alignment rules)"
    )


def test_macro_calendar_cells_are_center_aligned() -> None:
    css = _read(EDITORIAL)
    selector = "body[data-page=\"macro-calendar\"] #macro-calendar-detail .table-wrap td"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    assert "text-align: center" in block, (
        "macro-calendar event cells must be center-aligned for numeric / chip "
        "columns to read consistently with their centered header"
    )


def test_macro_calendar_first_column_stays_left_aligned() -> None:
    # The 事件 column contains a stacked `<strong>` title + `<small>` key.
    # Anchoring that block to the leading edge avoids orphaned title text.
    # Without this override the rule above would push it to the center.
    css = _read(EDITORIAL)
    selector = "body[data-page=\"macro-calendar\"] #macro-calendar-detail .table-wrap td:first-child"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    assert "text-align: left" in block, (
        "macro-calendar first cell must override center alignment "
        "and stay left-aligned for the stacked title block"
    )