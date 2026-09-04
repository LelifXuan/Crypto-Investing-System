"""Read-only Structure workspace browser contracts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_analysis_workbench import capture_errors
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _json, capture_workbench

ROOT = Path(__file__).resolve().parents[1]


def test_structure_source_has_no_inspector_adapter_or_trigger() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    assert "mountStructureWorkbench" not in source
    assert "structure-inspector" not in source
    assert not (ROOT / "app/static/pages/structureWorkbench.js").exists()
    assert not (ROOT / "app/static/pages/structureInspection.js").exists()
    assert 'id="structure-chart-panel"' in source
    assert 'id="structure-summary-panel"' in source
    assert 'currentUrl.searchParams.delete("inspect")' in source
    assert 'currentUrl.searchParams.delete("keep")' in source


def structure_payload(*, score=62):
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def at(index):
        return (origin + timedelta(hours=index)).isoformat()

    def point(index, price):
        return {"index": index, "time": at(index), "ts": at(index), "price": price}

    candles = [
        {
            "ts_open": at(index),
            "open": str(100 + index / 10),
            "close": str(101 + index / 10),
            "high": str(102 + index / 10),
            "low": str(99 + index / 10),
            "volume": "1000",
        }
        for index in range(240)
    ]
    pattern = {
        "id": "published-pattern",
        "source_pattern_type": "rectangle",
        "pattern_type": "rectangle",
        "display_name": "矩形区间",
        "status": "developing",
        "direction_bias": "neutral",
        "confidence": 0.9,
        "display_role": "primary",
        "renderable": True,
        "display_range": {"start_index": 80, "start_time": at(80), "end_index": 220},
        "region": {
            "polygon_points": [
                point(80, 110), point(220, 110), point(220, 130), point(80, 130)
            ],
            "fill_token": "patternNeutral",
            "fill_alpha": 0.12,
        },
        "lines": [
            {
                "role": "upper_boundary",
                "label": "上边界",
                "points": [point(80, 130), point(220, 130)],
            },
            {
                "role": "lower_boundary",
                "label": "下边界",
                "points": [point(80, 110), point(220, 110)],
            },
        ],
        "levels": {"breakout_confirm": 130, "breakdown_confirm": 110},
        "explanation": {"status_text": "发展中", "tooltip": "已发布矩形证据"},
    }
    snapshot = {
        "snapshot_version": "fixture-v1",
        "generated_at": "2026-08-31T00:00:00Z",
        "overall": {
            "overall_bias": "neutral",
            "score": 50,
            "confidence": 0.8,
            "meaning": "已发布结构摘要",
            "text_decision": {"headline": "矩形区间内", "resolved_state": "inside"},
        },
        "systems": [
            {
                "system": key,
                "score": score,
                "confidence": 0.9,
                "status": "confirmed",
                "direction": "neutral",
                "top_reasons": [f"{key} 已发布证据"],
                "generated_at": "2026-08-31T00:00:00Z",
            }
            for key in ("swing", "classic", "profile")
        ],
        "classic_patterns": {
            "version": "classic-pattern-region-v1",
            "primary": pattern,
            "candidates": [],
        },
        "geometry": [
            {
                "geometry_id": "swing-line",
                "system": "swing",
                "kind": "swing_zigzag",
                "visible": True,
                "points_json": [point(80, 107), point(140, 116), point(200, 119)],
                "meta_json": {"role": "swing_zigzag"},
            },
            {
                "geometry_id": "profile-area",
                "system": "profile",
                "kind": "value_area",
                "visible": True,
                "meta_json": {"poc": 120, "vah": 125, "val": 115},
                "points_json": [
                    {**point(80, 120), "label": "POC"},
                    {**point(220, 120), "label": "POC"},
                    {**point(220, 125), "label": "VAH"},
                    {**point(220, 115), "label": "VAL"},
                ],
            },
        ],
    }
    return {
        "snapshot": snapshot,
        "candles": candles,
        "cache_state": "ready",
        "freshness_state": "fresh",
    }


def install_structure_fixture(page, state):
    def route_api(route):
        if "/structure/tab/bundle" in route.request.url:
            state["reads"] = state.get("reads", 0) + 1
            _json(route, structure_payload(score=state.get("score", 62)))
        elif "/structure/tab/refresh" in route.request.url:
            state["refreshes"] = state.get("refreshes", 0) + 1
            _json(route, {"refreshed": True})
        else:
            fixture_api(route)

    page.route("**/api/v1/**", route_api)


@pytest.mark.parametrize("width,height", [(2560, 1440), (1180, 800), (390, 844)])
def test_structure_keeps_chart_and_summary_without_inspector(width, height):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        install_structure_fixture(page, {})
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/structure-page?inspect=structure:system:swing&keep=yes")

        expect(page.locator(".structure-chart-svg")).to_be_visible()
        expect(page.locator(".structure-summary-card")).to_be_visible()
        expect(page.locator(".structure-system-merge")).to_have_count(3)
        assert page.locator("#structure-inspector").count() == 0
        assert page.locator(".workbench-inspector").count() == 0
        assert page.locator("[data-workbench-id]").count() == 0
        assert "inspect=" not in page.url and "keep=" not in page.url
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture_workbench(page, f"structure-read-only-{width}-{height}")
        assert errors == []
        browser.close()


def test_structure_filters_and_refresh_keep_primary_workspace():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        state = {}
        install_structure_fixture(page, state)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/structure-page")
        expect(page.locator(".structure-chart-svg")).to_be_visible()

        page.locator('[data-dropdown-id="structure-system"]').click()
        page.get_by_role("option", name="摆动结构", exact=True).click()
        expect(page.locator('[data-dropdown-id="structure-system"]')).to_contain_text(
            "摆动结构"
        )
        expect(page.locator(".structure-chart-svg")).to_be_visible()

        state["score"] = 75
        page.locator("#structure-refresh").click()
        expect(page.locator(".structure-summary-card")).to_contain_text("75")
        assert page.locator("#structure-inspector").count() == 0
        assert state["reads"] >= 2
        assert errors == []
        browser.close()


def test_structure_wide_viewport_keeps_complete_workspace_above_fold():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1600}, reduced_motion="reduce")
        install_structure_fixture(page, {})
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/structure-page")
        expect(page.locator(".structure-chart-svg")).to_be_visible()

        chart = page.locator(".structure-main-card").bounding_box()
        summary = page.locator(".structure-summary-card").bounding_box()
        assert summary["x"] > chart["x"] + chart["width"]
        assert abs(summary["y"] - chart["y"]) <= 1
        assert page.evaluate("document.documentElement.scrollHeight <= innerHeight + 1")
        assert page.locator("#structure-inspector").count() == 0
        assert errors == []
        browser.close()
