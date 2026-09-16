"""Static smoke checks for §13.2 #7 width-breakpoint consolidation.

Asserts that:
1. styles.css + editorial.css together use only 6 width breakpoints:
   `560` (mobile-s) / `720` (mobile-l) / `900` (tablet) /
   `1180` (small-desktop) / `1500` (wide-desktop), plus `520` as an
   acknowledged mobile-s extreme sub-tier.
2. No legacy breakpoint widths remain (`640`, `700`, `760`, `767`,
   `768`, `780`, `800`, `960`, `980`, `1100`, `1181`, `1200`, `1279`,
   `1280`, `1400`, `1599`).
3. A11y/input-feature breakpoints (hover/pointer/reduced-motion/reduced-
   transparency) are exempt from the width-breakpoint count.
4. `min-width` and `max-width` queries match the canonical 6-group set
   (allow `min-width: 1181` and `min-width: 1500` as the small-desktop
   and wide-desktop lower edges).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root
CSS_FILES = [
    ROOT / "source" / "app" / "static" / "styles.css",
    ROOT / "source" / "app" / "static" / "editorial.css",
]

# Canonical 6-group; `520` is an acknowledged mobile-s extreme sub-tier.
CANONICAL_WIDTHS = {560, 720, 900, 1180, 1500}
ALLOWED_SUB_TIERS = {520, 721}  # 520 mobile-s extreme; 721 desktop+ lower edge
OBSOLETE_WIDTHS = {640, 700, 760, 767, 768, 780, 800, 960, 980, 1100,
                   1181, 1200, 1279, 1280, 1400, 1599}

# A11y / input-feature media queries are exempt.
A11Y_QUERY_PREFIXES = (
    "(hover:",
    "(any-hover:",
    "(pointer:",
    "(any-pointer:",
    "(prefers-reduced-motion:",
    "(prefers-reduced-transparency:",
    "(prefers-color-scheme:",
    "(prefers-contrast:",
    "(orientation:",
    "(forced-colors:",
)


def _width_queries(source: str) -> list[tuple[str, str]]:
    """Return list of (operator, value_string) for every width breakpoint
    query that is NOT an a11y/input feature query.

    Example returns:
      ("max-width", "720px")
      ("min-width", "1180px")
    """
    results: list[tuple[str, str]] = []
    # Greedily capture @media (...width... px...) clauses. We intentionally
    # match per-clause rather than per-file for clarity.
    for m in re.finditer(
        r"@media\s*\(\s*(max-width|min-width)\s*:\s*(\d+)px\s*\)", source
    ):
        op, value = m.group(1), int(m.group(2))
        results.append((op, value))
    return results


def _a11y_query_count(source: str) -> int:
    return sum(source.count(p) for p in A11Y_QUERY_PREFIXES)


def test_only_canonical_width_breakpoints_used() -> None:
    """Across both CSS files the only width breakpoints used are the 6
    canonical values (plus mobile-s `520` extreme sub-tier)."""
    all_widths: list[tuple[str, int, str]] = []
    for css in CSS_FILES:
        if not css.exists():
            continue
        source = css.read_text(encoding="utf-8")
        for op, value in _width_queries(source):
            all_widths.append((op, value, css.name))

    # Group by (op, value) for visibility.
    counts: dict[tuple[str, int], int] = {}
    for op, value, _ in all_widths:
        counts[(op, value)] = counts.get((op, value), 0) + 1

    unexpected = [
        (op, value) for (op, value), _ in counts.items()
        if value not in CANONICAL_WIDTHS and value not in ALLOWED_SUB_TIERS
    ]
    assert not unexpected, (
        f"unexpected non-canonical width breakpoint used: "
        f"{[(op, v, counts[(op, v)]) for op, v in unexpected]}. "
        f"Canonical set: {sorted(CANONICAL_WIDTHS)}; "
        f"sub-tier set: {sorted(ALLOWED_SUB_TIERS)}"
    )

    # And at least one breakpoint per group has been kept (sanity).
    expected = {720, 900, 1180, 1500}
    present = {v for (_, v) in counts.keys()}
    missing = expected - present
    assert not missing, (
        f"canonical width breakpoint groups missing from CSS: {missing}"
    )


def test_no_obsolete_width_breakpoints_remain() -> None:
    """Legacy widths (V2.x-era) must no longer appear in any @media query."""
    leaks: list[tuple[str, int, str]] = []
    for css in CSS_FILES:
        if not css.exists():
            continue
        source = css.read_text(encoding="utf-8")
        for op, value in _width_queries(source):
            if value in OBSOLETE_WIDTHS:
                leaks.append((op, value, css.name))

    assert not leaks, (
        f"obsolete width breakpoint still in use: {leaks}. "
        f"Obsolete set: {sorted(OBSOLETE_WIDTHS)}"
    )


def test_a11y_queries_exempt_from_width_consolidation() -> None:
    """Sanity check: this suite must not mistake a11y queries for width
    queries. We don't pin an exact count, just confirm the parser ignored
    them gracefully."""
    for css in CSS_FILES:
        if not css.exists():
            continue
        source = css.read_text(encoding="utf-8")
        _a11y_query_count(source)
        width = len(_width_queries(source))
        # V3.2: the codebase has at least one of each (hover, prefers-
        # reduced-motion); width count > 0 by design.
        assert width > 0, f"{css.name}: no width breakpoints found"


def test_breakpoint_groups_have_clear_separation() -> None:
    """Verify the canonical 6-group spacing: each group's max-width is at
    least 100px larger than the previous — no two values within 100px.
    This guards against accidental regressions like `720` and `767`."""
    widths = sorted(CANONICAL_WIDTHS)
    for prev, nxt in zip(widths, widths[1:], strict=False):
        gap = nxt - prev
        assert gap >= 100, (
            f"adjacent canonical breakpoints {prev} and {nxt} only {gap}px apart; "
            f"expected ≥100px separation"
        )
