"""Static guards for the responsive structure chart (ui-audit 2026-09-04 P1#3).

Audit finding: the SVG used a fixed 1040x520 viewBox; on a 390px phone the
whole graphic scaled to 0.275x, leaving axis labels at ~3.3px screen size
(guideline §7.9 chart readability). The fix renders the SVG at the panel's
inner content width and adapts axis density below 640px.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")


def test_svg_size_comes_from_container_inner_width() -> None:
    assert "const width = 1040" not in STRUCTURE
    assert "containerWidth" in STRUCTURE
    assert "clientWidth" in STRUCTURE
    assert "paddingLeft" in STRUCTURE
    # width floor allows narrow phones to render 1:1 instead of shrinking
    assert "Math.max(\n    280," in STRUCTURE


def test_compact_axis_density_below_640px() -> None:
    assert "compactAxis" in STRUCTURE
    assert "width < 640" in STRUCTURE
    assert "yTickCount = compactAxis ? 3 : 5" in STRUCTURE
    assert "compactAxis ? 3 : 6" in STRUCTURE
    assert "is-compact" in STRUCTURE


def test_post_layout_recalibration_re_renders_once() -> None:
    # First render can measure the loading shell; the next frame re-renders
    # when the real inner width diverges.
    assert "requestAnimationFrame(() => {" in STRUCTURE
    assert "Math.abs(inner - rendered) > 1" in STRUCTURE


def test_css_no_longer_forces_svg_width_or_fixed_height() -> None:
    idx = STYLES.index(".structure-chart-svg {")
    block = STYLES[idx:STYLES.index("}", idx)]
    import re
    width_decls = [ln.strip() for ln in block.splitlines() if re.match(r"^\s*width:", ln)]
    assert not width_decls, f"CSS width must not override inline render size: {width_decls}"
    # legacy fixed-size duplicates removed
    assert "height: clamp(360px, 45vh, 520px)" not in STYLES
    assert "min-height: 520px" not in STYLES
    # editorial override no longer clamps the render height
    assert "clamp(320px, 36dvh, 520px)" not in EDITORIAL
