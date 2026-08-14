"""Static smoke checks for §16.C chart theme token readback.

Asserts that the 17 chart-only tokens declared in :root are reachable from
the `app/static/ui/charts.js` THEME read path. The audit specifies the
fallback dict must remain so SSR / unit-test bootstrap can still produce
non-empty colors.

Audit reference: docs/UI_UX_AUDIT_2026-07-31.md §16.C
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARTS_JS = ROOT / "app" / "static" / "ui" / "charts.js"
STYLES = ROOT / "app" / "static" / "styles.css"

EXPECTED_TOKEN_KEYS = {
    "legend":         "--chart-legend",
    "tooltipBg":      "--chart-tooltip-bg",
    "tooltipBorder":  "--chart-tooltip-border",
    "tooltipFg1":     "--chart-tooltip-fg-1",
    "tooltipFg2":     "--chart-tooltip-fg-2",
    "axis":           "--chart-axis",
    "gridX":          "--chart-grid-x",
    "gridY":          "--chart-grid-y",
    "referenceLine":  "--chart-reference-line",
    "referenceLabel": "--chart-reference-label",
    "expiryLine":     "--chart-expiry-line",
    "expiryLabel":    "--chart-expiry-label",
    "dotPutWall":     "--chart-dot-put-wall",
    "dotMaxPain":     "--chart-dot-max-pain",
    "dotCallWall":    "--chart-dot-call-wall",
    "dotStroke":      "--chart-dot-stroke",
    "upStroke":       "--chart-up-stroke",
    "downStroke":     "--chart-down-stroke",
    "upFill":         "--chart-up-fill",
    "downFill":       "--chart-down-fill",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_styles_declares_each_chart_token():
    source = _read(STYLES)
    root_match = re.search(r":root\s*\{", source)
    assert root_match, ":root block missing"
    start = root_match.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    root_block = source[start : i - 1]
    missing: list[str] = []
    for cssvar in EXPECTED_TOKEN_KEYS.values():
        pattern = re.compile(rf"{re.escape(cssvar)}\s*:")
        if not pattern.search(root_block):
            missing.append(cssvar)
    assert not missing, f":root missing chart tokens: {missing}"


def test_charts_declares_THEME_with_all_keys():
    source = _read(CHARTS_JS)
    assert "CHART_THEME_FALLBACK" in source, "CHART_THEME_FALLBACK missing"
    fallback_block = re.search(
        r"const\s+CHART_THEME_FALLBACK\s*=\s*Object\.freeze\(\{(.+?)\}\);",
        source, re.S,
    )
    assert fallback_block, "CHART_THEME_FALLBACK not declared as Object.freeze"
    body = fallback_block.group(1)
    for key in EXPECTED_TOKEN_KEYS:
        if not re.search(rf"^\s*{key}\s*:", body, re.M):
            raise AssertionError(f"FALLBACK missing key {key!r}")


def test_charts_reads_each_css_var():
    source = _read(CHARTS_JS)
    for cssvar in EXPECTED_TOKEN_KEYS.values():
        assert cssvar in source, f"charts.js does not reference {cssvar}"


def test_no_consumer_side_hardcoded_palette_outside_fallback():
    """Lines 12-32 of charts.js hold the fallback dict. After §16.C, all
    site-level color references must use CHART_THEME.<key>. We assert no
    bare chart palette literal appears in 'release' code (lines 33+)."""
    source = _read(CHARTS_JS)
    # fallback section
    fallback_start = source.find("const CHART_THEME_FALLBACK = Object.freeze({")
    fallback_end = source.find("});", fallback_start)
    assert fallback_start != -1 and fallback_end != -1
    head = source[:fallback_start]
    tail = source[fallback_end:]
    rest = head + tail
    palette_fragments = [
        '"#4b5961"', '"#f8fafc"', '"#e2e8f0"', '"#627078"',
        '"rgba(21, 35, 42, 0.92)"', '"rgba(23, 34, 39, 0.042)"',
        '"rgba(23, 34, 39, 0.05)"', '"rgba(83, 99, 108, 0.72)"',
        '"#53636c"', '"rgba(83, 99, 108, 0.45)"', '"rgba(48, 84, 130, 0.85)"',
        '"#c2725a"', '"#5a6a7c"', '"#8eb098"',
        'dataset.upStrokeColor || "#16a34a"',
        'dataset.downStrokeColor || "#dc2626"',
        'dataset.upColor || "rgba(124,155,138,0.32)"',
        'dataset.downColor || "rgba(194,114,90,0.30)"',
    ]
    leaked: list[str] = []
    for frag in palette_fragments:
        if frag in rest:
            leaked.append(frag)
    assert not leaked, f"chart palette literal leaked past fallback block: {leaked}"


def test_charts_module_audit_marker():
    source = _read(CHARTS_JS)
    assert "§16.C" in source, "§16.C marker missing in charts.js"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
