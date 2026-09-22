"""Prove live quote delivery independently of the slow analysis snapshot."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from test_analysis_workbench import analysis_payload
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL


def install_quotes(page, state):
    def route_api(route):
        url = route.request.url
        if "/analysis/bundle" in url:
            payload = analysis_payload(62)
            payload["mark"] = {
                "mark_price": "77.21",
                "ts_event": (datetime.now(UTC) - timedelta(days=6)).isoformat(),
            }
            route.fulfill(json=payload)
        elif "/marks/latest" in url:
            state.setdefault("requests", []).append(url)
            if state.get("fail"):
                route.fulfill(status=503, json={"detail": "quote feed unavailable"})
            else:
                iid = parse_qs(urlparse(url).query)["instrument_id"][0]
                route.fulfill(json={
                    "mark_price": "103.55" if iid == "btc-usdt-perp" else "93.89",
                    "ts_event": datetime.now(UTC).isoformat(), "source": "live:test",
                })
        else:
            fixture_api(route)
    page.route("**/api/v1/**", route_api)


# The technical-analysis page is registered as /indicators-page in
# app/web/router.py (page_id = "market-analysis"). The original test
# referenced "/analysis-page", which does not exist — the result was a
# 404 before any DOM was rendered, masking every assertion. This constant
# keeps the route lookup in one place so a future rename only needs a
# single edit.
ANALYSIS_PAGE_URL = f"{BASE_URL}/indicators-page"


def test_quote_arrives_before_analysis_and_old_snapshot_cannot_overwrite_it():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        state = {}
        install_quotes(page, state)
        page.add_init_script("""{
          const fetch = window.fetch.bind(window);
          const gate = new Promise(resolve => window.releaseAnalysis = resolve);
          window.fetch = (input, init) => String(input?.url || input).includes('/analysis/bundle')
            ? gate.then(() => fetch(input, init)) : fetch(input, init);
        }""")
        page.goto(ANALYSIS_PAGE_URL)
        expect(page.locator("#analysis-mark-price")).to_have_text("103.55", timeout=3000)
        assert "prefer_live=true" in state["requests"][0]
        assert "persist_live=false" in state["requests"][0]
        page.evaluate("window.releaseAnalysis()")
        expect(page.locator("#analysis-mark-close")).not_to_have_text("-")
        expect(page.locator("#analysis-mark-price")).to_have_text("103.55")
        page.locator('.instrument-pill:not([data-instrument-id="btc-usdt-perp"])').first.click()
        expect(page.locator("#analysis-mark-price")).to_have_text("93.89", timeout=4000)
        expect(page.locator("#analysis-mark-freshness")).to_have_text("实时")
        browser.close()


def test_failed_live_feed_marks_old_price_and_recovers_on_periodic_refresh():
    """Live feed returning 503 + a 6-day-old bundle mark is the exact bug
    that motivated the price-lag fix (see git log ba60a99..). Pre-fix
    behaviour was to render the stale bundle price for one frame and keep
    a "实时" chip; post-fix the bundle mark is rejected as too old and the
    user sees an empty placeholder until live recovers.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        state = {"fail": True}
        install_quotes(page, state)
        page.goto(ANALYSIS_PAGE_URL)
        # Post-fix: bundle mark older than BUNDLE_MARK_STALE_AFTER_MS (30s)
        # must NOT be rendered as the current price. The card stays empty
        # ("—") and the freshness chip degrades to "报价过期" instead of
        # falsely displaying 77.21 as if it were live.
        expect(page.locator("#analysis-mark-price")).to_have_text("—")
        expect(page.locator("#analysis-mark-freshness")).to_have_text("报价过期")
        expect(page.locator("#analysis-mark-next")).to_contain_text("重试", timeout=12000)
        state["fail"] = False
        expect(page.locator("#analysis-mark-price")).to_have_text("103.55", timeout=20000)
        expect(page.locator("#analysis-mark-freshness")).to_have_text("实时")
        page.locator('[data-page-link="knowledge-base"]').click()
        page.wait_for_url("**/knowledge-page")
        count = len(state["requests"])
        page.wait_for_timeout(16000)
        assert len(state["requests"]) == count
        browser.close()
