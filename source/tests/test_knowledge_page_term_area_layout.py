"""Static guard for the knowledge-base PAGE-GUIDES term-card area.

Two regressions addressed on 2026-08-18:

1. The middle content column was capped at `var(--reading-measure) = 800px`
   (designed for paragraph line-length) which on the 2560-wide dev viewport
   pinned cards at ~273px each — visibly cramped against the 240px left
   rail and 300px right rail. Loosened to 1fr so the column can grow.

2. `.knowledge-guide-card` used `rgba(255,255,255,0.92)` + `rgba(247,251,255,0.98)`
   on a warmer page background, producing a disconnected tile. It now uses
   the same cool-neutral surface gradient as every other card on the page.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "app" / "static" / "editorial.css"
STYLES = ROOT / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_knowledge_workspace_middle_column_is_not_reading_measure_capped() -> None:
    css = _read(EDITORIAL)
    selector = "body[data-page=\"knowledge-base\"] .knowledge-workspace {"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    # Must not retain the old 560px/reading-measure cap; 1fr / minmax with
    # a much looser floor (≥ 720px) is the new shape.
    assert "minmax(560px, var(--reading-measure))" not in block, (
        "knowledge-workspace middle column still capped at reading-measure "
        "(560px on wide viewports); use minmax(720px, 1fr) or wider"
    )
    assert "minmax(720px, 1fr)" in block, (
        "knowledge-workspace middle column must use minmax(720px, 1fr) so "
        "term cards can breathe on 2560x1600 viewport"
    )


def test_knowledge_content_column_is_not_reading_measure_capped() -> None:
    css = _read(EDITORIAL)
    selector = "body[data-page=\"knowledge-base\"] .knowledge-content-column {"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    # The .knowledge-content-column is the inner wrapper inside the middle
    # grid track. It was also clamped at reading-measure, which cascaded
    # into narrow cards.
    assert "max-width: var(--reading-measure)" not in block, (
        "knowledge-content-column still max-width: var(--reading-measure); "
        "this was designed for paragraph line-length, not card grids"
    )
    assert "max-width: none" in block, (
        "knowledge-content-column must drop the reading-measure cap using a "
        "valid max-width value so the card grid can grow with its grid track"
    )
    assert "max-width: 1fr" not in block, (
        "1fr is a grid track unit, not a valid max-width value"
    )


def test_knowledge_guide_card_uses_shared_neutral_surface() -> None:
    css = _read(STYLES)
    selector = ".knowledge-guide-card {"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    # Old cool-blue backgrounds must be gone
    assert "rgba(255, 255, 255, 0.92)" not in block, (
        "knowledge-guide-card outer background was a cool blue-tinted white "
        "that clashed with the shared page surface (see design guidelines §9)"
    )


def test_knowledge_guide_card_is_open_uses_shared_neutral_surface() -> None:
    css = _read(STYLES)
    selector = ".knowledge-guide-card.is-open {"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    block = css[idx:block_end]
    assert "rgba(247, 251, 255, 0.98)" not in block, (
        "knowledge-guide-card.is-open still uses the cool blue "
        "rgba(247,251,255,0.98) — should be the same neutral gradient "
        "as the closed state, with only a slight alpha bump for the open "
        "hint instead of a color swap"
    )
