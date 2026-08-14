"""Static guards for §16.D sticky thead + tooltip Escape.

Asserts:
  1. base `table thead th` carries `position: sticky` (with `top: 0`).
  2. .table-wrap and .btc-table-wrap declare overflow-y: auto and max-height.
  3. core/dom.js exports bindTooltipEscape.
  4. main.js boot() calls bindTooltipEscape(document).
  5. mobile breakpoint strips sticky to avoid horizontal-header collapse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "app" / "static" / "styles.css"
DOM_JS = ROOT / "app" / "static" / "core" / "dom.js"
MAIN_JS = ROOT / "app" / "static" / "main.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_styles_table_thead_th_is_sticky():
    source = _read(STYLES)
    block = re.search(r"table\s+thead\s+th\s*\{([^}]+)\}", source, re.S)
    assert block, "table thead th block missing"
    body = block.group(1)
    assert "position: sticky" in body, "sticky not declared on table thead th"
    assert "top: 0" in body, "top: 0 not declared on sticky thead"


def test_styles_table_wrap_overflow_y_auto():
    source = _read(STYLES)
    block = re.search(r"^\.table-wrap\s*\{([^}]+)\}", source, re.S | re.M)
    assert block, ".table-wrap block missing"
    body = block.group(1)
    assert "overflow-y: auto" in body, ".table-wrap needs overflow-y: auto"
    assert "max-height" in body, ".table-wrap needs a max-height to enable vertical scroll"


def test_styles_btc_table_wrap_overflow_y_auto():
    source = _read(STYLES)
    block = re.search(r"^\.btc-table-wrap\s*\{([^}]+)\}", source, re.S | re.M)
    assert block, ".btc-table-wrap block missing"
    body = block.group(1)
    assert "overflow: auto" in body or "overflow-y: auto" in body, \
        ".btc-table-wrap needs vertical scroll"


def test_styles_mobile_breakpoint_disables_sticky():
    """A common regression: sticky thead forces a 2-line wrap on narrow viewports
    because column headings can't truncate. Strip it under 980px."""
    source = _read(STYLES)
    open_brace = "{"
    close_brace = "}"
    pattern = re.compile(
        r"@media[^{]+\{\s*table\s+thead\s+th\s*\{[^}]*position:\s*static[^}]*\}",
        re.S,
    )
    assert pattern.search(source), \
        "@media (max-width: 980px) override of table thead th position:static is missing"


def test_dom_js_exports_bind_tooltip_escape():
    source = _read(DOM_JS)
    assert re.search(r"export function bindTooltipEscape\b", source), \
        "bindTooltipEscape() not exported from core/dom.js"


def test_main_js_calls_bind_tooltip_escape_in_boot():
    source = _read(MAIN_JS)
    assert "bindTooltipEscape" in source, "bindTooltipEscape not referenced in main.js"
    # Find the boot() function and confirm it calls the helper.
    boot_block = re.search(r"async function boot\b[\s\S]*?^\}", source, re.M | re.S)
    assert boot_block, "boot() function not found"
    assert "bindTooltipEscape(document)" in boot_block.group(0), \
        "boot() must call bindTooltipEscape(document)"


def test_dom_js_marker_present():
    source = _read(DOM_JS)
    assert "§16.D" in source
    assert _read(STYLES).count("§16.D") >= 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
