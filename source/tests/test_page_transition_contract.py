from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN = (REPO_ROOT / "app" / "static" / "main.js").read_text(encoding="utf-8")
STYLES = (REPO_ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
EDITORIAL = (REPO_ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
# 2026-08-27: post-token-ownership cleanup, route motion tokens (--dur-route-*)
# moved into editorial.css. The browser still sees both stylesheets, so any
# CSS-level assertion about "the page has X selector / Y token" must look at
# the full concatenated cascade, not styles.css alone.
CSS_STACK = STYLES + "\n" + EDITORIAL


def test_old_page_exits_before_route_skeleton_is_mounted() -> None:
    boot = MAIN.index("async function boot()")
    exit_call = MAIN.index("await transitionOutCurrentPage(pageRoot);", boot)
    skeleton_call = MAIN.index("mountRouteSkeleton(pageRoot, pageMeta);", exit_call)
    assert exit_call < skeleton_call
    navigate = MAIN[MAIN.index("function navigateToPage"):MAIN.index("function installSpaRouter")]
    assert "pageRoot.innerHTML" not in navigate
    assert "renderNavSkeleton" not in navigate


def test_route_motion_uses_short_transform_and_opacity_only() -> None:
    assert "--dur-route-exit: 72ms" in CSS_STACK
    assert "--dur-route-skeleton: 120ms" in CSS_STACK
    assert "--dur-route-enter: 160ms" in CSS_STACK
    assert "translateY(-2px)" in CSS_STACK
    assert "opacity: 0.55; transform: translateY(3px)" in CSS_STACK
    assert ".page-transition-skeleton" in CSS_STACK
    assert "will-change: opacity, transform" in CSS_STACK
    assert "revealStagger(pageRoot);" in MAIN


def test_initial_load_skips_route_enter_and_queued_navigation_has_feedback() -> None:
    assert "transitionInNewPage(pageRoot, isRouteTransition);" in MAIN
    assert "const isRouteTransition = activePageId !== null && activePageId !== pageId;" in MAIN
    assert "setPendingNavigation(pageId);" in MAIN
    assert ".editorial-nav a.is-pending" in EDITORIAL
    assert "navPendingPulse" in EDITORIAL
    assert "transitionInPageIdentity(isRouteTransition);" in MAIN
    assert ".app-page-identity.is-route-entering" in EDITORIAL
    assert MAIN.rstrip().endswith("scheduleBoot();")
