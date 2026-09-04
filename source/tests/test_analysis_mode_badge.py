"""Playwright tests for the regime mode badge in the technical indicator page."""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _backend_up() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", 8002))
        return True
    except (socket.error, socket.timeout):
        return False
    finally:
        s.close()


@pytest.fixture
def base_url():
    return os.getenv("BASE_URL", "http://127.0.0.1:8002")


def _open_analysis(page, base_url, query=""):
    response = page.goto(f"{base_url}/indicators-page{query}", wait_until="domcontentloaded")
    assert response.status == 200
    page.locator(".analysis-hero-grid").wait_for()


def _mock_mode_bundle(page, mode):
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)
    candles = [
        {
            "ts_open": (origin + timedelta(hours=index)).isoformat(),
            "open": str(100 + index),
            "high": str(103 + index),
            "low": str(99 + index),
            "close": str(102 + index),
            "volume": "1000",
        }
        for index in range(240)
    ]
    payload = {
        "status": "ready",
        "mode": mode,
        "candles": candles,
        "core_indicator_series": {},
        "secondary_indicator_series": {"bbands_width": [10] * 239 + [2]},
    }
    page.route(
        "**/api/v1/analysis/bundle**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload)
        ),
    )


def test_range_mode_badge_visible(base_url):
    """When the analysis payload reports mode='range', the status-bar badge is shown."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        _mock_mode_bundle(page, "range")
        _open_analysis(page, base_url)
        badge = page.locator(".status-mode-badge.range-mode")
        badge.wait_for()
        assert badge.is_visible()
        link = badge.locator("a.regime-action")
        assert link.count() == 1
        assert link.get_attribute("href") == "/structure-page"

        ctx.close()
        browser.close()


def test_transition_mode_badge_visible(base_url):
    """Transition badge gives a user-facing direction and execution plan."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        _mock_mode_bundle(page, "transition")
        _open_analysis(page, base_url)
        badge = page.locator(".status-mode-badge.transition-mode")
        badge.wait_for()
        assert badge.is_visible()
        text = badge.inner_text()
        assert any(label in text for label in ("偏多", "偏空", "区间震荡"))
        assert "vol_compression" not in text
        assert "mt_compression" not in text
        # The compact transition badge is informational, with no obsolete
        # self-link to the removed /market-analysis route.
        assert badge.locator("a").count() == 0

        ctx.close()
        browser.close()


def test_focus_banner_removed_on_analysis_page(base_url):
    """The wide trade-judgement banner is no longer rendered on the technical
    indicator page (2026-08-11 product decision — the content duplicates the
    AI strategy page; only the compact status-mode badge remains). Whatever the
    mode or ?focus= param, `.status-focus-banner` must not appear."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        _open_analysis(page, base_url, "?focus=breakout")
        page.wait_for_timeout(2000)

        banner = page.locator(".status-focus-banner")
        assert banner.count() == 0, (
            "The focus banner was removed from the analysis page (2026-08-11); "
            "the compact status-mode-badge is the only mode indicator."
        )

        # The URL must keep focus=breakout so the user can refresh and still
        # see the same mode.
        assert "focus=breakout" in page.url

        ctx.close()
        browser.close()


def test_focus_banner_absent_without_param(base_url):
    """No `.status-focus-banner` is ever rendered on the analysis page (the
    wide banner was removed on 2026-08-11), regardless of URL params."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        _open_analysis(page, base_url)
        page.wait_for_timeout(2000)

        banner = page.locator(".status-focus-banner")
        assert banner.count() == 0

        ctx.close()
        browser.close()


def test_mode_badge_markup_has_no_emoji_or_text_arrow():
    """Static guard: the redesigned regime badge must rely on inline SVG and
    three-zone DOM (`regime-icon` / `regime-info` / `regime-action`) instead
    of platform-dependent emoji and textual arrows."""
    source = (ROOT / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8")
    start = source.index("function renderModeBadge")
    end = source.index("function setRefreshBusy", start)
    badge_block = source[start:end]
    assert "📊" not in badge_block, "Range badge must not use emoji"
    assert "⚡" not in badge_block, "Transition badge must not use emoji"
    assert "→" not in badge_block, "Status badge must not use textual arrow"
    assert "regime-icon" in badge_block, "Status badge must use regime-icon block"
    assert "regime-info" in badge_block, "Status badge must use regime-info block"
    assert "regime-action" in badge_block, "Status badge must use regime-action block"
    assert "<svg" in badge_block, "Status badge must include inline SVG"


def test_focus_banner_never_renders_when_data_empty(base_url):
    """The wide focus banner is removed from the analysis page (2026-08-11
    product decision), so even a cold bundle (`secondary_indicator_series`
    empty) must not produce a `.status-focus-banner` node — the compact
    status-mode-badge carries the mode state instead.

    Kept as a browser test rather than deleted so future re-introductions of
    the banner are reviewed against this decision.
    """
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        # Intercept the analysis bundle response and short-circuit
        # secondary_indicator_series to an empty object so the frontend
        # phase classification returns null. We KEEP the mode field
        # at "transition" — the old banner branch is not entered any more.
        def _short_circuit_bundle(route, request):
            body = (
                '{"status":"ready","mode":"transition",'
                '"secondary_indicator_series":{},'
                '"core_indicator_series":{},'
                '"candles":[],"mark":null}'
            )
            route.fulfill(status=200, content_type="application/json", body=body)

        page.route("**/api/v1/analysis/bundle**", _short_circuit_bundle)

        page.goto(
            f"{base_url}/indicators-page?focus=breakout",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(2500)

        banner = page.locator(".status-focus-banner")
        assert banner.count() == 0, (
            "The focus banner was removed from the analysis page (2026-08-11); "
            "it must not render even with focus=breakout and an empty bundle."
        )

        # The URL must still carry focus=breakout so a manual refresh keeps
        # the same mode.
        assert "focus=breakout" in page.url

        ctx.close()
        browser.close()
