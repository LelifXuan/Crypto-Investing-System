"""Static guards for the market-event feed loading experience."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "market_events.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_new_event_page_immediately_renders_a_feed_skeleton() -> None:
    assert "function renderEventFeedLoading()" in PAGE
    assert '${renderEventFeedLoading()}' in PAGE
    assert 'id="events-feed" aria-busy="true"' in PAGE
    assert 'lastFeedFingerprint = ""' in PAGE
    assert 'lastCalendarFingerprint = ""' in PAGE


def test_feed_motion_is_page_specific_and_reduced_motion_safe() -> None:
    assert "@keyframes eventStreamArrive" in CSS
    assert "@keyframes eventFeedSync" in CSS
    assert ".event-stream-skeleton-row" in CSS
    assert "prefers-reduced-motion: reduce" in CSS
    assert "animation: none !important" in CSS


def test_manual_refresh_exposes_busy_state_without_blank_replacement() -> None:
    assert "setFeedBusy(true)" in PAGE
    assert "setFeedBusy(false)" in PAGE
    assert 'feed.setAttribute("aria-busy", String(isBusy))' in PAGE
