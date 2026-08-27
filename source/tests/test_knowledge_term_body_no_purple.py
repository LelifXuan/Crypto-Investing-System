"""Static guard: term-detail `.knowledge-body` must NOT use lavender / purple.

Background: editorial.css redefines `:root --surface-muted: #f0edf3` (light
lavender) and `:root --accent: #66548e` (mid purple). Combined with the
previous rule

    body[data-page="knowledge-base"] .knowledge-body {
      background: var(--surface-muted);
      border-left: 3px solid var(--accent);
    }

this produced a lavender slab with a purple left-stripe on every opened
term card. The user flagged it as AI-default purple. Switched to hard-coded
neutral warm cream + warm border instead. This guard prevents regression
to the purple tokens.
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
    # Hard-coded neutral cream (rgba(255, 253, 249, ...)) is the intended
    # replacement; any reference to --surface-muted in this block would
    # silently re-introduce the lavender look.
    assert "var(--surface-muted)" not in block, (
        "knowledge-body must not use --surface-muted (which is #f0edf3 "
        "lavender in editorial.css); see docs/design-guidelines.md §9 "
        "color-consistency rules"
    )


def test_knowledge_body_does_not_use_purple_accent_stripe() -> None:
    css = _read(EDITORIAL)
    block = _knowledge_body_block(css)
    # Must not reference --accent as the left stripe — that token is the
    # indigo-purple #66548e. Use --border-strong (warm brown) or a neutral
    # tone instead so the stripe reads as warm-cream-page chrome rather
    # than AI purple.
    assert "var(--accent)" not in block, (
        "knowledge-body left stripe must not use --accent (which is the "
        "indigo-purple #66548e in editorial.css)"
    )


def test_knowledge_body_does_not_paint_lavender_hex() -> None:
    css = _read(EDITORIAL)
    block = _knowledge_body_block(css)
    # Guard against someone copying the lavender value back from the
    # token definition into a hard-coded background.
    assert "#f0edf3" not in block, (
        "knowledge-body must not paint the lavender #f0edf3 background"
    )