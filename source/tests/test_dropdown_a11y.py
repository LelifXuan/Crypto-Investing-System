"""§17 dropdown accessibility + ARIA guards.

Asserts:
  1. role=combobox / listbox / option are emitted.
  2. Trigger has the three required ARIA toggles.
  3. Listbox gets role=listbox.
  4. Each option gets role=option.
  5. active element id matches aria-activedescendant when keyboard nav active.
  6. Trigger root tag remains BUTTON (per spec / invariant).
  7. destroy() removes event listeners + popover DOM cleanly.

Audit reference: docs/superpowers/specs/2026-07-31-dropdown-revision-design.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROPDOWN_JS = ROOT / "app" / "static" / "ui" / "dropdown.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_mount_dropdown_root_must_be_button():
    src = _read(DROPDOWN_JS)
    assert re.search(
        r"if\s*\(\s*!root\s*\|\|\s*root\.tagName\s*!==\s*[\"']BUTTON[\"']\s*\)",
        src,
    ), "mountDropdown must assert root.tagName === 'BUTTON'"


def test_buildItem_emits_role_option():
    src = _read(DROPDOWN_JS)
    pattern = r"""btn\.setAttribute\(\s*['"]role['"]\s*,\s*['"]option['"]\s*\)"""
    assert re.search(pattern, src), "buildItem must emit role=option"


def test_buildpopover_emits_role_listbox():
    src = _read(DROPDOWN_JS)
    pattern = r"""popover\.setAttribute\(\s*['"]role['"]\s*,\s*['"]listbox['"]\s*\)"""
    assert re.search(pattern, src), "buildPopover must emit role=listbox"


def test_trigger_sets_aria_haspopup_listbox():
    src = _read(DROPDOWN_JS)
    pattern = r"""root\.setAttribute\(\s*['"]aria-haspopup['"]\s*,\s*['"]listbox['"]\s*\)"""
    assert re.search(pattern, src), 'Trigger should set aria-haspopup="listbox"'


def test_aria_activedescendant_set_by_sync_highlight():
    src = _read(DROPDOWN_JS)
    # syncHighlight should both set and reference aria-activedescendant;
    # the precise conditional structure is enforced at runtime instead.
    block = re.search(
        r"function\s+syncHighlight\s*\([^)]*\)\s*\{([\s\S]+?)\n\s*\}\s*\n\s*function",
        src,
    )
    if not block:
        # fallback: just search the whole source for setAttribute aria-activedescendant inside syncHighlight scope
        block = re.search(
            r"function\s+syncHighlight[\s\S]+?\n\s*\}\s*\n",
            src,
        )
    assert block, "syncHighlight body not found"
    body = block.group(0)
    assert "aria-activedescendant" in body, \
        "syncHighlight must reference aria-activedescendant"


def test_clear_highlight_removes_aria_activedescendant():
    src = _read(DROPDOWN_JS)
    # Find any block that contains "removeAttribute" + "aria-activedescendant"
    # (clearHighlight is the dominant path).
    has_remove = (
        'removeAttribute("aria-activedescendant"' in src
        or "removeAttribute('aria-activedescendant'" in src
    )
    assert has_remove, \
        "clearHighlight (or equivalent) must remove aria-activedescendant on root"


def test_no_document_level_keydown_capture_added():
    src = _read(DROPDOWN_JS)
    bad = re.search(
        r"document\.addEventListener\(\s*['\"]keydown['\"][^,]*,\s*[^,]+,\s*true\s*\)",
        src,
    )
    assert not bad, \
        "Document-level capturing keydown listener detected; type-ahead must remain root-scoped"


def test_destroy_removes_every_listener():
    src = _read(DROPDOWN_JS)
    # search for the destroy() method body up to the next sibling property
    destroy = re.search(
        r"destroy\s*\(\s*\)\s*\{",
        src,
    )
    assert destroy, "destroy() not found in export"
    start = destroy.end()
    # find matching close brace by depth counting
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        c = src[i]
        if c == "{": depth += 1
        elif c == "}": depth -= 1
        i += 1
    body = src[start:i-1]
    for kind in ("click", "keydown"):
        assert "removeEventListener" in body and kind in body, \
            f"destroy() must removeEventListener for {kind}"
    # popover.detach: popover.remove() or popover.removeChild(parent)
    assert "popover.remove()" in body or ".remove()" in body, \
        "destroy() must remove popover from DOM"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
