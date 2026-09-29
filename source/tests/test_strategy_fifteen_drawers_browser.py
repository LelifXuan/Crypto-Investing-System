"""Browser contract: all fifteen matrix cells open their own trade horizon."""

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright
from test_strategy_period_opportunity import bundle, node

from app.services.strategy_unified.opportunity_scanner import _extract_scan_item
from app.services.strategy_unified.period_opportunity import build_period_opportunities

INSTRUMENTS = ("btc", "eth", "hype", "bnb", "okb")
EXECUTION = {"1w": "1d", "1d": "4h", "4h": "1h"}


def _payload(instrument: str) -> dict:
    iid = f"{instrument}-usdt-perp"
    weekly = "LONG"
    daily = "NEUTRAL" if instrument == "hype" else "LONG"
    four_hour = "SHORT" if instrument == "hype" else "LONG"
    hourly = four_hour
    nodes = [
        node("1M", "LONG"),
        node("1w", weekly),
        node("1d", daily),
        node("4h", four_hour),
        node("1h", hourly),
    ]
    decisions = build_period_opportunities(
        iid,
        nodes,
        {
            "1w": bundle("LONG", "100", target_delta="45", stop_delta="8", atr_pct="12"),
            "1d": bundle("LONG", "100", target_delta="25", stop_delta="4", atr_pct="6"),
            "4h": bundle(
                four_hour,
                "101",
                target_delta="20" if instrument == "hype" else "14",
                stop_delta="4" if instrument == "hype" else "2",
                atr_pct="3",
            ),
            "1h": bundle(
                hourly,
                "102",
                target_delta="8" if instrument == "hype" else "5",
                stop_delta="2",
                atr_pct="1.5",
            ),
        },
        [],
    )
    return {
        "instrument_id": iid,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_key": f"browser:{iid}",
        "status": "ready",
        "cache_state": "fresh",
        "market_decision_snapshot": {"snapshot_id": f"browser:{iid}"},
        "unified_state": {"current_price": 102, "risk_level": "low"},
        "timeframe_stack": [
            {
                "timeframe": n.timeframe,
                "direction": n.direction,
                "freshness": "fresh",
                "confidence": 92,
                "long_score": 75 if n.direction == "LONG" else 35,
                "short_score": 75 if n.direction == "SHORT" else 35,
                "evidence": n.evidence,
            }
            for n in nodes
        ],
        "opportunity_decisions": decisions,
        "trade_decision": {"side": "NONE", "permission": "observe"},
    }


def test_fifteen_scan_slots_open_only_confirmed_period_opportunities():
    payloads = {f"{code}-usdt-perp": _payload(code) for code in INSTRUMENTS}
    matrix = [
        asdict(_extract_scan_item(payload, iid, code.upper(), tf))
        for iid, payload in payloads.items()
        for code in (iid.split("-")[0],)
        for tf in EXECUTION
    ]
    scan = {
        "matrix": matrix,
        "ranked": [],
        "timeframes": list(EXECUTION),
        "cache_meta": {"source": "cache"},
    }
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_api(route):
            url = route.request.url
            if "/strategy/scan" in url:
                route.fulfill(json=scan)
            elif "/strategy/unified" in url:
                iid = parse_qs(urlparse(url).query).get("instrument_id", ["btc-usdt-perp"])[0]
                route.fulfill(json=payloads[iid])
            else:
                route.fulfill(json={})

        page.route("**/api/v1/**", route_api)
        page.goto(f"{base_url}/strategy-page", wait_until="domcontentloaded")
        page.locator(".scan-cell-btn").first.wait_for()
        assert page.locator(".scan-cell-btn").count() == 15
        btc_horizon_metrics = {}
        for iid in payloads:
            for tf, execution_tf in EXECUTION.items():
                cell = page.locator(
                    f'.scan-cell-btn[data-instrument="{iid}"][data-timeframe="{tf}"]'
                )
                decision = payloads[iid]["opportunity_decisions"][tf]
                if decision["status"] != "READY":
                    assert cell.count() == 0
                    row = page.locator(
                        ".scan-matrix-table tr",
                        has=page.locator(".scan-matrix-code", has_text=iid.split("-")[0].upper()),
                    )
                    inactive_cell = row.locator(".scan-cell-btn").nth(list(EXECUTION).index(tf))
                    assert inactive_cell.is_disabled()
                    assert "无机会" in inactive_cell.inner_text()
                    continue
                cell.click()
                opportunity = page.locator(".strategy-period-opportunity")
                opportunity.wait_for()
                assert opportunity.get_attribute("data-opportunity-id") == f"{iid}:{tf}"
                assert opportunity.get_attribute("data-trade-timeframe") == tf
                assert opportunity.get_attribute("data-execution-timeframe") == execution_tf
                assert decision["side"] in {"LONG", "SHORT"}
                if iid == "btc-usdt-perp":
                    metrics = opportunity.locator(
                        ".strategy-timeframe-focus-metrics strong"
                    ).all_text_contents()
                    btc_horizon_metrics[tf] = (
                        metrics[4],
                        metrics[6],
                        metrics[7],
                        metrics[10],
                        metrics[11],
                    )
                if iid == "btc-usdt-perp" and tf == "4h":
                    page.screenshot(
                        path=str(Path(__file__).parent / "screenshots/strategy-period-15.png"),
                        full_page=True,
                    )
                page.locator("#strategy-detail-close").click()
                page.locator("#strategy-detail-panel").wait_for(state="detached")
        for field in zip(*btc_horizon_metrics.values(), strict=True):
            assert len(set(field)) == 3
        assert not errors
        browser.close()
