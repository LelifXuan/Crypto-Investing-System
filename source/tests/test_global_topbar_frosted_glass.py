"""Static guards for the quiet shared application topbar surface."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITORIAL = ROOT / "source/app/static/editorial.css"


def _css() -> str:
    return EDITORIAL.read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    start = css.index(f"{selector} {{")
    return css[start : css.index("}", start) + 1]


def test_shared_topbar_uses_quiet_solid_surface_without_layout_changes() -> None:
    block = _block(_css(), ".app-topbar")

    assert "position: sticky" in block
    assert "top: 0" in block
    assert "min-height: var(--topbar-height)" in block
    assert "background: color-mix(in srgb, var(--surface-elevated) 96%, transparent)" in block
    assert "border-bottom: 1px solid var(--border)" in block
    assert "box-shadow: none" in block
    assert "backdrop-filter: none" in block
    assert "-webkit-backdrop-filter: none" in block


def test_shared_topbar_has_solid_reduced_transparency_fallback() -> None:
    css = _css()
    start = css.index("@media (prefers-reduced-transparency: reduce)")
    end = css.index("@media (prefers-reduced-motion", start)
    fallback = css[start:end]

    assert ".app-topbar" in fallback
    assert "background: var(--surface-elevated)" in fallback
    assert "backdrop-filter: none" in fallback
    assert "-webkit-backdrop-filter: none" in fallback
