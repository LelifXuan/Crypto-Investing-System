import pytest
from playwright.sync_api import sync_playwright
from test_workbench_browser_contract import BASE_URL, _btc_payload, _json, _monitoring_payload


def fixture_api(route) -> None:
    url = route.request.url
    if "/dashboard/refresh" in url or "/macro/sync" in url or "/precompute/hint" in url:
        _json(route, {"status": "success"})
    elif "/monitoring/dashboard" in url:
        _json(route, _monitoring_payload())
    elif "/monitoring/macro-overview" in url:
        _json(route, _monitoring_payload()["macro_overview"])
    elif "/btc-derivatives/dashboard" in url:
        _json(route, _btc_payload())
    else:
        route.continue_()


def navigate_with_sidebar(page, label: str) -> None:
    opener = page.get_by_role("button", name="打开导航", exact=True)
    if opener.is_visible():
        opener.click()
    page.get_by_role("link", name=label, exact=True).click()


@pytest.mark.parametrize("width", [2560, 1100, 390])
def test_palette_overlay_keyboard_and_route_scope(width: int) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce")
        page.route("**/api/v1/**", fixture_api)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{BASE_URL}/monitoring-page")
        target = page.locator(".macro-layer-card").first
        target.wait_for()
        target.press("Enter")
        page.keyboard.press("Control+k")
        dialog = page.get_by_role("dialog", name="工作台命令")
        assert dialog.is_visible()
        search = dialog.get_by_role("combobox")
        assert search.evaluate("el => el === document.activeElement")
        assert page.get_by_role("option").count() == 3
        search.fill("does-not-exist")
        assert dialog.get_by_text("没有匹配的命令").is_visible()
        search.press("Escape")
        assert dialog.is_hidden()
        assert page.locator("#monitoring-inspector").is_visible()
        if width <= 1180:
            assert page.evaluate("document.body.style.overflow") == "hidden"
        page.keyboard.press("Escape")
        assert page.locator("#monitoring-inspector").is_hidden()
        for _ in range(20):
            page.keyboard.press("Control+k")
            assert dialog.is_visible()
            page.keyboard.press("Escape")
        page.keyboard.press("Control+k")
        search.press("Escape")
        navigate_with_sidebar(page, "BTC 衍生品")
        page.wait_for_url("**/btc-derivatives-page")
        page.locator("#btc-open-summary-evidence").wait_for()
        page.keyboard.press("Control+k")
        search.fill("刷新")
        assert page.get_by_role("option").count() == 1
        assert "BTC" in page.get_by_role("option").inner_text()
        search.press("Escape")
        navigate_with_sidebar(page, "监控总览")
        page.wait_for_url("**/monitoring-page")
        target.wait_for()
        page.keyboard.press("Control+k")
        assert page.get_by_role("option").count() == 3
        search.press("Escape")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
        browser.close()


def test_pages_have_no_visible_palette_entry_point() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.goto(f"{BASE_URL}/knowledge-page")
        page.locator(".knowledge-hero").wait_for()
        assert page.locator(".workbench-command-trigger").count() == 0
        page.keyboard.press("Control+k")
        assert page.get_by_role("dialog", name="工作台命令").is_hidden()
        browser.close()


def test_palette_preserves_underlying_strategy_detail() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        page.route("**/api/v1/**", fixture_api)
        page.goto(f"{BASE_URL}/monitoring-page")
        page.locator(".macro-layer-card").first.wait_for()
        page.evaluate("""async () => {
          const {openDetailPanel} = await import('/static/pages/strategy/renderDetailPanel.js');
          openDetailPanel('btc-usdt-perp', '4h', () => new Promise(() => {}), () => {});
        }""")
        page.locator("#strategy-detail-close").focus()
        assert (
            page.locator("#strategy-detail-panel").evaluate("el => getComputedStyle(el).position")
            == "fixed"
        )
        page.keyboard.press("Control+k")
        page.get_by_role("combobox").click()
        assert page.locator("#strategy-detail-panel").is_visible()
        page.keyboard.press("Escape")
        assert page.locator("#strategy-detail-panel").is_visible()
        assert page.locator("#strategy-detail-close").evaluate(
            "el => el === document.activeElement"
        )
        page.keyboard.press("Escape")
        assert page.locator("#strategy-detail-panel").count() == 0
        assert page.evaluate("document.body.style.overflow") != "hidden"
        browser.close()


def test_palette_over_navigation_drawer_and_ime() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.route("**/api/v1/**", fixture_api)
        page.goto(f"{BASE_URL}/monitoring-page")
        page.locator(".macro-layer-card").first.wait_for()
        page.locator('[data-shell-action="open-nav"]').click()
        page.keyboard.press("Control+k")
        palette = page.get_by_role("dialog", name="工作台命令")
        search = palette.get_by_role("combobox")
        search.fill("刷新")
        search.dispatch_event("keydown", {"key": "Enter", "isComposing": True})
        assert palette.is_visible() and "/monitoring-page" in page.url
        search.press("Shift+Tab")
        assert palette.evaluate("el => el.contains(document.activeElement)")
        search.press("Escape")
        assert page.locator("body").evaluate("el => el.classList.contains('is-nav-open')")
        assert page.evaluate("document.body.style.overflow") == "hidden"
        page.keyboard.press("Escape")
        assert not page.locator("body").evaluate("el => el.classList.contains('is-nav-open')")
        assert page.evaluate("document.body.style.overflow") != "hidden"
        browser.close()
