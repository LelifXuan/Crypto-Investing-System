"""Guards shared dropdown geometry and the clean real-time mark surface."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DROPDOWN = (ROOT / "app" / "static" / "ui" / "dropdown.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_dropdown_popovers_default_to_trigger_width_without_pixel_rounding() -> None:
    assert 'sizeMode: "trigger"' in DROPDOWN
    assert "const requestedWidth = rect.width" in DROPDOWN
    assert 'popover.style.left = `${left}px`' in DROPDOWN
    assert 'popover.style.left = `${Math.round(left)}px`' not in DROPDOWN


def test_dropdown_trigger_and_popover_share_white_surface() -> None:
    assert ".dropdown {\n  background: var(--white);" in EDITORIAL
    assert ".dropdown-popover {" in EDITORIAL
    popover = EDITORIAL[EDITORIAL.index(".dropdown-popover {"):]
    popover = popover[:popover.index("}")]
    assert "background: var(--white)" in popover


def test_realtime_mark_metadata_uses_dividers_not_tinted_cards() -> None:
    assert '.realtime-card .status-grid {' in EDITORIAL
    assert '.realtime-card .mini-card {' in EDITORIAL
    block = EDITORIAL[EDITORIAL.index('body[data-page="market-analysis"] .realtime-card .mini-card {'):]
    block = block[:block.index("}")]
    assert "background: transparent" in block
    assert "border: 0" in block
    assert '.mini-card + .mini-card {' in EDITORIAL
    assert "border-left: 1px solid var(--border-light)" in EDITORIAL
