"""Static smoke checks for §16.B mountChip / mountButton.

We can't import ES modules with vanilla pytest, so we re-implement the
contract expectations here as plain string assertions against the JS source.
If the API shape drifts, this test fires *before* any caller churns.

Audit reference: docs/UI_UX_AUDIT_2026-07-31.md §16.B
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOM_JS = ROOT / "app" / "static" / "core" / "dom.js"
STYLES = ROOT / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_dom_js_exports_mount_chip():
    source = _read(DOM_JS)
    m = re.search(r"export function mountChip\b", source)
    assert m, "mountChip() not exported from core/dom.js"


def test_dom_js_exports_mount_button():
    source = _read(DOM_JS)
    m = re.search(r"export function mountButton\b", source)
    assert m, "mountButton() not exported from core/dom.js"


def test_mount_chip_supports_eight_tones():
    source = _read(DOM_JS)
    # The CHIP_TONE_CLASS map must list all 8 documented tones.
    block = re.search(r"const CHIP_TONE_CLASS\s*=\s*\{([^}]+)\}", source, re.S)
    assert block, "CHIP_TONE_CLASS not defined"
    body = block.group(1)
    for tone in ("bull", "bear", "neutral", "warning", "danger", "info", "success", "event"):
        assert re.search(rf"^\s*{tone}\s*:", body, re.M), f"tone {tone!r} missing from CHIP_TONE_CLASS"


def test_mount_chip_supports_three_variants():
    source = _read(DOM_JS)
    block = re.search(r"const CHIP_VARIANT_CLASS\s*=\s*\{([^}]+)\}", source, re.S)
    assert block, "CHIP_VARIANT_CLASS not defined"
    body = block.group(1)
    for variant in ("solid", "soft", "outline"):
        assert re.search(rf"^\s*{variant}\s*:", body, re.M), f"variant {variant!r} missing"


def test_mount_button_supports_five_variants():
    source = _read(DOM_JS)
    block = re.search(r"const BUTTON_VARIANT_CLASS\s*=\s*\{([^}]+)\}", source, re.S)
    assert block, "BUTTON_VARIANT_CLASS not defined"
    body = block.group(1)
    for variant in ("primary", "secondary", "ghost", "danger", "tab"):
        assert re.search(rf"^\s*{variant}\s*:", body, re.M), f"button variant {variant!r} missing"


def test_mount_button_escapes_text_and_attrs():
    source = _read(DOM_JS)
    assert "escapeHtml(text" in source or "escapeHtml(text ||" in source or "escapeHtml(text || \"\")" in source, \
        "mountButton must escape text via escapeHtml"
    assert "escapeHtml(k)" in source and "escapeHtml(String(v))" in source, \
        "mountButton must escape user-provided attribute keys + values"


def test_styles_define_chip_tone_classes():
    source = _read(STYLES)
    for tone in ("chip-bull", "chip-bear", "chip-neutral", "chip-warning",
                 "chip-danger", "chip-info", "chip-success", "chip-event"):
        assert f".{tone}" in source, f"missing .{tone} in styles.css"


def test_styles_define_chip_variant_classes():
    source = _read(STYLES)
    for variant in ("chip-solid", "chip-soft", "chip-outline"):
        assert f".{variant}" in source, f"missing .{variant} in styles.css"


def test_styles_define_button_classes():
    source = _read(STYLES)
    for variant in ("btn-primary", "btn-secondary", "btn-ghost", "btn-danger", "btn-tab"):
        assert f".{variant}" in source, f"missing .{variant} in styles.css"
    for size in ("btn-sm", "btn-md", "btn-lg"):
        assert f".{size}" in source, f"missing .{size} in styles.css"


def test_styles_chip_block_carries_audit_marker():
    """Adds a sanity check that the §16.B block was added intentionally and
    is not silently lost in a future re-flow."""
    source = _read(STYLES)
    assert "§16.B" in source, "§16.B marker missing in styles.css"

    source_dom = _read(DOM_JS)
    assert "§16.B" in source_dom, "§16.B marker missing in core/dom.js"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
