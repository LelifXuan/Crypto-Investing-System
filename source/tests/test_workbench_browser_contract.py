from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Error as PlaywrightError

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")


def capture_workbench(page, name: str) -> None:
    if destination := os.getenv("WORKBENCH_SCREENSHOT_DIR"):
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        page.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})")
        page.evaluate("""async () => {
          await document.fonts.ready;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }""")
        # Chromium can reject a capture while a just-mounted page changes its
        # document bounds. Retry that CDP capture error only, never assertions,
        # page errors or navigation failures. Persistent capture failure fails.
        for attempt in range(3):
            try:
                data = page.screenshot(full_page=True)
                (directory / f"{name}.png").write_bytes(data)
                break
            except PlaywrightError as error:
                if "Unable to capture screenshot" not in str(error) or attempt == 2:
                    raise
                page.wait_for_timeout(100 * (attempt + 1))


def _backend_running() -> bool:
    parsed = urlparse(BASE_URL)
    try:
        address = (parsed.hostname or "127.0.0.1", parsed.port or 80)
        with socket.create_connection(address, timeout=0.25):
            return True
    except OSError:
        return False


def _monitoring_payload(*, score: int = 62, include_layer: bool = True) -> dict:
    layers = []
    indicators = []
    if include_layer:
        layers = [
            {
                "layer_key": "rates_policy",
                "label_cn": "利率与政策",
                "score": score,
                "contribution": 8.5,
                "effective_count": 1,
                "total_count": 1,
            }
        ]
        indicators = [
            {
                "indicator_key": "fed_funds_rate",
                "display_label": "联邦基金利率",
                "layer_key": "rates_policy",
                "layer_label": "利率与政策",
                "value_num": 4.25,
                "unit": "%",
                "status": "ok",
                "direction_label": "中性偏空",
                "source_provider": "FRED",
                "observation_ts": "2026-08-29T02:00:00Z",
            }
        ]
    macro = {
        "total_score": score,
        "score_band": "中性偏多",
        "confidence": "medium",
        "layers": layers,
        "indicators": indicators,
    }
    return {
        "status": "ok",
        "status_message": "监控快照可用",
        "updated_at": "2026-08-29T02:00:00Z",
        "macro_overview": macro,
        "terminal_summary": {
            "confidence": 68,
            "regime": "中性偏多",
            "headline": "宏观与技术输入保持温和一致。",
            "module_scores": {
                "macro": {"score": score, "state": "中性偏多", "impact": "bullish"},
                "technical_trend": {"score": 55, "state": "温和上行", "impact": "bullish"},
                "momentum_volume": {"score": 50, "state": "中性", "impact": "neutral"},
                "volatility": {"score": 48, "state": "正常", "impact": "neutral"},
                "structure": {"score": 52, "state": "区间", "impact": "neutral"},
                "event_risk": {"score": 40, "state": "可控", "impact": "neutral"},
            },
        },
        "source_status": {
            "gateio": {"status": "online", "updated_at": "2026-08-29T02:00:00Z"},
            "fred": {"status": "online", "updated_at": "2026-08-29T02:00:00Z"},
            "market_events": {"status": "cached", "updated_at": "2026-08-29T01:55:00Z"},
            "ashare_etf": {"status": "online", "updated_at": "2026-08-29T02:00:00Z"},
        },
    }


def _btc_payload(*, funding: float = 0.01) -> dict:
    chart = {
        "status": "ok",
        "title": "杠杆压力时间线",
        "type": "line",
        "labels": ["2026-08-27T00:00:00Z", "2026-08-28T00:00:00Z", "2026-08-29T00:00:00Z"],
        "datasets": [
            {"label": "BTC 价格", "data": [111000, 112000, 113000], "unit": "USD"},
            {"label": "Funding Z", "data": [-0.2, 0.1, funding], "unit": "z"},
            {"label": "聚合 OI", "data": [28.1, 28.4, 28.8], "unit": "B USD"},
        ],
        "metadata": {"data_points": 3, "actual_window": "90D", "providers": ["Gate.io"]},
    }
    return {
        "snapshot_state": "live",
        "data_timestamp": "2026-08-29T02:00:00Z",
        "selection": {"window": "90D", "maturity_bucket": "60D", "strike_range_pct": "30"},
        "source_status": [
            {"venue": "Gate.io", "status": "ok", "updated_at": "2026-08-29T02:00:00Z"},
            {"venue": "Deribit", "status": "degraded", "updated_at": "2026-08-29T01:55:00Z"},
        ],
        "joint_analysis": {
            "confidence": "medium",
            "range_state": "RANGE",
            "inference_blocks": [
                {
                    "id": "futures",
                    "tone": "neutral",
                    "confidence": "medium",
                    "conclusion": "杠杆压力处于中性区间",
                    "basis": ["Funding 与 OI 未形成单边共振"],
                    "implication": "维持区间观察。",
                }
            ],
        },
        "cards": [
            {
                "id": "market_state",
                "label": "当前衍生品状态",
                "state": "neutral",
                "confidence": "medium",
                "conclusion": "杠杆压力处于中性区间",
                "basis": ["Funding 与 OI 未形成单边共振"],
                "implication": "维持区间观察。",
            },
            {
                "id": "primary_risk",
                "label": "主要风险",
                "state": "neutral",
                "confidence": "medium",
                "conclusion": "暂未形成单边拥挤",
                "basis": ["OI 温和变化"],
                "implication": "等待结构确认。",
            },
            {
                "id": "strategy_implication",
                "label": "策略含义",
                "state": "neutral",
                "confidence": "medium",
                "conclusion": "有限风险保护优先",
                "basis": ["保护成本可控"],
                "implication": "不扩大裸露杠杆。",
            },
        ],
        "indicator_judgements": [
            {
                "indicator_key": "funding_rate_zscore",
                "label": "Funding Z",
                "value_num": funding,
                "signal_state": "neutral",
                "data_status": "ready",
                "reason": "资金费率未进入拥挤区",
            }
        ],
        "futures": {"charts": {"leverage_pressure_timeline": chart}, "rows": []},
        "options": {"charts": {}, "maturity_ladder": [], "standard_expiries": []},
        "chart_layout": {
            "sections": [
                {"id": "summary", "title": "杠杆压力", "charts": ["leverage_pressure_timeline"]}
            ],
            "cards": {"leverage_pressure_timeline": {"span": 12}},
        },
        "hedge_context": {"spot_price": 113000, "iv_state": "normal", "liquidity_state": "usable"},
    }


def _json(route, payload: dict) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.skipif(not _backend_running(), reason="browser backend not running")
def test_monitoring_workbench_keyboard_refresh_and_route_cleanup() -> None:
    from playwright.sync_api import sync_playwright

    dashboard_reads = 0
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 2560, "height": 1440}, reduced_motion="reduce"
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_api(route) -> None:
            nonlocal dashboard_reads
            url = route.request.url
            if (
                "/monitoring/dashboard/refresh" in url
                or "/macro/sync" in url
                or "/precompute/hint" in url
            ):
                _json(route, {"status": "success"})
            elif "/monitoring/dashboard" in url:
                dashboard_reads += 1
                _json(
                    route,
                    _monitoring_payload(
                        score=62 + dashboard_reads, include_layer=dashboard_reads < 3
                    ),
                )
            elif "/monitoring/macro-overview" in url:
                _json(
                    route,
                    _monitoring_payload(
                        score=62 + dashboard_reads, include_layer=dashboard_reads < 3
                    )["macro_overview"],
                )
            else:
                route.continue_()

        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/monitoring-page", wait_until="domcontentloaded")
        target = page.locator(".macro-layer-card").first
        target.wait_for(state="visible")
        target.hover()
        assert page.locator("[data-workbench-related='preview']").count() >= 1
        assert page.locator("#monitoring-inspector").is_hidden()

        target.focus()
        target.press("Enter")
        inspector = page.locator("#monitoring-inspector")
        assert inspector.is_visible()
        assert inspector.get_attribute("role") == "complementary"
        capture_workbench(page, "monitoring-open")
        assert page.locator("[data-workbench-related='selected']").count() >= 1
        assert page.locator(".is-semantic-value-change, .is-semantic-state-change").count() == 0

        page.locator(".monitoring-refresh").click()
        page.wait_for_function(
            "document.querySelector('#monitoring-inspector')?.textContent.includes('64')"
        )
        assert inspector.is_visible()
        inspector.press("Escape")
        assert inspector.is_hidden()
        assert page.evaluate("document.activeElement?.classList.contains('macro-layer-card')")

        target = page.locator(".macro-layer-card").first
        target.click()
        page.locator(".monitoring-refresh").click()
        page.wait_for_function("document.querySelector('.macro-layer-card') === null")
        assert inspector.is_hidden()

        page.locator('[data-page-link="market-analysis"]').click()
        page.wait_for_url("**/indicators-page")
        assert not page.locator("body").evaluate(
            "el => el.classList.contains('is-workbench-inspector-open')"
        )
        page.locator("#monitoring-inspector").wait_for(state="detached")
        assert page.locator("#monitoring-inspector").count() == 0
        assert errors == []
        context.close()
        browser.close()


@pytest.mark.skipif(not _backend_running(), reason="browser backend not running")
@pytest.mark.parametrize(
    ("viewport", "role"),
    [
        ({"width": 2560, "height": 1440}, "complementary"),
        ({"width": 1100, "height": 800}, "dialog"),
        ({"width": 800, "height": 900}, "dialog"),
    ],
)
def test_btc_workbench_drawer_resize_and_selection_lifecycle(viewport: dict, role: str) -> None:
    from playwright.sync_api import sync_playwright

    dashboard_reads = 0
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_api(route) -> None:
            nonlocal dashboard_reads
            url = route.request.url
            if "/btc-derivatives/dashboard/refresh" in url:
                _json(route, {"status": "success"})
            elif "/btc-derivatives/dashboard" in url:
                dashboard_reads += 1
                _json(route, _btc_payload(funding=0.01 + dashboard_reads / 100))
            elif "/precompute/hint" in url:
                _json(route, {"status": "success"})
            else:
                route.continue_()

        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/btc-derivatives-page", wait_until="domcontentloaded")
        target = page.locator("#btc-open-summary-evidence")
        target.wait_for(state="visible")
        target.press("Space")
        inspector = page.locator("#btc-workbench-inspector")
        assert inspector.is_visible()
        assert inspector.get_attribute("role") == role
        capture_workbench(page, f"btc-open-{viewport['width']}")
        assert inspector.get_attribute("aria-modal") == ("true" if role == "dialog" else "false")
        if role == "dialog":
            assert page.locator("body").evaluate(
                "el => el.classList.contains('is-workbench-inspector-drawer-open')"
            )
            assert page.locator(".workbench-inspector-close").evaluate(
                "el => document.activeElement === el"
            )
            rect = inspector.evaluate(
                "el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); "
                "const root = document.querySelector('#page-root'); "
                "const rs = getComputedStyle(root); "
                "return { y: r.y, height: r.height, bottom: r.bottom, position: s.position, "
                "top: s.top, maxHeight: s.maxHeight, scrollY, innerHeight, "
                "rootWillChange: rs.willChange, rootTransform: rs.transform }; }"
            )
            assert rect["y"] < viewport["height"], rect
            assert rect["bottom"] <= viewport["height"] + 1, rect
        else:
            assert not page.locator("body").evaluate(
                "el => el.classList.contains('is-workbench-inspector-drawer-open')"
            )

        page.locator("#btc-refresh").evaluate("el => el.click()")
        page.wait_for_function(
            "document.querySelector('#btc-workbench-inspector')?.textContent.includes('0.03')"
        )
        assert inspector.is_visible()
        inspector.press("Escape")
        assert inspector.is_hidden()
        # Refresh replaces the summary controls, so the remounted inspector
        # returns focus to the stable refresh action.
        assert page.evaluate("document.activeElement?.id === 'btc-refresh'")

        page.locator('[data-page-link="monitoring-overview"]').evaluate("el => el.click()")
        page.wait_for_url("**/monitoring-page")
        page.locator("#btc-workbench-inspector").wait_for(state="detached")
        assert not page.locator("body").evaluate(
            "el => el.classList.contains('is-workbench-inspector-open')"
        )
        assert page.locator("#btc-workbench-inspector").count() == 0
        assert errors == []
        context.close()
        browser.close()


@pytest.mark.skipif(not _backend_running(), reason="browser backend not running")
def test_market_events_feed_refresh_replacement_and_route_cleanup() -> None:
    from playwright.sync_api import sync_playwright

    event_reads = 0
    errors: list[str] = []
    event = {
        "event_id": "fixture-event-1",
        "category": "macro",
        "title": "Fixture 宏观事件",
        "summary": "用于验证事件选择生命周期。",
        "source": "fixture",
        "reliability": "high",
        "ts_event": "2026-08-29T02:00:00Z",
        "payload_json": {},
        "instrument_ids": ["btc-usdt-perp"],
        "is_frozen": False,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_api(route) -> None:
            nonlocal event_reads
            url = route.request.url
            if "/market-events/supply-event-calendar" in url:
                _json(route, {"items": [], "coverage": []})
            elif "/market-events/sync" in url:
                _json(route, {"status": "success"})
            elif "/marketevents" in url:
                event_reads += 1
                _json(route, [event] if event_reads == 1 else [])
            else:
                route.continue_()

        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/market-events-page", wait_until="domcontentloaded")
        target = page.locator(".event-card").first
        target.wait_for(state="visible")
        assert "btc-usdt-perp" in target.text_content()
        assert page.locator("#events-inspector").count() == 0
        capture_workbench(page, "events-feed")

        page.locator("#events-refresh").click()
        page.wait_for_function("document.querySelector('.event-card') === null")
        assert page.locator("#events-inspector").count() == 0

        page.locator('[data-page-link="knowledge-base"]').click()
        page.wait_for_url("**/knowledge-page")
        assert page.locator("#events-inspector").count() == 0
        assert not page.locator("body").evaluate(
            "el => el.classList.contains('is-workbench-inspector-open')"
        )
        assert errors == []
        context.close()
        browser.close()


@pytest.mark.skipif(not _backend_running(), reason="browser backend not running")
def test_macro_day_selection_refresh_replacement_and_route_cleanup() -> None:
    from playwright.sync_api import sync_playwright

    calendar_reads = 0
    errors: list[str] = []
    event_day = datetime.now(timezone.utc).date().isoformat()
    macro_event = {
        "event_id": "fixture-macro-1",
        "event_key": "us_cpi",
        "title": "美国 CPI",
        "scheduled_at": f"{event_day}T12:30:00Z",
        "status": "released",
        "actual_value_num": 2.8,
        "consensus_value_num": 2.9,
        "previous_value_num": 3.0,
        "surprise_num": -0.1,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_api(route) -> None:
            nonlocal calendar_reads
            url = route.request.url
            if "/macro/sync" in url:
                _json(route, {"status": "success"})
            elif "/macro/calendar" in url:
                calendar_reads += 1
                _json(route, [macro_event] if calendar_reads == 1 else [])
            else:
                route.continue_()

        page.route("**/api/v1/**", route_api)
        page.goto(f"{BASE_URL}/macro-calendar-page", wait_until="domcontentloaded")
        page.locator("#macro-calendar-toggle").click()
        day = page.locator(".calendar-day[data-workbench-selectable]").first
        day.wait_for(state="visible")
        day.press("Space")
        inspector = page.locator("#macro-inspector")
        assert inspector.is_visible()
        assert "事件数量" in inspector.text_content()
        capture_workbench(page, "macro-open")

        page.locator("#macro-sync-button").click()
        page.wait_for_function(
            "document.querySelector('.calendar-day[data-workbench-selectable]') === null"
        )
        assert inspector.is_hidden()
        assert page.evaluate("document.activeElement?.id === 'macro-sync-button'")

        page.locator('[data-page-link="knowledge-base"]').click()
        page.wait_for_url("**/knowledge-page")
        page.locator("#macro-inspector").wait_for(state="detached")
        assert page.locator("#macro-inspector").count() == 0
        assert not page.locator("body").evaluate(
            "el => el.classList.contains('is-workbench-inspector-open')"
        )
        assert errors == []
        context.close()
        browser.close()
