"""Static guards for the unified skeleton shimmer animation.

Background:
    2026-08-14 refactor generalized @keyframes skeletonShimmer
    (1.6s opacity 0.45↔0.85 breathing) so all loading placeholders
    share the same "I'm working" rhythm. The four carriers are:

        - .chart-skeleton-candle / .chart-skeleton-axis span (via .loading-pulse)
        - .shimmer-bar::after (loadingState progress bar)
        - .nav-skeleton-row (SPA navigation placeholder)
        - .event-stream-skeleton-copy i (market-events feed text bars)

    Dead keyframes shimmerSlide and nav-skeleton-shimmer must be removed.

These tests pin the four carriers + dead-keyframe cleanup so any
future drift (e.g. someone re-introducing a sweep animation on
.shimmer-bar) is caught by CI.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
DOM = (ROOT / "app" / "static" / "core" / "dom.js").read_text(encoding="utf-8")


# ---- 1. keyframe definition ---------------------------------------------

def test_skeletonShimmer_keyframe_defined() -> None:
    """@keyframes skeletonShimmer must define 0.45↔0.85 opacity breath."""
    # Keyframes contain nested { ... } blocks (per-step), so we
    # bracket-balance instead of relying on [^}]+ which truncates
    # at the first inner brace.
    start = STYLES.find("@keyframes skeletonShimmer")
    assert start >= 0, "@keyframes skeletonShimmer missing in styles.css"
    # Find the opening brace of the keyframe body
    open_brace = STYLES.find("{", start)
    assert open_brace > 0
    depth = 0
    body_start = open_brace + 1
    body_end = body_start
    for i in range(body_start, len(STYLES)):
        ch = STYLES[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                body_end = i
                break
            depth -= 1
    body = STYLES[body_start:body_end]
    assert re.search(r"0%\s*,\s*100%\s*\{\s*opacity:\s*0\.45", body), (
        "skeletonShimmer 0%/100% should be opacity:0.45"
    )
    assert re.search(r"50%\s*\{\s*opacity:\s*0\.85", body), (
        "skeletonShimmer 50% should be opacity:0.85"
    )


# ---- 2. .loading-pulse carrier class -------------------------------------

def test_loading_pulse_class_references_skeletonShimmer() -> None:
    """.loading-pulse must drive the unified breathing animation."""
    assert re.search(
        r"\.loading-pulse\s*\{[^}]*animation:[^}]*skeletonShimmer",
        STYLES,
    ), ".loading-pulse must use skeletonShimmer animation"


# ---- 3. chartSkeleton() DOM emits .loading-pulse ------------------------

def test_chart_skeleton_candles_carry_loading_pulse_class() -> None:
    """Each <div class="chart-skeleton-candle"> must also carry loading-pulse."""
    assert 'class="chart-skeleton-candle loading-pulse"' in DOM, (
        "chartSkeleton() must emit chart-skeleton-candle with loading-pulse class"
    )


def test_chart_skeleton_axis_spans_carry_loading_pulse_class() -> None:
    """Each axis <span> must carry loading-pulse."""
    # Pattern: <span class="loading-pulse"></span> appears 5 times
    matches = re.findall(
        r'<span\s+class="loading-pulse"></span>',
        DOM,
    )
    assert len(matches) >= 5, (
        f"chartSkeleton() axis should emit ≥5 loading-pulse spans, got {len(matches)}"
    )


# ---- 4. .shimmer-bar::after switched to skeletonShimmer ------------------

def test_shimmer_bar_after_uses_skeleton_shimmer() -> None:
    """.shimmer-bar::after must animate via skeletonShimmer (no shimmerSlide)."""
    # Bracket-balance extraction (handles nested { } in @media etc).
    selector = ".shimmer-bar::after"
    sel_idx = STYLES.find(selector)
    assert sel_idx >= 0, ".shimmer-bar::after rule missing"
    open_brace = STYLES.find("{", sel_idx)
    assert open_brace > 0
    depth = 0
    body_start = open_brace + 1
    body_end = body_start
    for i in range(body_start, len(STYLES)):
        ch = STYLES[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                body_end = i
                break
            depth -= 1
    body = STYLES[body_start:body_end]
    # Only the animation declaration matters — comments may mention
    # removed keyframes for migration context.
    anim_match = re.search(r"animation:\s*([^;]+);", body)
    assert anim_match is not None, (
        ".shimmer-bar::after must declare an animation"
    )
    anim_value = anim_match.group(1)
    assert "skeletonShimmer" in anim_value, (
        ".shimmer-bar::after animation must reference skeletonShimmer"
    )
    assert "shimmerSlide" not in anim_value, (
        ".shimmer-bar::after animation must NOT reference removed shimmerSlide"
    )


# ---- 5. .nav-skeleton-row switched to skeletonShimmer -------------------

def test_nav_skeleton_row_uses_skeleton_shimmer() -> None:
    """.nav-skeleton-row must animate via skeletonShimmer (no nav-skeleton-shimmer)."""
    selector = ".nav-skeleton-row"
    sel_idx = STYLES.find(selector)
    assert sel_idx >= 0, ".nav-skeleton-row rule missing in styles.css"
    open_brace = STYLES.find("{", sel_idx)
    depth = 0
    body_start = open_brace + 1
    body_end = body_start
    for i in range(body_start, len(STYLES)):
        ch = STYLES[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                body_end = i
                break
            depth -= 1
    body = STYLES[body_start:body_end]
    anim_match = re.search(r"animation:\s*([^;]+);", body)
    assert anim_match is not None, (
        ".nav-skeleton-row must declare an animation"
    )
    anim_value = anim_match.group(1)
    assert "skeletonShimmer" in anim_value, (
        ".nav-skeleton-row animation must reference skeletonShimmer"
    )
    assert "nav-skeleton-shimmer" not in anim_value, (
        ".nav-skeleton-row animation must NOT reference removed nav-skeleton-shimmer"
    )


# ---- 6. .event-stream-skeleton-copy i added skeletonShimmer -------------

def test_event_stream_skeleton_copy_uses_skeleton_shimmer() -> None:
    """market-events feed text bars must breathe with skeletonShimmer."""
    selector = ".event-stream-skeleton-copy i"
    sel_idx = EDITORIAL.find(selector)
    assert sel_idx >= 0, (
        ".event-stream-skeleton-copy i rule missing in editorial.css"
    )
    open_brace = EDITORIAL.find("{", sel_idx)
    depth = 0
    body_start = open_brace + 1
    body_end = body_start
    for i in range(body_start, len(EDITORIAL)):
        ch = EDITORIAL[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                body_end = i
                break
            depth -= 1
    body = EDITORIAL[body_start:body_end]
    anim_match = re.search(r"animation:\s*([^;]+);", body)
    assert anim_match is not None, (
        ".event-stream-skeleton-copy i must declare an animation"
    )
    assert "skeletonShimmer" in anim_match.group(1), (
        ".event-stream-skeleton-copy i animation must reference skeletonShimmer"
    )


# ---- 7. dead keyframes cleaned up ---------------------------------------

def test_dead_keyframe_shimmerSlide_removed() -> None:
    """@keyframes shimmerSlide must be deleted (replaced by skeletonShimmer)."""
    assert "@keyframes shimmerSlide" not in STYLES, (
        "@keyframes shimmerSlide should be removed — shimmer-bar uses skeletonShimmer"
    )


def test_dead_keyframe_nav_skeleton_shimmer_removed() -> None:
    """@keyframes nav-skeleton-shimmer must be deleted (replaced by skeletonShimmer)."""
    assert "@keyframes nav-skeleton-shimmer" not in STYLES, (
        "@keyframes nav-skeleton-shimmer should be removed — nav-skeleton-row uses skeletonShimmer"
    )


# ---- 8. prefers-reduced-motion unchanged --------------------------------

def test_reduced_motion_global_block_still_present() -> None:
    """Global @media (prefers-reduced-motion: reduce) must clamp duration to 0.01ms."""
    match = re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]+?)\n\}",
        STYLES,
    )
    assert match is not None, (
        "prefers-reduced-motion media query missing in styles.css"
    )
    body = match.group(1)
    assert "animation-duration: 0.01ms !important" in body, (
        "Global reduced-motion must clamp animation-duration to 0.01ms"
    )


def test_loading_pulse_reduced_motion_strategy() -> None:
    """.loading-pulse should NOT appear in the explicit 'animation: none' list —
    it relies on the global duration clamp (consistent with other skeletonShimmer
    carriers). The explicit 'none' list should only target true infinite loops
    that benefit from complete disable (vol-compression-spin / dropdown-spin).
    """
    match = re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]+?)\n\}",
        STYLES,
    )
    assert match is not None
    body = match.group(1)
    # Find the explicit 'animation: none' block(s)
    none_blocks = re.findall(
        r"([^{}]+)\{\s*animation:\s*none\s*!important\s*;?\s*\}",
        body,
    )
    joined = " | ".join(none_blocks)
    assert ".loading-pulse" not in joined, (
        ".loading-pulse should rely on the global clamp, not the explicit none list"
    )