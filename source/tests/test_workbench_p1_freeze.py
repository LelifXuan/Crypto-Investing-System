from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def test_p1_inspector_retains_controls_across_notifications(base_url) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 800})
        page.goto(f"{base_url}/knowledge-page")
        result = page.evaluate("""async () => {
          const {createWorkbenchState} = await import('/static/core/workbenchState.js');
          const {mountInspector} = await import('/static/ui/inspector.js');
          const host = document.createElement('aside'); document.body.append(host);
          const state = createWorkbenchState({scopeId: 'test'});
          const ui = mountInspector(host, {state});
          const dto = {id:'a', title:'A', current:{value:'10'}};
          state.select(dto); await Promise.resolve();
          const close = host.querySelector('button'); close.focus();
          const body = host.querySelector('.workbench-inspector-body');
          const value = body.firstElementChild;
          state.select(dto);
          const unchanged = body.firstElementChild === value;
          state.select({...dto, current:{value:'11'}});
          const stable = close === host.querySelector('button') && document.activeElement === close;
          ui.destroy(); state.destroy(); host.remove();
          return {unchanged, stable};
        }""")
        assert result == {"unchanged": True, "stable": True}
        browser.close()


def test_p1_adapter_and_refresh_guards() -> None:
    macro = (ROOT / "app/static/pages/macro_calendar.js").read_text(encoding="utf-8")
    monitoring = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    assert "function bindMacroSelection" not in macro
    assert 'status: "live"' not in macro
    assert "boundRefreshButtons.has(button)" in monitoring
    assert "pageController !== controller" in monitoring
    assert "signal: controller.signal" in monitoring


def test_btc_cold_refresh_abort_cannot_overwrite_next_route(base_url) -> None:
    import json

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        pending = []
        page.route(
            "**/api/v1/btc-derivatives/dashboard?*",
            lambda route: route.fulfill(
                content_type="application/json",
                body=json.dumps({"snapshot_state": "data_insufficient"}),
            ),
        )
        page.route(
            "**/api/v1/btc-derivatives/dashboard/refresh*", lambda route: pending.append(route)
        )
        page.goto(f"{base_url}/btc-derivatives-page")
        page.wait_for_function("document.querySelector('.btc-derivatives-page') !== null")
        page.locator('[data-page-link="knowledge-base"]').click()
        page.locator(".knowledge-hero").wait_for()
        page.wait_for_timeout(400)
        assert page.locator(".knowledge-hero").is_visible()
        assert page.locator(".btc-derivatives-page").count() == 0
        browser.close()
