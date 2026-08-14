"""Static guards for the SPA router's nav-click handling in main.js.

Regression: a nav click landing while the previous page's boot() was still
settling (mount() may await a data fetch) used to be silently dropped — the
click handler returned with `event.preventDefault()` and no navigation. The
link felt dead and verify_pages' SPA-switch test timed out (btc-derivatives
5s timeout after ashare-etf). The fix queues the pending navigation and
flushes it when the in-flight boot settles.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = REPO_ROOT / "app" / "static" / "main.js"


def _read() -> str:
    return MAIN_PATH.read_text(encoding="utf-8")


class TestQueuedNavigation:
    def test_pending_navigation_holder_exists(self):
        src = _read()
        assert "let pendingSpaNavigation = null;" in src, (
            "main.js must hold a pending-navigation slot for clicks that land "
            "while a boot is in flight"
        )

    def test_click_queues_when_in_flight(self):
        """The click handler must queue { pageId, href } instead of dropping
        when spaNavigationInFlight is true."""
        src = _read()
        assert "if (spaNavigationInFlight) {" in src
        assert "pendingSpaNavigation = { pageId, href };" in src

    def test_boot_finally_flushes_pending(self):
        """boot().finally() must clear spaNavigationInFlight AND flush the
        queued navigation."""
        src = _read()
        assert "spaNavigationInFlight = false;" in src
        assert "pendingSpaNavigation = null;" in src
        # The flush must actually navigate (pushState + scheduleBoot), not
        # just clear the slot.
        assert "navigateToPage(pending.pageId, pending.href);" in src

    def test_navigate_to_page_helper_used(self):
        src = _read()
        assert "function navigateToPage(pageId, href)" in src
        assert "window.history.pushState({ pageId, href }" in src

    def test_popstate_clears_queued_navigation(self):
        """Back/forward must clear any queued nav click so the boot finally
        doesn't bounce back to a stale target."""
        src = _read()
        assert "pendingSpaNavigation = null;" in src

    def test_no_silent_drop_branch(self):
        """The old dead-click branch (preventDefault + return inside the
        in-flight guard) must be gone — the in-flight branch now queues."""
        src = _read()
        assert "if (spaNavigationInFlight) {\n      event.preventDefault();" not in src
