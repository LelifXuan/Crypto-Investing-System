"""Static smoke checks for §13.2 #6 local component color tokenization.

Asserts that:
1. editorial.css :root declares the 20 --info-* tokens (18 base + 2 sub-tier).
2. styles.css only emits indigo literals inside :root declarations that ARE
   the --info-* token source-of-truth (i.e. zero raw rgba(99,102,241,*) at
   consumer site). One linear-gradient pair stop is documented exception.
3. charts.js keeps its palette literals as SSR/legacy fallbacks but the
   CSS var names appear in the CHART_SERIES read path (already enforced
   by test_chart_series_token_consistency).
4. No "dead fallback" pattern remains (var(--X, rgba(99,...)) is forbidden).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "app" / "static" / "editorial.css"
STYLES = ROOT / "app" / "static" / "styles.css"
CHARTS_JS = ROOT / "app" / "static" / "ui" / "charts.js"

# 18 base + 2 sub-tier (info-ghost-faint, info-surface-soft) = 20 tokens.
EXPECTED_INFO_TOKENS = [
    "--info-ghost",
    "--info-ghost-soft",
    "--info-ghost-faint",
    "--info-ghost-strong",
    "--info-surface-soft",
    "--info-tint",
    "--info-tint-em",
    "--info-tint-strong",
    "--info-tint-max",
    "--info-edge",
    "--info-edge-strong",
    "--info-edge-max",
    "--info-glow",
    "--info-key",
    "--info-focus",
    "--info-focus-em",
    "--info-halo-soft",
    "--info-halo",
    "--info-halo-mid",
    "--info-halo-strong",
    "--info-halo-em",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_editorial_declares_every_info_token() -> None:
    source = _read(EDITORIAL)
    missing: list[str] = []
    for token in EXPECTED_INFO_TOKENS:
        # Look for declaration: `--token-name: rgba(...)` form (use lookbehind
        # for whitespace or { so `--info-*` matches without word-boundary traps).
        if not re.search(rf"(?<![\w-]){re.escape(token)}\s*:", source):
            missing.append(token)
    assert not missing, f"editorial.css missing --info-* token declarations: {missing}"


def test_styles_emits_no_consumer_side_indigo_literals() -> None:
    """Every rgba(99,102,241,α) outside :root declarations in editorial.css
    must have been migrated to var(--info-*). The only acceptable residuals
    are documented exceptions inside linear-gradient stop tuples."""
    styles = _read(STYLES)
    # Strip comments to avoid matching commentary.
    no_comments = re.sub(r"/\*.*?\*/", "", styles, flags=re.DOTALL)
    hits = re.findall(r"rgba\(\s*99\s*,?\s*102\s*,?\s*241\s*,[^)]*\)", no_comments)
    # The 0.03 literal inside .strategy-primary-plan-card linear-gradient
    # (paired with var(--info-ghost-strong) at the other end) is the lone
    # documented exception; this guard accepts it.
    assert len(hits) <= 1, (
        f"styles.css emits raw indigo literals outside :root ({len(hits)} found, "
        f"expected ≤ 1 for the documented gradient pair stop): {hits[:3]}"
    )
    if len(hits) == 1:
        assert hits[0].endswith("0.03)"), (
            f"unexpected residual indigo literal: {hits[0]!r}"
        )


def test_no_dead_indigo_fallback_in_var_clamps() -> None:
    """The pattern `var(--X, rgba(99,102,241,...))` is forbidden — both --X
    tokens (--neutral-soft, --accent-ghost) are defined in editorial.css."""
    target = _read(STYLES)
    bad = re.findall(
        r"var\(--(?:neutral-soft|accent-ghost),\s*rgba\(\s*99\s*,?\s*102\s*,?\s*241",
        target,
    )
    assert not bad, f"dead indigo fallback literal present: {bad}"


def test_charts_js_keeps_indigo_palette_literals_but_with_crossref() -> None:
    """charts.js SERIES_FALLBACK may carry rgba(99,102,241,*) literally —
    that's the SSR/bootstrap path. The cross-reference comment must point
    readers to the CSS source-of-truth."""
    source = _read(CHARTS_JS)
    # The literal is fine — we just enforce that the cross-reference comment
    # is present and mentions editorial.css.
    assert "editorial.css" in source, (
        "charts.js should reference editorial.css :root as the palette source-of-truth"
    )
    # And the read path must consume --series-pattern-zone / --pattern-fill-neutral.
    assert "_readCssVar" in source
    assert "--series-pattern-zone" in source
    assert "--pattern-fill-neutral" in source


def test_styles_references_at_least_one_info_token() -> None:
    """Sanity: the migration actually flowed through to consumer code. If
    this fails it means tokens were defined but no caller picked them up."""
    styles = _read(STYLES)
    used = re.findall(r"var\(--info-[a-z-]+\)", styles)
    families = {re.match(r"var\(--info-([a-z-]+)\)", u).group(1) for u in used}
    # Expect at least 12 distinct families wired into styles.css.
    assert len(families) >= 12, (
        f"expected ≥12 distinct --info-* families in styles.css consumers, got {len(families)}: {sorted(families)}"
    )
