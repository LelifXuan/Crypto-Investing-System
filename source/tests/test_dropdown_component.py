"""Static guards for the unified dropdown component."""
import re
from pathlib import Path

import pytest

CSS_FILE = Path("app/static/styles.css")


def _read_css() -> str:
    return CSS_FILE.read_text(encoding="utf-8") if CSS_FILE.exists() else ""


@pytest.mark.parametrize("selector", [".dropdown", ".dropdown-popover", ".dropdown-item"])
def test_dropdown_selectors_exist(selector):
    css = _read_css()
    pattern = re.escape(selector) + r"\s*\{"
    assert re.search(pattern, css), f"missing CSS rule for {selector}"


def test_dropdown_size_variants_have_height():
    css = _read_css()
    for variant in ('[data-dropdown-size="default"]', '[data-dropdown-size="compact"]'):
        idx = css.find(f".dropdown{variant}")
        assert idx >= 0, f"missing .dropdown{variant} selector"
        block_end = css.find("}", idx)
        block = css[idx:block_end]
        assert "height:" in block, f".dropdown{variant} missing height declaration"


def test_dropdown_popover_uses_fixed_and_zindex():
    css = _read_css()
    idx = css.find(".dropdown-popover {")
    assert idx >= 0, "missing .dropdown-popover base rule"
    block_end = css.find("}", idx)
    block = css[idx:block_end]
    assert "position: fixed" in block, ".dropdown-popover must use position:fixed"
    assert re.search(r"z-index:\s*\d{3,}", block), ".dropdown-popover must declare z-index >= 100"


def test_no_new_hex_colors_in_dropdown_rules():
    css = _read_css()
    blocks = re.findall(r"(\.dropdown-[^{]*\{[^}]*\})", css)
    hex_colors = re.compile(r"#[0-9a-fA-F]{3,8}")
    offenders = []
    for b in blocks:
        for m in hex_colors.finditer(b):
            start = max(0, m.start() - 10)
            window = css[start:m.end() + 10]
            if "var(" not in window:
                offenders.append((b.split("{")[0].strip(), m.group(0)))
    assert not offenders, f"dropdown rules introduced new hex colors: {offenders}"


def test_no_backdrop_filter_in_dropdown_rules():
    css = _read_css()
    blocks = re.findall(r"(\.dropdown-[^{]*\{[^}]*\})", css)
    for b in blocks:
        assert "backdrop-filter" not in b, "dropdown rules must not use backdrop-filter"