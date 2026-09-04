"""Deterministic Analysis migration checks; backend absence is a failure."""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_command_palette_browser_contract import fixture_api
from test_workbench_browser_contract import BASE_URL, _json, capture_workbench

ROOT = Path(__file__).resolve().parents[1]


def test_stress_distinguishes_chart_loss_from_explicit_unavailability():
    from stress_test import _detect_issues

    before = {"canvas": 6, "loading": 0, "checkVisible": True}
    after = {"canvas": 0, "loading": 0, "checkVisible": False}
    config = {"expected_canvas": True, "check_selector": "canvas"}
    result = {"actions": [], "verdict": "PASS"}
    _detect_issues(result, before, after, config)
    assert result["verdict"] == "FAIL"
    result = {"actions": [], "verdict": "PASS"}
    _detect_issues(result, before, {**after, "terminalUnavailable": True}, config)
    assert result["verdict"] == "PASS"
    assert result["availability"] == "unavailable-with-explicit-terminal-ui"
    result = {"actions": [], "verdict": "PASS"}
    _detect_issues(result, before, {**before, "busy": True}, config)
    assert result["verdict"] == "FAIL"


def test_stress_waits_for_same_context_refresh_busy_state():
    from stress_test import PWTimeout, _wait_for_analysis_settle

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(
            '<main id="page-root"></main>'
            '<button id="analysis-refresh" aria-busy="true"></button>'
        )
        page.evaluate("""setTimeout(() => {
            document.querySelector('button').setAttribute('aria-busy', 'false');
        }, 150)""")
        _wait_for_analysis_settle(page, timeout=3000)
        expect(page.locator("button")).to_have_attribute("aria-busy", "false")
        page.locator("button").evaluate("el=>el.setAttribute('aria-busy','true')")
        with pytest.raises(PWTimeout):
            _wait_for_analysis_settle(page, timeout=100)
        browser.close()


def test_analysis_adapter_real_fields_stable_ids_and_missing_values():
    module = (ROOT / "app/static/pages/analysisInspection.js").as_uri()
    script = f"""
      import {{buildAnalysisInspections,CHART_OBJECTS}} from {module!r};
      import assert from 'node:assert/strict';
      const a={{ema30:[],ema60:[],ema120:[],adxValues:{{}},macdValues:{{}},boll:{{}},
        vwapValues:{{}},kdjValues:{{}},rsiValues:[0]}};
      const model={{analysis:a,cards:[{{key:'rsi',title:'RSI',desc:'已有解释'}}],
        bundle:{{status:'ready',snapshot_at:'2026-08-31T00:00:00Z'}},descriptions:{{}}}};
      let rows=buildAnalysisInspections(model);
      assert.equal(rows.length,1); assert.equal(rows[0].id,'analysis:rsi');
      assert.equal(rows[0].current.value,0);
      assert.equal(rows[0].sources[0].status,'unavailable');
      assert.equal(rows[0].interpretation,'已有解释');
      a.rsiValues=[null]; assert.equal(buildAnalysisInspections(model).length,0);
      a.rsiValues=[72]; rows=buildAnalysisInspections(model);
      assert.equal(rows[0].id,'analysis:rsi'); assert.equal(rows[0].current.value,72);
      assert.deepEqual(CHART_OBJECTS['analysis-volume'],['volume']);
      assert.ok(!Object.values(CHART_OBJECTS).flat().includes('obv'));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def analysis_payload(rsi=62, *, status="ready"):
    origin = datetime(2026, 8, 1, tzinfo=timezone.utc)
    candles = [
        {
            "ts_open": (origin + timedelta(hours=i)).isoformat(),
            "open": str(100 + i),
            "high": str(103 + i),
            "low": str(99 + i),
            "close": str(102 + i),
            "volume": "1000",
        }
        for i in range(240)
    ]
    return {
        "status": status,
        "cache_state": "stale" if status == "stale" else "fresh",
        "snapshot_at": "2026-08-31T00:00:00Z",
        "mode": "range",
        "candles": candles,
        "core_indicator_series": {"rsi_14": [rsi] * 240},
        "secondary_indicator_series": {"bbands_width": [10] * 239 + [2]},
    }


def install_fixture(page, state):
    def route_api(route):
        url = route.request.url
        if "/analysis/bundle" in url:
            payload = analysis_payload(state.get("rsi", 62), status=state.get("status", "ready"))
            if state.get("cold"):
                payload.update(candles=[], status="missing", refresh_task_key="analysis-fixture")
            _json(route, payload)
        elif "/precompute/hint" in url:
            _json(route, {"status": "queued", "queued_keys": ["analysis-fixture"]})
        elif "/precompute/tasks/" in url:
            state["polls"] = state.get("polls", 0) + 1
            _json(
                route,
                {"status": state.get("task", "missing"), "last_error": "fixture task failure"},
            )
        else:
            fixture_api(route)

    page.route("**/api/v1/**", route_api)


def capture_errors(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    return errors


@pytest.mark.parametrize("width", [2560, 1180, 900, 390])
def test_analysis_cards_are_read_only_and_sidebar_is_absent(width):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": 1440}, reduced_motion="reduce"
        )
        state = {"rsi": 62}
        install_fixture(page, state)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/indicators-page?keep=yes&inspect=analysis:rsi")
        rsi = page.locator('#analysis-signal-cards [data-workbench-id="analysis:rsi"]')
        expect(rsi).to_be_visible()
        expect(rsi).not_to_have_attribute("role", "button")
        assert page.locator("#analysis-inspector").count() == 0
        assert page.locator(".analysis-regime-objects").count() == 0
        assert page.locator('[data-workbench-id="analysis:volatility-phase"]').count() == 0
        assert page.locator('[data-workbench-id="analysis:directional-bias"]').count() == 0
        expect(page.locator("#analysis-statusbar .status-banner")).to_be_visible()
        expect(page.locator("#analysis-statusbar .status-mode-badge")).to_be_visible()
        hero_width = page.locator(".analysis-hero-card").evaluate(
            "element => element.getBoundingClientRect().width"
        )
        mark_width = page.locator(".realtime-card").evaluate(
            "element => element.getBoundingClientRect().width"
        )
        if width > 1180:
            assert mark_width < hero_width * 0.5
        else:
            assert abs(mark_width - hero_width) <= 1
        assert "inspect=" not in page.url and "keep=" not in page.url
        state["rsi"] = 71
        page.locator("#analysis-refresh").click()
        expect(rsi.locator(".signal-value")).to_have_text("71")
        page.keyboard.press("Control+k")
        expect(page.get_by_role("option")).to_have_count(4)
        page.keyboard.press("Escape")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
        browser.close()


def test_analysis_refresh_preserves_card_identity_without_sidebar_state():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        state = {}
        install_fixture(page, state)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/indicators-page")
        rsi = page.locator('#analysis-signal-cards [data-workbench-id="analysis:rsi"]')
        rsi.evaluate("el => window.analysisOriginalCard = el")
        page.locator("#analysis-refresh").click()
        expect(page.locator("#analysis-refresh")).to_have_attribute("aria-busy", "false")
        assert rsi.evaluate("el => el === window.analysisOriginalCard")
        assert page.locator(".workbench-inspector").count() == 0
        assert "is-workbench-inspector-open" not in page.locator("body").get_attribute("class")
        assert errors == []
        browser.close()


def test_analysis_lkg_cold_failure_and_late_recovery():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        state = {"status": "stale", "task": "error"}
        install_fixture(page, state)
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/indicators-page?inspect=analysis:rsi")
        expect(page.locator(".analysis-recovery-note")).to_contain_text("保留最近有效")
        assert "inspect=" not in page.url
        state.update(cold=True, task="running")
        page.reload()
        expect(page.locator("#analysis-context-rail")).to_contain_text("等待分析快照")
        state["task"] = "error"
        expect(page.locator(".analysis-recovery-note")).to_contain_text("暂不可用")
        expect(page.get_by_role("status", name="图表加载中", exact=True)).to_have_count(0)
        expect(page.locator(".analysis-is-transitioning")).to_have_count(0)
        assert page.locator(".workbench-inspector").count() == 0
        assert errors == []
        browser.close()


def test_analysis_nine_indicators_form_two_aligned_rows():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        install_fixture(page, {})
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/indicators-page")
        cards = page.locator("#analysis-signal-cards > .signal-card")
        expect(cards).to_have_count(9)
        geometry = cards.evaluate_all("""cards => cards.map(card => {
          const box = card.getBoundingClientRect();
          const offset = selector => {
            const child = card.querySelector(selector).getBoundingClientRect();
            return Math.round(child.top - box.top);
          };
          return { y: Math.round(box.y), height: Math.round(box.height),
            title: offset('.card-head-inline'), value: offset('.signal-value'),
            label: offset('.signal-label'), copy: offset('.signal-copy') };
        })""")
        assert len({item["y"] for item in geometry}) == 2
        card_heights = [item["height"] for item in geometry]
        assert max(card_heights) - min(card_heights) <= 1
        for layer in ("title", "value", "label", "copy"):
            layer_offsets = [item[layer] for item in geometry]
            assert max(layer_offsets) - min(layer_offsets) <= 1
        assert page.locator("#analysis-inspector").count() == 0
        assert errors == []
        browser.close()


@pytest.mark.parametrize(
    "viewport",
    [
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
    ],
)
def test_analysis_responsive_settled(viewport):
    width, height = viewport
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        install_fixture(page, {})
        errors = capture_errors(page)
        page.goto(f"{BASE_URL}/indicators-page?inspect=analysis:rsi")
        expect(page.locator("#analysis-refresh")).to_have_attribute("aria-busy", "false")
        assert page.locator("#analysis-inspector").count() == 0
        assert "inspect=" not in page.url
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        capture_workbench(page, f"analysis-responsive-{width}-{height}")
        assert errors == []
        browser.close()
