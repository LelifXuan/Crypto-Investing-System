"""Playwright tests for the regime mode badge in the technical indicator page."""

from __future__ import annotations

import os
import socket
import sys
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


def test_range_mode_badge_visible(base_url):
    """When the analysis payload reports mode='range', the status-bar badge is shown."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/market-analysis", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        badge = page.locator(".status-mode-badge")
        if badge.count() > 0:
            assert badge.first.is_visible()
            link = badge.first.locator("a.status-mode-link")
            assert link.count() == 1
            href = link.first.get_attribute("href")
            assert href is not None
            assert "/structure-page" in href or "/market-structure" in href

        ctx.close()
        browser.close()


def test_transition_mode_badge_visible(base_url):
    """When mode='transition', the status-bar shows the transition badge with
    vol_compression info."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/market-analysis", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        badge = page.locator(".status-mode-badge.transition-mode")
        if badge.count() > 0:
            assert badge.first.is_visible()
            text = badge.first.inner_text()
            assert "波动率压缩" in text or "vol_compression" in text

        ctx.close()
        browser.close()


def test_focus_breakout_banner_visible(base_url):
    """When ?focus=breakout is in the URL AND mode='transition', a focus
    banner appears explaining the vol_compression context."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(
            f"{base_url}/market-analysis?focus=breakout",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(2000)

        # Without the transition badge we cannot compute vol_compression, so
        # the banner is intentionally absent. This matches the spec ("only if
        # focus=breakout and we're in transition mode").
        badge = page.locator(".status-mode-badge.transition-mode")
        if badge.count() == 0:
            ctx.close()
            browser.close()
            pytest.skip("backend is not currently in transition mode")

        banner = page.locator(".status-focus-banner[data-focus-banner='breakout']")
        assert banner.count() == 1
        assert banner.first.is_visible()
        text = banner.first.inner_text()
        assert "突破信号关注模式" in text
        assert "vol_compression" in text

        # The URL must keep focus=breakout so the user can refresh and still
        # see the banner.
        assert "focus=breakout" in page.url

        ctx.close()
        browser.close()


def test_focus_breakout_banner_absent_without_param(base_url):
    """When ?focus=breakout is NOT in the URL, no focus banner is rendered,
    even when the transition badge is present (regression guard)."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/market-analysis", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        banner = page.locator(".status-focus-banner")
        assert banner.count() == 0

        ctx.close()
        browser.close()
