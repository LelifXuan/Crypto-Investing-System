import pytest
from playwright.sync_api import sync_playwright
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _json, capture_workbench

VIEWPORTS = [
    (2560, 1440),
    (1500, 900),
    (1440, 900),
    (1280, 720),
    (1180, 800),
    (1100, 800),
    (900, 900),
    (800, 900),
    (768, 1024),
    (768, 900),
    (390, 844),
    (2560, 1600),
]
PAGES = [
    ("monitoring", "monitoring-page", ".macro-layer-card", "#monitoring-inspector"),
    ("btc", "btc-derivatives-page", "#btc-open-summary-evidence", "#btc-workbench-inspector"),
    ("macro", "macro-calendar-page", "tr[data-workbench-selectable]", "#macro-inspector"),
]


def four_page_fixture(route):
    url = route.request.url
    if "/market-events/supply-event-calendar" in url:
        _json(route, {"items": [], "coverage": []})
    elif "/market-events/sync" in url:
        _json(route, {"status": "success"})
    elif "/marketevents" in url:
        _json(
            route,
            [
                {
                    "event_id": "acceptance-event",
                    "category": "macro",
                    "title": "宏观数据发布",
                    "summary": "已发布事件的来源与关联品种。",
                    "source": "fixture",
                    "source_status": "stale",
                    "ts_event": "2026-08-29T02:00:00Z",
                    "payload_json": {},
                    "instrument_ids": ["btc-usdt-perp"],
                },
                {
                    "event_id": "acceptance-frozen-event",
                    "category": "exchange",
                    "title": "已冻结的交易所事件",
                    "summary": "冻结状态仍使用一致的 hover 反馈。",
                    "source": "fixture",
                    "ts_event": "2026-08-29T01:00:00Z",
                    "payload_json": {},
                    "is_frozen": True,
                },
            ],
        )
    elif "/macro/calendar" in url:
        _json(
            route,
            [
                {
                    "event_id": "acceptance-cpi",
                    "event_key": "us_cpi",
                    "title": "美国 CPI",
                    "scheduled_at": "2026-08-29T12:30:00Z",
                    "status": "released",
                    "actual_value_num": 2.8,
                    "consensus_value_num": 2.9,
                    "previous_value_num": 3.0,
                    "surprise_num": -0.1,
                }
            ],
        )
    else:
        fixture_api(route)


@pytest.mark.parametrize("size", VIEWPORTS)
@pytest.mark.parametrize("name,route_path,target_selector,inspector_selector", PAGES)
def test_four_page_viewports_and_layer_states(
    size, name, route_path, target_selector, inspector_selector
):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": size[0], "height": size[1]}, reduced_motion="reduce"
        )
        problems = []
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.on("console", lambda msg: problems.append(msg.text) if msg.type == "error" else None)
        page.on(
            "response",
            lambda response: (
                problems.append(str(response.status)) if response.status >= 400 else None
            ),
        )
        page.route("**/api/v1/**", four_page_fixture)
        page.goto(f"{BASE_URL}/{route_path}")
        target = page.locator(target_selector).first
        target.wait_for()
        if page.locator(".page-guide-panel").count():
            assert page.locator(".page-guide-panel").evaluate(
                "el => el.hidden && getComputedStyle(el).opacity === '0'"
            )
        prefix = f"{name}-{size[0]}x{size[1]}"
        capture_workbench(page, prefix + "-closed")
        target.press("Enter")
        inspector = page.locator(inspector_selector)
        inspector.wait_for()
        assert inspector.get_attribute("role") == ("dialog" if size[0] <= 1180 else "complementary")
        capture_workbench(page, prefix + "-open-linked")
        page.locator(".workbench-inspector-pin").click()
        assert page.locator(".workbench-inspector-pin").get_attribute("aria-pressed") == "true"
        capture_workbench(page, prefix + "-pinned")
        page.keyboard.press("Control+k")
        palette = page.get_by_role("dialog", name="工作台命令")
        assert palette.is_visible()
        capture_workbench(page, prefix + "-palette")
        page.keyboard.press("Escape")
        assert inspector.is_visible()
        page.keyboard.press("Escape")
        assert inspector.is_hidden()
        assert page.evaluate("document.body.style.overflow") != "hidden"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not problems
        browser.close()


@pytest.mark.parametrize("width", [2560, 390])
def test_market_events_feed_uses_full_width_and_uniform_hover(width):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1440})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", four_page_fixture)
        page.goto(f"{BASE_URL}/market-events-page")
        cards = page.locator(".event-feed-item")
        cards.first.wait_for()
        assert cards.count() == 2
        assert page.locator("#events-inspector").count() == 0
        assert page.locator(".event-feed-related").count() == 1
        feed = page.locator(".events-feed-shell").bounding_box()
        layout = page.locator(".events-workbench-layout").bounding_box()
        assert feed and layout and feed["width"] >= layout["width"] - 2
        colors = []
        for card in (cards.first, cards.nth(1)):
            card.hover()
            colors.append(card.evaluate("el => getComputedStyle(el).backgroundColor"))
        assert colors[0] == colors[1]
        assert not errors
        browser.close()


@pytest.mark.parametrize("name,route_path,target_selector,inspector_selector", PAGES)
def test_rapid_page_commands_selection_and_unload(
    name, route_path, target_selector, inspector_selector
):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", four_page_fixture)
        page.goto(f"{BASE_URL}/{route_path}")
        page.locator(target_selector).first.wait_for()
        for _ in range(10):
            page.locator(target_selector).first.press("Space")
            page.keyboard.press("Control+k")
            search = page.get_by_role("dialog", name="工作台命令").get_by_role("combobox")
            search.fill("更新" if name == "macro" else "刷新")
            search.press("Enter")
            if page.get_by_role("dialog", name="工作台命令").is_visible():
                # An in-flight command can become enabled between keydown and
                # this read. Close the still-open palette before the next loop.
                page.keyboard.press("Escape")
            page.locator(target_selector).first.wait_for()
        nav_opener = page.get_by_role("button", name="打开导航", exact=True)
        if nav_opener.is_visible():
            nav_opener.click()
        page.get_by_role("link", name="知识百科", exact=True).click()
        page.locator(".knowledge-hero").wait_for()
        assert page.locator(inspector_selector).count() == 0
        assert "inspect=" not in page.url
        assert page.evaluate("document.body.style.overflow") != "hidden"
        assert not errors
        browser.close()
