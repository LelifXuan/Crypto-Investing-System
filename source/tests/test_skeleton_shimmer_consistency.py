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
    """@keyframes skeletonShimmer must define an opacity breath.

    2026-08-17: tuned from 0.45↔0.85 → 0.78↔1.0 → 0.65↔1.0 (Δ 0.35).
    The candle breath (chart-skeleton-candle, scaleY+opacity wave) is the
    primary motion signal. The wrapper opacity keeps non-candle carriers
    (axis spans, .shimmer-bar::after, .nav-skeleton-row,
    .event-stream-skeleton-copy i) visibly alive — too subtle (0.78↔1.0,
    Δ 0.22) made the horizontal bars read as static.
    """
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
    # Wrapper breath at rest should be lighter than the candle peak
    # (candles reach opacity 0.95 mid-cycle). Range 0.5–0.85 keeps the
    # wrapper visible without competing with the candle wave; peak ~1.0
    # is the upper bound.
    m = re.search(r"0%\s*,\s*100%\s*\{\s*opacity:\s*([0-9.]+)", body)
    assert m is not None, "skeletonShimmer 0%/100% must declare opacity"
    rest = float(m.group(1))
    assert 0.5 <= rest <= 0.85, (
        f"skeletonShimmer rest opacity should be in [0.5, 0.85] for visible breath "
        f"(Δ≥0.15), got {rest}"
    )
    peak = float(re.search(r"50%\s*\{\s*opacity:\s*([0-9.]+)", body).group(1))
    assert peak >= 0.95, (
        f"skeletonShimmer peak should be ~1.0 (got {peak})"
    )
    delta = peak - rest
    assert delta >= 0.15, (
        f"skeletonShimmer breath delta should be ≥0.15 (visible), got {delta:.2f}"
    )
    assert delta < 0.5, (
        f"skeletonShimmer breath delta should be <0.5 so it doesn't compete "
        f"with candle wave; got {delta:.2f}"
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
    # Axis markup is generated from five entries and each carries its phase.
    matches = re.findall(
        r'<span\s+class="loading-pulse"\s+style="\$\{skeletonPhaseStyle',
        DOM,
    )
    assert "{ length: 5 }" in DOM
    assert matches, "chartSkeleton() axis spans must carry loading-pulse and a global phase"


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

# ---- 7b. per-candle scaleY wave (2026-08-17 redesign) -------------------

def test_candleBreath_keyframe_defined() -> None:
    """@keyframes candleBreath must define a coordinated scaleY+opacity wave.

    Replaces the prior per-candle ::after translateX sweep. Each candle
    fades+rises from a runtime negative phase, so the breath reads as a
    single left→right wave immediately rather than N independent sweeps.
    """
    assert "@keyframes candleBreath" in STYLES, (
        "@keyframes candleBreath missing — per-candle scaleY wave not implemented"
    )
    # Wave must move scaleY (not just opacity) to feel like "linked breath"
    assert re.search(
        r"@keyframes candleBreath[\s\S]*?scaleY",
        STYLES,
    ), "@keyframes candleBreath must animate scaleY for the linked-breath wave"
    # Wave must use ease-in-out (smooth start/end), not linear.
    # The animation is declared on .chart-skeleton-candle.loading-pulse
    # (higher specificity) so it wins over the bare .loading-pulse
    # skeletonShimmer rule that lives later in the file.
    candle_rule = re.search(
        r"\.chart-skeleton-candle\.loading-pulse\s*\{[^}]*animation:\s*([^;]+);",
        STYLES,
    )
    assert candle_rule is not None, (
        ".chart-skeleton-candle.loading-pulse must declare an animation"
    )
    assert "candleBreath" in candle_rule.group(1), (
        ".chart-skeleton-candle.loading-pulse animation must reference candleBreath"
    )
    assert "infinite" in candle_rule.group(1), (
        "candleBreath should be infinite (skeleton loops until data lands)"
    )


def test_chart_skeleton_candle_uses_runtime_negative_phase() -> None:
    """Any candle count must join the wave immediately without nth-child rules."""
    assert "skeletonPhaseStyle(-i, { periodMs: 2400, stepMs: 70 })" in DOM
    assert "--candle-index" not in STYLES
    assert re.search(
        r"animation-delay:\s*var\(--skeleton-delay,\s*0ms\)",
        STYLES,
    )


def test_chart_skeleton_no_legacy_shimmer_sweep() -> None:
    """@keyframes shimmerSweep must be removed — replaced by candleBreath wave."""
    assert "@keyframes shimmerSweep" not in STYLES, (
        "@keyframes shimmerSweep should be removed — per-candle sweep replaced by candleBreath"
    )


def test_chart_skeleton_candle_fill_mode_both() -> None:
    """.chart-skeleton-candle.loading-pulse must set animation-fill-mode: both.

    Runtime delays are negative, so there is no pending delay window. Keep
    "both" as a defensive contract for CSS fallback or future retiming.
    """
    candle_rule = re.search(
        r"\.chart-skeleton-candle\.loading-pulse\s*\{([^}]*)\}",
        STYLES,
    )
    assert candle_rule is not None, (
        ".chart-skeleton-candle.loading-pulse rule missing"
    )
    body = candle_rule.group(1)
    assert "animation-fill-mode" in body, (
        ".chart-skeleton-candle.loading-pulse must set animation-fill-mode"
    )
    assert re.search(r"animation-fill-mode:\s*both", body), (
        "animation-fill-mode must be 'both' so candles show trough state during delay"
    )


def test_chart_skeleton_candle_no_after_pseudo() -> None:
    """The old per-candle pseudo-element sweep must remain removed."""
    assert ".chart-skeleton-candle::after" not in STYLES, (
        ".chart-skeleton-candle::after should stay replaced by the candleBreath wave"
    )


def test_reduced_motion_global_block_still_present() -> None:
    """Global @media (prefers-reduced-motion: reduce) must clamp duration to 0.01ms."""
    matches = re.findall(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]+?)\n\}",
        STYLES,
    )
    assert matches, (
        "prefers-reduced-motion media query missing in styles.css"
    )
    # 2026-09-04: page-local cold-start blocks precede the global clamp in
    # the file; the GLOBAL block is whichever one carries the 0.01ms rule.
    assert any(
        "animation-duration: 0.01ms !important" in body for body in matches
    ), "Global reduced-motion must clamp animation-duration to 0.01ms"


def test_loading_pulse_reduced_motion_strategy() -> None:
    """Reduced-motion users receive a stable placeholder, not a compressed loop."""
    matches = re.findall(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]+?)\n\}",
        STYLES,
    )
    assert matches
    # The global clamp block (not the cold-start override) owns the
    # stable-placeholder rules for loading-pulse and stagger items.
    body = next((b for b in matches if ".loading-pulse" in b), matches[-1])
    assert ".loading-pulse" in body
    assert "[data-stagger-item]" in body
    assert "animation: none !important" in body
