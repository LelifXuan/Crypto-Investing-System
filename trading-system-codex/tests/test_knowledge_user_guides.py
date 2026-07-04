"""Playwright + Node integration tests for the knowledge page user guides."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _backend_up() -> bool:
    """Quick check that uvicorn is up on 8002 (skip test if not)."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", 8002))
        return True
    except (socket.error, socket.timeout):
        return False
    finally:
        s.close()


import pytest


@pytest.fixture
def base_url():
    return os.getenv("BASE_URL", "http://127.0.0.1:8002")


def test_page_guides_section_visible_and_expanded(base_url):
    """knowledge page should expose the 'page-guides' section with default-expanded cards."""
    if not _backend_up():
        pytest.skip("backend not running on :8002")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/knowledge-page", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Section is present (wait for SPA render)
        section = page.locator(".knowledge-section-card").filter(has_text="页面使用指南")
        section.first.wait_for(state="attached", timeout=5000)

        # At least one guide card visible, default-expanded
        guide_cards = page.locator(".knowledge-guide-card")
        guide_cards.first.wait_for(state="attached", timeout=5000)
        assert guide_cards.count() >= 3

        first = guide_cards.first
        assert first.locator(".knowledge-guide-purpose").count() >= 1
        assert first.locator(".knowledge-guide-walkthrough").count() >= 1
        assert first.locator(".knowledge-guide-lineage").count() >= 1
        assert first.locator(".knowledge-guide-caveats").count() >= 1

        ctx.close()
        browser.close()
