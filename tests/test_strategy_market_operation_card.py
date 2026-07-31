"""Static guards for §17 / spec 2026-07-31-strategy-market-operation-card-redesign.

Asserts:
  1. .strategy-v2-grid.five uses repeat(3, minmax(0, 1fr)) (fixed 3-col)
     instead of auto-fit minmax.
  2. .strategy-operation-card[data-tone="bull"] / "bear" / "neutral"
     rules each set a color value distinct from the default ink.
  3. .strategy-operation-card-detail ul li::before uses an SVG / pseudo
     element (list-style is overridden, not disc).
  4. .op-chevron has a transform rule for [open] state (rotate 90deg).
  5. .strategy-operation-card-title span becomes pill-like (padding +
     border-radius).
  6. renderMarketOperation.js emits data-tone attribute on <details>
     based on direction.
  7. <small> in summary now contains an <span class="op-chevron"> marker.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "app" / "static" / "styles.css"
RENDER = ROOT / "app" / "static" / "pages" / "strategy" / "renderMarketOperation.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_grid_five_is_fixed_three_cols():
    src = _read(STYLES)
    block = re.search(r"\.strategy-v2-grid\.five\s*\{([^}]+)\}", src, re.S)
    assert block, ".strategy-v2-grid.five block missing"
    body = block.group(1)
    assert "repeat(3, minmax(0, 1fr))" in body, \
        ".strategy-v2-grid.five must be fixed 3-col grid, not auto-fit"
    # Strip /* ... */ comments and re-check for auto-fit (the audit comment
    # mentions the keyword historically).
    code_only = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    assert "auto-fit" not in code_only, \
        ".strategy-v2-grid.five must not use auto-fit (auto-fit causes uneven widths)"


def test_grid_five_responsive_fallback():
    src = _read(STYLES)
    assert "@media (max-width: 960px)" in src and \
        "grid-template-columns: repeat(2, minmax(0, 1fr))" in src, \
        "960px breakpoint must fall back to 2 cols"
    assert "@media (max-width: 560px)" in src, \
        "560px breakpoint must collapse to 1 col"


def test_three_tone_data_attributes_have_color_rules():
    src = _read(STYLES)
    for tone, expected_token in (
        ("bull", "var(--bullish-strong)"),
        ("bear", "var(--bearish-strong)"),
        ("neutral", "var(--muted-strong)"),
    ):
        pattern = re.compile(
            rf"\.strategy-operation-card\[data-tone=\"{tone}\"]\s*\.strategy-operation-card-title\s*strong\s*\{{[^}}]*{re.escape(expected_token)}",
            re.S,
        )
        assert pattern.search(src), \
            f"data-tone={tone} rule missing or uses wrong token (expected {expected_token})"


def test_evidence_bullet_is_pseudo_not_disc():
    src = _read(STYLES)
    # ul must have list-style: none (or list-style-type: none)
    ul_block = re.search(r"\.strategy-operation-card-detail\s+ul\s*\{([^}]+)\}", src, re.S)
    assert ul_block, ".strategy-operation-card-detail ul block missing"
    body = ul_block.group(1)
    assert "list-style" in body, "ul must override list-style"
    # li must have a pseudo-element ::before for the bullet
    li_before = re.search(r"\.strategy-operation-card-detail\s+ul\s+li::before\s*\{([^}]+)\}", src, re.S)
    assert li_before, "ul li::before pseudo-element missing"
    body = li_before.group(1)
    assert "border-radius" in body, "bullet pseudo-element must use border-radius: 50%"
    assert "background:" in body or "background-color:" in body, \
        "bullet pseudo-element must declare background color"


def test_chevron_rotation_rule():
    src = _read(STYLES)
    assert re.search(r"\.op-chevron\s*\{[^}]*border-left", src, re.S), \
        ".op-chevron must use triangle border pattern"
    assert re.search(
        r"\.strategy-operation-card\[open\]\s*\.op-chevron\s*\{[^}]*transform:\s*rotate\(90deg\)",
        src, re.S
    ), ".op-chevron must rotate 90deg when card [open]"


def test_summary_chip_is_pill_shaped():
    src = _read(STYLES)
    span_block = re.search(
        r"\.strategy-operation-card-title\s+span\s*\{([^}]+)\}", src, re.S
    )
    assert span_block, ".strategy-operation-card-title span block missing"
    body = span_block.group(1)
    assert "padding" in body, "confidence span must declare padding"
    assert "border-radius" in body, "confidence span must have border-radius"
    assert "999px" in body or "50%" in body or "9999px" in body, \
        "confidence span must be pill-shaped (border-radius >= 999px)"


def test_render_emits_data_tone_attribute():
    src = _read(RENDER)
    assert re.search(r'data-tone="\$\{tone\}"', src), \
        'renderResolutionOperationCard must emit data-tone="${tone}" attribute on <details>'
    # Also check tone resolution logic
    assert 'direction === "LONG"' in src and 'return "bull"' in src, \
        "tone logic for LONG must map to bull"
    assert 'direction === "SHORT"' in src and 'return "bear"' in src, \
        "tone logic for SHORT must map to bear"


def test_summary_contains_chevron_marker():
    src = _read(RENDER)
    assert re.search(r'<span class="op-chevron"', src), \
        "summary must contain <span class=\"op-chevron\"> marker"
    assert 'op-chevron-label' in src, \
        "summary must contain <span class=\"op-chevron-label\"> wrapper for the affordance text"


def test_detail_body_dashed_dividers():
    src = _read(STYLES)
    p_block = re.search(
        r"\.strategy-operation-card-detail\s+p\s*\{([^}]+)\}", src, re.S
    )
    assert p_block, ".strategy-operation-card-detail p block missing"
    body = p_block.group(1)
    assert "border-bottom" in body and "dashed" in body, \
        "detail body paragraphs must have dashed dividers"


def test_summary_layers_have_visual_separation():
    """Layer 4 (meaning) and affordance must have margin-top: auto on the
    affordance so it pins to the bottom of the summary."""
    src = _read(STYLES)
    affordance_block = re.search(
        r"\.strategy-operation-card\s*>\s*summary\s*>\s*small\s*\{([^}]+)\}", src, re.S
    )
    assert affordance_block, ".strategy-operation-card > summary > small block missing"
    body = affordance_block.group(1)
    assert "margin-top: auto" in body, "affordance must pin to bottom of summary"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))