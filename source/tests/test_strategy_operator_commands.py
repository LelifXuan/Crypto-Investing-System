"""H4 keeps the existing detail panel and exposes only four scoped actions."""

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_analysis_workbench import capture_errors
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _json, capture_workbench


def install_strategy_fixture(page, calls=None):
    calls = [] if calls is None else calls
    snapshot_key = "operator-fixture:btc-usdt-perp"

    def fixture(route):
        url = route.request.url
        if "/strategy/scan" in url:
            calls.append(url)
            _json(route, {
                "matrix": [{
                    "instrument_id": "btc-usdt-perp",
                    "instrument_code": "BTC",
                    "timeframe": "1w",
                    "cache_state": "fresh",
                    "qualified": False,
                    "direction": "WAIT",
                    "qualification_reasons": ["NO_DIRECTION"],
                    "source_snapshot_key": snapshot_key,
                }],
                "ranked": [],
                "cache_meta": {"source": "cache"},
            })
        elif "/strategy/prewarm" in url:
            _json(route, {"status": "queued"})
        elif "/strategy/unified" in url:
            _json(route, {
                "snapshot_key": snapshot_key,
                "cache_state": "fresh",
                "status": "ready",
                "timeframe_stack": [{
                    "timeframe": "1w", "direction": "NEUTRAL",
                    "long_score": 52, "short_score": 50,
                    "evidence": ["多空分差不足，当前没有交易方向。"],
                }],
                "opportunity_decisions": {"1w": {
                    "opportunity_id": "btc-usdt-perp:1w",
                    "trade_timeframe": "1w",
                    "execution_timeframe": "1d",
                    "side": "NONE",
                    "status": "NO_DIRECTION",
                    "permission": "observe",
                    "primary_reason": {"message": "周线暂无明确方向。"},
                    "setup_evidence": ["多空分差不足，当前没有交易方向。"],
                }},
            })
        else:
            fixture_api(route)

    page.route("**/api/v1/**", fixture)
    return calls


def test_strategy_scope_contract():
    source = (Path(__file__).resolve().parents[1] / "app/static/pages/strategy/index.js").read_text(
        encoding="utf-8"
    )
    for key in ("refresh-scan", "focus-matrix", "focus-ranked", "close-detail"):
        assert f'id: "strategy:{key}"' in source
    assert "commandDisposers.forEach((dispose) => dispose())" in source
    assert "commandLifetime.abort()" in source
    assert "mountInspector" not in source
    assert "mountWorkbenchUrlState" not in source
    assert '"click", refreshScan' in source


@pytest.mark.parametrize("width,height", [(2560, 1440), (1100, 800), (390, 844)])
def test_strategy_commands_focus_refresh_detail_and_scope(width, height):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
        )
        calls = install_strategy_fixture(page)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/strategy-page")
        expect(page.locator(".scan-cell-btn").first).to_be_visible()

        def command(label):
            page.keyboard.press("Control+k")
            page.get_by_role("combobox").fill(label)
            page.keyboard.press("Enter")

        command("聚焦策略矩阵")
        expect(page.locator("#strategy-scan-matrix-section")).to_be_focused()
        command("聚焦策略排名")
        expect(page.locator("#strategy-scan-ranked-section")).to_be_focused()
        count = len(calls)
        command("刷新策略扫描")
        expect(page.locator(".scan-cell-btn").first).to_be_visible()
        assert len(calls) == count + 1
        page.locator('.scan-cell-btn[data-instrument="btc-usdt-perp"][data-timeframe="1w"]').click()
        detail = page.locator("#strategy-detail-panel")
        expect(detail).to_be_visible()
        expect(page.locator("#strategy-detail-title")).to_contain_text("无交易机会")
        expect(detail).to_have_attribute("role", "dialog")
        expect(detail).to_have_attribute("aria-modal", "true")
        page.keyboard.press("Control+k")
        expect(page.get_by_role("option")).to_have_count(4)
        capture_workbench(page, f"strategy-detail-palette-{width}")
        page.keyboard.press("Escape")
        expect(detail).to_be_visible()
        assert page.evaluate("document.body.style.overflow") == "hidden"
        command("关闭策略详情")
        expect(detail).to_have_count(0)
        assert page.evaluate("document.body.style.overflow") != "hidden"
        for _ in range(20):
            page.keyboard.press("Control+k")
            expect(page.get_by_role("option")).to_have_count(4)
            page.keyboard.press("Escape")
        opener = page.get_by_role("button", name="打开导航", exact=True)
        if opener.is_visible():
            opener.click()
        page.get_by_role("link", name="监控总览", exact=True).click()
        expect(page.locator("#monitoring-topbar")).to_be_visible()
        expect(page.locator("#monitoring-context-rail")).to_have_count(0)
        page.keyboard.press("Control+k")
        expect(page.get_by_role("option")).to_have_count(3)
        page.get_by_role("combobox").fill("strategy:")
        expect(page.get_by_role("option")).to_have_count(0)
        page.keyboard.press("Escape")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
        browser.close()
