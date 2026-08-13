"""Guards the shared table hover tone and vertical row alignment."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_shared_table_rows_use_brand_hover_and_middle_alignment() -> None:
    assert ".table-wrap :is(th, td)" in EDITORIAL
    assert "vertical-align: middle" in EDITORIAL
    hover = EDITORIAL[EDITORIAL.index(".table-wrap tbody tr:hover > td"):]
    assert "background: var(--accent-ghost)" in hover


def test_macro_release_ledger_centres_rows_vertically() -> None:
    selector = 'body[data-page="macro-calendar"] #macro-calendar-detail .table-wrap :is(th, td)'
    assert selector in EDITORIAL
    block = EDITORIAL[EDITORIAL.index(selector):]
    assert "height: 60px" in block
    assert "vertical-align: middle" in block
