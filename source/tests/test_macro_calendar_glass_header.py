"""Static guards for the macro-calendar frosted sticky release header."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app/static/pages/macro_calendar.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")


def test_release_table_has_a_stable_scoped_container() -> None:
    assert PAGE.count('id="macro-calendar-detail"') == 2


def test_release_header_uses_frosted_glass_instead_of_beige_gradient() -> None:
    selector = 'body[data-page="macro-calendar"] #macro-calendar-detail thead {'
    start = STYLES.index(selector)
    block = STYLES[start : STYLES.index("}", start)]

    assert "rgba(255, 255, 255, 0.74)" in block
    assert "backdrop-filter: blur(18px) saturate(1.2)" in block
    assert "248, 244, 236" not in block


def test_release_rows_fade_before_crossing_the_sticky_header() -> None:
    assert '#macro-calendar-detail .table-wrap::before {' in STYLES
    assert "position: sticky" in STYLES
    assert "height: 16px" in STYLES
    assert "rgba(255, 255, 255, 0.98)" in STYLES
    assert "#macro-calendar-detail thead th" in STYLES
