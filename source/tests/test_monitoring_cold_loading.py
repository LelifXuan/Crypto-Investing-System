"""Cold-start feedback uses real page markup and CSS, with a held API response."""

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.mark.parametrize("outcome", ["success", "failure", "reduced-motion"])
def test_monitoring_cold_loading_lifecycle(base_url, outcome):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 2560, "height": 1440})
        motion = "reduce" if outcome == "reduced-motion" else "no-preference"
        page.emulate_media(reduced_motion=motion)
        held = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/monitoring/dashboard?*", lambda route: held.append(route))
        page.goto(f"{base_url}/monitoring-page", wait_until="domcontentloaded")
        spinner = page.locator(".monitoring-cold-spinner").first
        expect(spinner).to_be_visible()
        expect(page.locator('.monitoring-topbar[aria-busy="true"]')).to_be_visible()
        # Cold-start shell now seeds placeholders in macro-panel / macro-grid /
        # governance / topbar grid (ui-audit U5, 2026-09-16). At least one
        # placeholder span must be non-zero width so the user sees a real skeleton
        # bar rather than an invisible 0-width cell.
        span_count = page.locator(".monitoring-cold-placeholder span").count()
        assert span_count >= 3, (
            f"Expected at least 3 .monitoring-cold-placeholder span rows during cold start, "
            f"got {span_count}."
        )
        max_width = 0
        for idx in range(span_count):
            box = page.locator(".monitoring-cold-placeholder span").nth(idx).bounding_box()
            if box and box["width"] > max_width:
                max_width = box["width"]
        assert max_width > 100, (
            f"At least one .monitoring-cold-placeholder span must be wider than 100px "
            f"during cold start; observed max width = {max_width}."
        )
        assert spinner.evaluate("el => getComputedStyle(el).animationName") == (
            "none" if outcome == "reduced-motion" else "monitoringColdSpin"
        )
        if outcome == "success":
            first = spinner.evaluate("el => getComputedStyle(el).transform")
            page.wait_for_function(
                "first => getComputedStyle(document.querySelector("
                "'.monitoring-cold-spinner')).transform !== first",
                arg=first,
            )
        artifacts = Path(__file__).resolve().parents[2] / "reports/monitoring-cold-start-20260904"
        artifacts.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifacts / f"{outcome}-pending.png"), full_page=True)
        assert held, "The cold dashboard request should be pending"
        if outcome == "failure":
            held[0].fulfill(status=503, json={"detail": "verification unavailable"})
            expect(page.locator(".monitoring-progress-banner")).to_contain_text(
                "监控快照暂不可用", timeout=35000,
            )
        else:
            held[0].continue_()
            expect(page.locator(".monitoring-topbar.is-warming")).to_have_count(0, timeout=35000)
        expect(spinner).to_have_count(0)
        page.unroute("**/monitoring/dashboard?*")
        expect(page.locator(".monitoring-cold-placeholder")).to_have_count(0)
        # Spinners settle together once the dashboard responds (ui-audit U5).
        expect(page.locator(".monitoring-cold-spinner")).to_have_count(0)
        assert not errors
        page.screenshot(path=str(artifacts / f"{outcome}-settled.png"), full_page=True)
        browser.close()
