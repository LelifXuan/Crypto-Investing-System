"""Static guards for §17 dropdown state uniqueness + scope.

Asserts:
  1. .dropdown-item[aria-selected="true"] border-left rule is gone.
  2. .dropdown-item[aria-selected="true"] no longer sets border-left-color.
  3. .dropdown-item.is-active background is distinct from selected.
  4. dropdown.js declares syncSelected, clearHighlight, fitPopover.
  5. dropdown.js close() / destroy() both call clearHighlight.
  6. dropdown.js emits per-option id under makeOptionId().
  7. dropdown.js sets aria-controls / aria-haspopup / aria-expanded.

Audit reference: docs/superpowers/specs/2026-07-31-dropdown-revision-design.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "app" / "static" / "styles.css"
DROPDOWN_JS = ROOT / "app" / "static" / "ui" / "dropdown.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_no_border_left_accent_on_selected_item():
    src = _read(STYLES)
    bad = re.search(
        r"\.dropdown-item\[aria-selected=\"true\"\][^{}]*border-left-color\s*:",
        src,
    )
    assert not bad, "Dropdown selected option must not set border-left-color (causes moon/arc artifact)"


def test_no_border_left_rule_on_item():
    src = _read(STYLES)
    bad = re.search(r"\.dropdown-item\s*\{[^}]*border-left\s*:", src, re.S)
    assert not bad, ".dropdown-item must not declare border-left (strip clips under radius)"


def test_active_background_distinct_from_selected():
    src = _read(STYLES)
    # Find the .dropdown-item.is-active rule and ensure its background does
    # not match the selected gradient (which would defeat keyboard visual cue).
    is_active_block = re.search(r"\.dropdown-item\.is-active\s*\{([^}]+)\}", src, re.S)
    selected_block = re.search(
        r"\.dropdown-item\[aria-selected=\"true\"\][^{}]*\{([^}]+)\}", src, re.S
    )
    assert is_active_block and selected_block
    active_bg = re.search(r"background\s*:[^;]+;", is_active_block.group(1))
    selected_bg = re.findall(r"background\s*:[^;]+;", selected_block.group(1))
    assert active_bg, "is-active rule must declare a background"
    assert active_bg.group(0) not in selected_bg, (
        "is-active background must visually differ from selected gradient"
    )


def test_dropdown_js_defines_sync_selected():
    src = _read(DROPDOWN_JS)
    assert re.search(r"function\s+syncSelected\s*\(", src), \
        "syncSelected() function missing in dropdown.js"


def test_dropdown_js_defines_clear_highlight():
    src = _read(DROPDOWN_JS)
    assert re.search(r"function\s+clearHighlight\s*\(", src), \
        "clearHighlight() function missing in dropdown.js"


def test_dropdown_js_defines_fit_popover():
    src = _read(DROPDOWN_JS)
    assert re.search(r"function\s+fitPopover\s*\(", src), \
        "fitPopover() function missing in dropdown.js"


def test_close_calls_clear_highlight():
    src = _read(DROPDOWN_JS)
    # locate function close() {...} and ensure the body contains clearHighlight(popover, root)
    close_block = re.search(r"function\s+close\s*\([^)]*\)\s*\{([^}]+)\}", src, re.S)
    assert close_block, "close() body not found"
    assert "clearHighlight" in close_block.group(1), \
        "close() must call clearHighlight to satisfy INV-2"


def test_destroy_removes_active_class_and_aria():
    src = _read(DROPDOWN_JS)
    destroy_block = re.search(
        r"destroy\s*\([^)]*\)\s*\{([\s\S]+?)(?=\n\s*\}\s*,|\n\s*\};\s*return)",
        src,
    )
    assert destroy_block, "destroy() body not found"
    body = destroy_block.group(1)
    assert "removeAttribute" in body and "aria-selected" in body, \
        "destroy() must strip aria-selected"
    assert "ACTIVE_CLASS" in body or "is-active" in body, \
        "destroy() must strip keyboard-highlight class"


def test_make_option_id_emitted_in_build_item():
    src = _read(DROPDOWN_JS)
    # ensure buildItem receives `root` and `index` and stamps el.id
    assert re.search(r"function\s+buildItem\s*\(\s*item\s*,\s*value\s*,\s*root\s*,\s*index", src), \
        "buildItem must accept root + index for stable per-option ids"
    assert re.search(r"btn\.id\s*=\s*makeOptionId", src), \
        "buildItem must stamp el.id = makeOptionId(...)"


def test_aria_controls_and_haspopup_set():
    src = _read(DROPDOWN_JS)
    assert 'setAttribute("aria-haspopup"' in src, "aria-haspopup must be set on Trigger root"
    assert 'setAttribute("aria-controls"' in src, "aria-controls must be set on Trigger root"
    assert 'setAttribute("aria-expanded"' in src, "aria-expanded must be set on Trigger root"


def test_dev_only_multi_selected_warning():
    src = _read(DROPDOWN_JS)
    assert 'console.warn' in src and 'multiple selected options' in src, \
        "INV-1 dev-only console.warn missing — should fire when >1 aria-selected items present"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
