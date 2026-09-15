"""Static guard: term-detail `.knowledge-body` must NOT use lavender / purple.

Background: the shared muted surface and accent color must not turn opened
term content into a purple tile. Combined with the
previous rule

    body[data-page="knowledge-base"] .knowledge-body {
      background: var(--surface-muted);
      border-left: 3px solid var(--accent);
    }

this produced a tinted slab with a purple left-stripe on every opened term
card. The body now uses the shared elevated neutral plus a neutral border.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "app" / "static" / "editorial.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comments(css: str) -> str:
    """Remove /* ... */ comments so a guard against a literal token
    inside a doc-comment doesn't false-positive."""
    out = []
    i = 0
    while i < len(css):
        if css[i:i + 2] == "/*":
            end = css.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        out.append(css[i])
        i += 1
    return "".join(out)


def _knowledge_body_block(css: str) -> str:
    css = _strip_comments(css)
    selector = "body[data-page=\"knowledge-base\"] .knowledge-body {"
    idx = css.index(selector)
    block_end = css.index("}", idx)
    return css[idx:block_end]


def test_knowledge_body_does_not_use_purple_surface_muted() -> None:
    css = _read(EDITORIAL)
    block = _knowledge_body_block(css)
    # Must not reference the lavender --surface-muted token directly.
    # The elevated neutral is the intended replacement; any reference to
    # --surface-muted would give the expanded body too much visual weight.
    assert "var(--surface-muted)" not in block, (
        "knowledge-body must not use --surface-muted; see "
        "docs/design-guidelines.md §9 "
        "color-consistency rules"
    )


def test_knowledge_body_does_not_use_purple_accent_stripe() -> None:
    css = _read(EDITORIAL)
    block = _knowledge_body_block(css)
    # Must not reference --accent as the left stripe — that token is the
    # theme accent. Use --border-strong so the stripe remains
    # neutral rather than reading as an accent state.
    assert "var(--accent)" not in block, (
        "knowledge-body left stripe must not use --accent (which is the "
        "theme accent in editorial.css)"
    )


def test_knowledge_body_uses_elevated_neutral_surface() -> None:
    css = _read(EDITORIAL)
    block = _knowledge_body_block(css)
    assert "var(--surface-elevated)" in block
