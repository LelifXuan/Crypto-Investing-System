"""Actual per-page guide FAB contracts, replacing the obsolete knowledge cards."""

import pytest
from playwright.sync_api import expect, sync_playwright
from test_analysis_workbench import capture_errors
from test_strategy_operator_commands import install_strategy_fixture
from test_workbench_browser_contract import BASE_URL, capture_workbench

PAGES = [
    ("monitoring-overview", "/monitoring-page"),
    ("btc-derivatives", "/btc-derivatives-page"),
    ("ai-strategy", "/strategy-page"),
]


def reveal_navigation(page):
    opener = page.get_by_role("button", name="打开导航", exact=True)
    if opener.is_visible():
        opener.click()


def navigate_with_sidebar(page, label):
    reveal_navigation(page)
    page.get_by_role("link", name=label, exact=True).click()


@pytest.mark.parametrize("page_id,route", PAGES)
@pytest.mark.parametrize("width,height", [(2560, 1440), (1100, 800), (390, 844)])
def test_guide_fab_content_preference_focus_and_unmount(page_id, route, width, height):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
        )
        install_strategy_fixture(page)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}{route}")
        fab = page.locator(".page-guide-fab")
        expect(fab).to_have_count(1)
        reveal_navigation(page)
        panel_id = fab.get_attribute("aria-controls")
        panel = page.locator(f"#{panel_id}")
        expect(panel).to_be_hidden()
        assert page.get_by_role("region", name="页面使用指南", exact=True).count() == 0
        fab.click()
        expect(fab).to_have_attribute("aria-expanded", "true")
        expect(panel).to_be_visible()
        for name in ("purpose", "walkthrough", "lineage", "caveats"):
            expect(panel.locator(f".knowledge-guide-{name}").first).to_be_visible()
        capture_workbench(page, f"guide-{page_id}-{width}-open")
        fab.click()
        expect(panel).to_be_hidden()
        fab.press("Enter")
        expect(panel).to_be_visible()
        # Mobile Escape first closes the higher-priority navigation drawer.
        page.keyboard.press("Escape")
        if panel.is_visible():
            page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
        if fab.is_visible():
            expect(fab).to_be_focused()
        reveal_navigation(page)
        fab.press("Space")
        expect(panel).to_be_visible()
        page.reload()
        expect(panel).to_be_visible()
        expect(fab).to_have_attribute("aria-expanded", "true")
        # The restored guide is readable without a navigation scrim over its content.
        capture_workbench(page, f"guide-{page_id}-{width}-ready-open")

        # Palette pointer/Tab/Escape must not dismiss the guide underneath.
        page.keyboard.press("Control+k")
        palette = page.get_by_role("dialog", name="工作台命令")
        expect(palette).to_be_visible()
        palette.get_by_role("combobox").click()
        page.keyboard.press("Tab")
        assert palette.evaluate("el => el.contains(document.activeElement)")
        capture_workbench(page, f"guide-{page_id}-{width}-palette")
        page.keyboard.press("Escape")
        expect(palette).to_be_hidden()
        expect(panel).to_be_visible()
        assert page.evaluate("document.body.style.overflow") != "hidden"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        navigate_with_sidebar(page, "知识百科")
        expect(page.locator(".knowledge-hero")).to_be_visible()
        expect(panel).to_have_count(0)
        expect(fab).to_have_count(0)
        page.keyboard.press("Escape")
        assert page.evaluate("document.body.style.overflow") != "hidden"
        navigate_with_sidebar(
            page,
            {
                "monitoring-overview": "监控总览",
                "btc-derivatives": "BTC 衍生品",
                "ai-strategy": "AI 策略",
            }[page_id],
        )
        expect(fab).to_have_count(1)
        expect(panel).to_have_count(1)
        # Sidebar navigation is an explicit outside interaction and closes the
        # guide before leaving the page, so returning starts from its closed state.
        expect(panel).to_be_hidden()
        reveal_navigation(page)
        # Opening navigation is an outside pointer and may already dismiss the guide.
        if fab.get_attribute("aria-expanded") == "true":
            fab.click()
        expect(panel).to_be_hidden()
        page.reload()
        expect(fab).to_have_attribute("aria-expanded", "false")
        expect(panel).to_be_hidden()
        assert errors == []
        browser.close()
