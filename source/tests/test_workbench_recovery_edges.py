import json

import pytest
from playwright.sync_api import sync_playwright
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _btc_payload, _json, _monitoring_payload


@pytest.mark.parametrize("outcome", ["success", "failed", "leave"])
def test_cold_url_waits_for_job_and_cannot_update_after_navigation(outcome):
    ready = False
    job_requests = []

    def route_api(route):
        url = route.request.url
        if "/btc-derivatives/dashboard/refresh" in url:
            _json(route, {"job_id": "fixture-job", "status": "queued", "poll_after_ms": 250})
        elif "/btc-derivatives/dashboard" in url:
            _json(route, _btc_payload() if ready else {"snapshot_state": "data_insufficient"})
        elif "fixture-job" in url:
            job_requests.append(route)
        else:
            fixture_api(route)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/btc-derivatives-page?inspect=btc:metric:funding")
        for _ in range(40):
            if job_requests:
                break
            page.wait_for_timeout(50)
        assert job_requests
        assert "inspect=" in page.url
        assert not page.locator("#btc-workbench-inspector").is_visible()
        if outcome == "leave":
            page.locator('[data-page-link="knowledge-base"]').click()
            page.locator(".knowledge-hero").wait_for()
            _json(job_requests.pop(), {"status": "success"})
            page.wait_for_timeout(400)
            assert page.locator(".knowledge-hero").is_visible()
            assert page.locator(".workbench-inspector").count() == 0
            assert "inspect=" not in page.url
        else:
            ready = outcome == "success"
            _json(job_requests.pop(), {"status": outcome})
            if ready:
                page.locator("#btc-workbench-inspector").wait_for()
                assert "inspect=" in page.url
            else:
                page.locator(".workbench-recovery-note").wait_for()
                assert "inspect=" not in page.url
        assert not errors
        browser.close()


def test_monitoring_lkg_restores_while_network_is_pending_then_fails():
    pending = []
    failed = False

    def route_api(route):
        if "/monitoring/dashboard" in route.request.url:
            if failed:
                route.abort("failed")
            else:
                pending.append(route)
        elif "/monitoring/macro-overview" in route.request.url:
            _json(route, {})
        else:
            fixture_api(route)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        saved = json.dumps(
            {"instrumentId": "btc-usdt-perp", "timeframe": "1d", "bundle": _monitoring_payload()}
        )
        page.add_init_script(
            "sessionStorage.setItem('monitoring.dashboard.lastSnapshot.v1', "
            + json.dumps(saved)
            + ");"
        )
        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/monitoring-page?inspect=monitoring:macro")
        page.locator("#monitoring-inspector").wait_for()
        assert "62" in page.locator("#monitoring-inspector").inner_text()
        for _ in range(40):
            if pending:
                break
            page.wait_for_timeout(50)
        assert pending
        failed = True
        pending.pop().abort("failed")
        page.get_by_text("监控快照读取失败，已保留上一份可用快照。").wait_for()
        assert page.locator("#monitoring-inspector").is_visible()
        assert "inspect=" in page.url
        browser.close()


def test_chart_selection_refresh_resize_and_context_reset():
    reads = 0

    def route_api(route):
        nonlocal reads
        if "/btc-derivatives/dashboard/refresh" in route.request.url:
            _json(route, {"status": "success"})
        elif "/btc-derivatives/dashboard" in route.request.url:
            reads += 1
            _json(route, _btc_payload(funding=0.01 * reads))
        else:
            fixture_api(route)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/btc-derivatives-page")
        canvas = page.locator('[data-chart-id="leverage_pressure_timeline"] canvas').first
        canvas.wait_for()
        page.wait_for_function("Object.keys(Chart.instances).length > 0")
        canvas.evaluate("""el => {
          const chart = Chart.getChart(el);
          const index = chart.data.datasets.findIndex(d => d.label === 'Funding Z');
          chart.options.onClick({}, [{datasetIndex:index,index:2}], chart);
        }""")
        inspector = page.locator("#btc-workbench-inspector")
        inspector.wait_for()
        page.locator(".workbench-inspector-pin").click()
        page.locator("#btc-refresh").click()
        page.wait_for_function(
            "document.querySelector('.workbench-inspector-current').textContent.includes('0.02')"
        )
        assert page.locator(".workbench-inspector-pin").get_attribute("aria-pressed") == "true"
        before = canvas.bounding_box()["width"]
        page.get_by_role("separator").press("End")
        page.wait_for_function(
            """before => {
          const el = document.querySelector('[data-chart-id="leverage_pressure_timeline"] canvas');
          const chart = Chart.getChart(el);
          return el.getBoundingClientRect().width < before && chart.width === el.clientWidth;
        }""",
            arg=before,
        )
        page.locator('[data-dropdown-id="btc-window"]').click()
        page.get_by_role("option", name="短期 30D", exact=True).click()
        page.wait_for_function("!new URL(location.href).searchParams.has('inspect')")
        assert inspector.is_hidden()
        browser.close()


def test_btc_failed_refresh_retains_committed_lkg_and_pin():
    def route_api(route):
        if "/btc-derivatives/dashboard/refresh" in route.request.url:
            _json(route, {"job_id": "failed-refresh", "status": "failed"})
        else:
            fixture_api(route)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/btc-derivatives-page?inspect=btc:evidence:funding")
        inspector = page.locator("#btc-workbench-inspector")
        inspector.wait_for()
        page.locator(".workbench-inspector-pin").click()
        title = inspector.locator("h2").inner_text()
        page.locator("#btc-refresh").click()
        page.locator(".btc-operation-status").wait_for()
        assert inspector.is_visible()
        assert inspector.locator("h2").inner_text() == title
        assert page.locator(".workbench-inspector-pin").get_attribute("aria-pressed") == "true"
        assert "inspect=" in page.url
        browser.close()
