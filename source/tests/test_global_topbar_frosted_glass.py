"""Static guards for the shared application topbar glass surface."""

from pathlib import Path

EDITORIAL = Path("app/static/editorial.css")


def _css() -> str:
    return EDITORIAL.read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    start = css.index(f"{selector} {{")
    return css[start:css.index("}", start) + 1]


def test_shared_topbar_uses_existing_glass_tokens_without_layout_changes() -> None:
    block = _block(_css(), ".app-topbar")

    assert "position: sticky" in block
    assert "top: 0" in block
    assert "min-height: var(--topbar-height)" in block
    assert "background: var(--glass-bg-deep)" in block
    assert "border-bottom: 1px solid var(--glass-border-outer)" in block
    assert "backdrop-filter: blur(var(--glass-blur))" in block
    assert "-webkit-backdrop-filter: blur(var(--glass-blur))" in block
    assert "inset 0 -1px 0 var(--glass-edge)" in block


def test_shared_topbar_has_solid_reduced_transparency_fallback() -> None:
    css = _css()
    start = css.index("@media (prefers-reduced-transparency: reduce)")
    end = css.index("@media (prefers-reduced-motion", start)
    fallback = css[start:end]

    assert ".app-topbar" in fallback
    assert "background: var(--surface-elevated)" in fallback
    assert "backdrop-filter: none" in fallback
    assert "-webkit-backdrop-filter: none" in fallback
