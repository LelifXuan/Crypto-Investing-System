from datetime import datetime, timezone

import pytest
from playwright.sync_api import sync_playwright
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _json, capture_workbench


@pytest.mark.parametrize("width", [2560, 1100, 800, 390])
def test_pin_preview_and_clear(width: int) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.route("**/api/v1/**", fixture_api)
        page.goto(f"{BASE_URL}/monitoring-page")
        target = page.locator(".macro-layer-card").first
        target.press("Enter")
        pin = page.locator(".workbench-inspector-pin")
        pin.click()
        assert pin.get_attribute("aria-pressed") == "true"
        title = page.locator("#monitoring-inspector h2").inner_text()
        if width > 1180:
            other = page.locator('[data-workbench-id="monitoring:macro"]')
            other.hover()
            assert page.locator("#monitoring-inspector h2").inner_text() == title
            assert target.get_attribute("data-workbench-related") == "selected"
            other.click()
            assert pin.get_attribute("aria-pressed") == "true"
        capture_workbench(page, f"operator-pin-{width}")
        page.keyboard.press("Escape")
        assert page.locator("#monitoring-inspector").is_hidden()
        target.press("Enter")
        assert (
            page.get_by_role("button", name="固定当前详情", exact=True).get_attribute(
                "aria-pressed"
            )
            == "false"
        )
        browser.close()


def test_url_restore_preview_popstate_and_invalid() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.route("**/api/v1/**", fixture_api)
        page.goto(f"{BASE_URL}/monitoring-page?keep=yes&inspect=monitoring:macro#context")
        inspector = page.locator("#monitoring-inspector")
        inspector.wait_for()
        assert "keep=yes" in page.url and page.url.endswith("#context")
        page.locator(".macro-layer-card").first.hover()
        assert (
            page.evaluate("new URL(location.href).searchParams.get('inspect')")
            == "monitoring:macro"
        )
        page.keyboard.press("Escape")
        assert "inspect=" not in page.url
        page.evaluate(
            "history.pushState({...history.state, custom: 42}, '', "
            "'?keep=yes&inspect=monitoring:macro#context'); "
            "dispatchEvent(new PopStateEvent('popstate', {state:history.state}))"
        )
        inspector.wait_for()
        assert page.evaluate("history.state.custom") == 42
        page.evaluate(
            "history.pushState(history.state, '', '?inspect=missing'); "
            "dispatchEvent(new PopStateEvent('popstate', {state:history.state}))"
        )
        assert inspector.is_hidden()
        assert "inspect=" not in page.url
        assert page.locator(".workbench-recovery-note").is_visible()
        browser.close()


@pytest.mark.parametrize(
    "route_path,object_id,selector",
    [
        ("btc-derivatives-page", "btc:metric:funding", "#btc-workbench-inspector"),
        ("market-events-page", "events:item:url-event", "#events-inspector"),
        ("macro-calendar-page", "macro:day:current", "#macro-inspector"),
    ],
)
def test_other_pages_restore_current_registry(route_path, object_id, selector) -> None:
    from urllib.parse import quote

    macro_day = datetime.now(timezone.utc).date().isoformat()
    if route_path == "macro-calendar-page":
        object_id = f"macro:day:{macro_day}"

    def route_api(route):
        url = route.request.url
        if "/market-events/supply-event-calendar" in url:
            _json(route, {"items": [], "coverage": []})
        elif "/marketevents" in url:
            _json(
                route,
                [
                    {
                        "event_id": "url-event",
                        "title": "URL event",
                        "summary": "Real fixture summary",
                        "source": "fixture",
                        "category": "macro",
                        "ts_event": "2026-08-29T02:00:00Z",
                        "instrument_ids": ["btc-usdt-perp"],
                        "payload_json": {},
                    }
                ],
            )
        elif "/macro/calendar" in url:
            _json(
                route,
                [
                    {
                        "event_id": "macro-url",
                        "event_key": "us_cpi",
                        "title": "美国 CPI",
                            "scheduled_at": f"{macro_day}T12:30:00Z",
                        "status": "released",
                        "actual_value_num": 2.8,
                        "consensus_value_num": 2.9,
                    }
                ],
            )
        else:
            fixture_api(route)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/{route_path}?inspect={quote(object_id)}")
        page.locator(selector).wait_for()
        assert page.evaluate("new URL(location.href).searchParams.get('inspect')") == object_id
        page.locator(".workbench-inspector-pin").click()
        assert page.locator(".workbench-inspector-pin").get_attribute("aria-pressed") == "true"
        page.keyboard.press("Escape")
        assert "inspect=" not in page.url
        browser.close()


def test_resize_keyboard_persistence_and_route_abort() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.route("**/api/v1/**", fixture_api)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{BASE_URL}/btc-derivatives-page")
        page.locator(".btc-evidence-tile").first.press("Enter")
        handle = page.get_by_role("separator", name="调整详情宽度")
        handle.press("Home")
        assert handle.get_attribute("aria-valuenow") == "320"
        capture_workbench(page, "resize-min")
        handle.press("ArrowLeft")
        assert handle.get_attribute("aria-valuenow") == "328"
        handle.press("Shift+ArrowLeft")
        assert handle.get_attribute("aria-valuenow") == "360"
        handle.press("End")
        assert handle.get_attribute("aria-valuenow") == "520"
        capture_workbench(page, "resize-max")
        page.set_viewport_size({"width": 1200, "height": 900})
        page.wait_for_function(
            "document.querySelector('[role=separator]').getAttribute('aria-valuenow') === '504'"
        )
        assert page.evaluate("localStorage.getItem('cis.workbench.inspector.width.v1')") == "520"
        page.set_viewport_size({"width": 1100, "height": 800})
        handle.wait_for(state="hidden")
        page.set_viewport_size({"width": 2560, "height": 1440})
        handle.wait_for()
        page.wait_for_function(
            "document.querySelector('[role=separator]').getAttribute('aria-valuenow') === '520'"
        )
        box = handle.bounding_box()
        page.mouse.move(box["x"] + 4, box["y"] + 20)
        page.mouse.down()
        page.mouse.move(box["x"] + 84, box["y"] + 20)
        page.wait_for_timeout(100)
        assert int(handle.get_attribute("aria-valuenow")) == 440
        page.get_by_role("link", name="监控总览", exact=True).dispatch_event("click")
        page.wait_for_url("**/monitoring-page", wait_until="commit")
        page.locator(".macro-layer-card").first.press("Enter")
        page.mouse.up()
        assert page.get_by_role("separator").get_attribute("aria-valuenow") == "520"
        assert not errors
        browser.close()
