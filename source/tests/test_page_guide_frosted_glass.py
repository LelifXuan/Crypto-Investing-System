"""Static guard for the BTC page-guide panel / tooltip frosted-glass styling.

Mirrors docs/design-guidelines.md §14 (glassmorphism rule) and the
taste-skill §2.B honest-implementation note: a frosted surface must
always ship with a solid `prefers-reduced-transparency: reduce` fallback
so users on systems that disable translucency still read the panel
cleanly.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EDITORIAL = REPO / "app" / "static" / "editorial.css"
STYLES = REPO / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frosted_block(css: str) -> str:
    """Locate the consolidated frosted-glass block (selectors .page-guide-panel
    + .tooltip-bubble with backdrop-filter blur) AND its
    prefers-reduced-transparency fallback. Distinct from the
    prefers-reduced-motion sub-block at the very end of the file."""
    anchor = ".page-guide-panel,\n.tooltip-bubble,\n.strategy-detail-panel {"
    idx = css.index(anchor)
    end = css.index("@media (prefers-reduced-motion", idx)
    return css[idx:end]


def test_glass_tokens_are_declared_in_root() -> None:
    css = _read(STYLES)
    for token in (
        "--glass-bg",
        "--glass-bg-deep",
        "--glass-tint",
        "--glass-border",
        "--glass-border-outer",
        "--glass-highlight",
        "--glass-blur",
        "--glass-blur-deep",
    ):
        assert f"{token}:" in css, f"missing glass token {token} in :root"


def test_page_guide_tooltip_and_strategy_drawer_share_frosted_block() -> None:
    css = _read(EDITORIAL)
    block = _frosted_block(css)
    assert "backdrop-filter: blur(var(--glass-blur))" in block
    assert "background: var(--glass-bg)" in block
    assert ".strategy-detail-panel" in block
    # Glass is intentionally neutral (no saturate bump, no color tint) so the
    # underlying page chroma bleeds through verbatim. See docs/design-guidelines.md
    # §14 and taste-skill §2.B Apple Liquid Glass note.
    assert "saturate(" not in block, "frosted glass must NOT tint — page chroma bleeds through"


def test_glass_tokens_are_neutral_not_tinted() -> None:
    css = _read(STYLES)
    # --glass-bg and --glass-bg-deep must be neutral white-with-alpha, not
    # a tinted blue/cream color that would shift the underlying hue.
    assert "--glass-bg: rgba(255, 255, 255," in css
    assert "--glass-bg-deep: rgba(255, 255, 255," in css
    # --glass-tint (inner section) is also neutral white.
    assert "--glass-tint: rgba(255, 255, 255," in css


def test_inner_section_cards_also_use_frosted_glass() -> None:
    css = _read(EDITORIAL)
    block = _frosted_block(css)
    assert ".page-guide-panel .knowledge-guide-body section" in block
    # Inner sections deliberately reuse --glass-tint (near-transparent) without
    # stacking another backdrop-filter, so the parent panel's blur carries
    # through. This avoids frosted-on-frosted (taste-skill §15).
    assert "background: var(--glass-tint)" in block
    inner_section = block.split(
        ".page-guide-panel .knowledge-guide-body section"
    )[1].split("}")[0]
    assert "backdrop-filter:" not in inner_section


def test_reduced_transparency_fallback_uses_solid_surface() -> None:
    css = _read(EDITORIAL)
    fallback_start = css.index("@media (prefers-reduced-transparency: reduce)")
    fallback_end = css.index("@media", fallback_start + 1)
    fallback = css[fallback_start:fallback_end]
    assert "backdrop-filter: none" in fallback
    assert "-webkit-backdrop-filter: none" in fallback
    assert "background: var(--surface-elevated)" in fallback


def test_legacy_backdrop_filter_none_override_is_gone() -> None:
    css = _read(EDITORIAL)
    # The previous override inside the .page-guide-panel block (formerly
    # at line ~1891) explicitly disabled the blur, silently cancelling the
    # frosted surface defined later in the file. Guard against re-adding it.
    block_start = css.index(".page-guide-panel {")
    block_end = css.index("}", block_start)
    block = css[block_start:block_end]
    assert "backdrop-filter: none" not in block
    assert "-webkit-backdrop-filter: none" not in block


def test_panel_is_widened_to_at_least_500px() -> None:
    """2026-08-18: panel widened from 410 to 615px (1.5x) so it occupies less
    vertical space — wider columns wrap text on fewer lines. Guard against
    silent narrowing back to the cramped mobile-portrait default."""
    css = _read(EDITORIAL)
    # Anchor on `width: min(` to skip the sidebar-collapsed override which
    # is the first .page-guide-panel { block in the file.
    anchor = ".page-guide-panel {"
    idx = 0
    while True:
        block_start = css.index(anchor, idx)
        block_end = css.index("}", block_start)
        block = css[block_start:block_end]
        if "width: min(" in block:
            break
        idx = block_end + 1
    assert "min(500px" in block or "min(615px" in block, (
        "page-guide-panel must stay at >= 500px wide; the original 410px "
        "made the content wrap onto too many vertical lines"
    )


def test_layered_highlight_border_uses_inset_shadow_not_extra_div() -> None:
    css = _read(EDITORIAL)
    block = _frosted_block(css)
    # taste-skill §2.B: layered borders + highlight overlay. We use the
    # --glass-shadow token (a 4-layer composite: outer drop, soft halo,
    # top highlight, bottom reflection) instead of stacking extra DOM
    # nodes. The token must therefore be declared in :root.
    assert "box-shadow: var(--glass-shadow)" in block


def test_frosted_block_sits_after_dropdown_block() -> None:
    """Make sure the frosted rule is *after* the existing .dropdown-popover
    block so the same-specificity cascade applies frosted tokens to the panel
    without leaking blur into the dropdown (which is asserted opaque in
    test_dropdown_component.py::test_no_backdrop_filter_in_dropdown_rules).
    """
    css = _read(EDITORIAL)
    dropdown_idx = css.rfind(".dropdown-popover {")
    frosted_idx = css.index(
        ".page-guide-panel,\n.tooltip-bubble,\n.strategy-detail-panel {"
    )
    assert dropdown_idx != -1, "expected existing .dropdown-popover block"
    assert frosted_idx > dropdown_idx, (
        "frosted block must come after .dropdown-popover to win the cascade "
        "without affecting the dropdown"
    )


def test_dropdown_remains_opaque() -> None:
    """Regression guard: the dropdown menu is explicitly NOT frosted
    (see test_dropdown_component.py::test_no_backdrop_filter_in_dropdown_rules).
    """
    css = _read(EDITORIAL)
    frosted_block = _frosted_block(css)
    assert ".dropdown-popover" not in frosted_block


def test_strategy_drawer_keeps_glass_visible_through_its_layers() -> None:
    css = _read(EDITORIAL)
    block = _frosted_block(css)

    assert ".strategy-detail-overlay" in block
    assert "background: rgba(31, 42, 58, 0.2)" in block
    assert "border-radius: 18px 0 0 18px" in block
    assert ".strategy-detail-panel .strategy-detail-header" in block
    assert ".strategy-detail-panel .strategy-detail-body > .card" in block
    assert block.count("background: var(--glass-bg-deep)") >= 2


def test_strategy_drawer_has_solid_reduced_transparency_fallback() -> None:
    css = _read(EDITORIAL)
    block = _frosted_block(css)
    fallback = block[block.index("@media (prefers-reduced-transparency: reduce)"):]

    assert ".strategy-detail-panel" in fallback
    assert ".strategy-detail-panel .strategy-detail-header" in fallback
    assert ".strategy-detail-panel .strategy-detail-body > .card" in fallback
    assert "background: var(--surface-elevated)" in fallback
