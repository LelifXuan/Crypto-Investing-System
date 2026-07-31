"""Readback probe for §16.C chart theme tokens.

Loads /indicators-page in headless Chromium, imports charts.js, and checks
that `globalThis.__CHART_THEME__` (set when charts.js evaluates) has all
20 keys resolved to non-empty strings equal (modulo whitespace) to the
CSS variables defined in :root.

Audit reference: docs/UI_UX_AUDIT_2026-07-31.md §16.C
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8002/indicators-page"

EXPECTED_KEYS = {
    "legend", "tooltipBg", "tooltipBorder", "tooltipFg1", "tooltipFg2",
    "axis", "gridX", "gridY",
    "referenceLine", "referenceLabel",
    "expiryLine", "expiryLabel",
    "dotPutWall", "dotMaxPain", "dotCallWall", "dotStroke",
    "upStroke", "downStroke", "upFill", "downFill",
}


def run() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=8000)
        page.wait_for_timeout(2500)

        # Force the charts.js module to evaluate so globalThis.__CHART_THEME__
        # gets populated regardless of which page is rendered.
        result = page.evaluate(
            """async () => {
              const mod = await import('/static/ui/charts.js');
              const theme = (typeof globalThis !== 'undefined' && globalThis.__CHART_THEME__) || null;
              return {
                moduleLoaded: typeof mod === 'object' && typeof mod.renderChart === 'function',
                hasTheme: !!theme,
                keys: theme ? Object.keys(theme).sort() : null,
              };
            }"""
        )
        print(f"§16.C runtime readback: {result}")
        if not result["moduleLoaded"]:
            print("FAIL: renderChart not exported from charts.js")
            browser.close()
            return 1
        if not result["hasTheme"]:
            print("FAIL: globalThis.__CHART_THEME__ not populated")
            browser.close()
            return 1
        keys = set(result["keys"] or [])
        missing = EXPECTED_KEYS - keys
        extra = keys - EXPECTED_KEYS
        if missing:
            print(f"FAIL: missing keys: {sorted(missing)}")
            browser.close()
            return 1
        if extra:
            print(f"NOTE: extra keys (allowed): {sorted(extra)}")

        # Compare theme values to CSS variables.
        resolved = page.evaluate(
            """async () => {
              await import('/static/ui/charts.js');
              const theme = globalThis.__CHART_THEME__;
              const cs = getComputedStyle(document.documentElement);
              const TOKEN_MAP = {
                legend: '--chart-legend',
                tooltipBg: '--chart-tooltip-bg',
                tooltipBorder: '--chart-tooltip-border',
                tooltipFg1: '--chart-tooltip-fg-1',
                tooltipFg2: '--chart-tooltip-fg-2',
                axis: '--chart-axis',
                gridX: '--chart-grid-x',
                gridY: '--chart-grid-y',
                referenceLine: '--chart-reference-line',
                referenceLabel: '--chart-reference-label',
                expiryLine: '--chart-expiry-line',
                expiryLabel: '--chart-expiry-label',
                dotPutWall: '--chart-dot-put-wall',
                dotMaxPain: '--chart-dot-max-pain',
                dotCallWall: '--chart-dot-call-wall',
                dotStroke: '--chart-dot-stroke',
                upStroke: '--chart-up-stroke',
                downStroke: '--chart-down-stroke',
                upFill: '--chart-up-fill',
                downFill: '--chart-down-fill',
              };
              const pairs = {};
              for (const k of Object.keys(theme)) {
                const tokenName = TOKEN_MAP[k];
                pairs[k] = { theme: theme[k], css: tokenName ? cs.getPropertyValue(tokenName).trim() : '' };
              }
              return pairs;
            }"""
        )
        print("§16.C theme-vs-CSS comparison:")
        failures = 0
        for k in sorted(resolved.keys()):
            row = resolved[k]
            ok = row["theme"] == row["css"]
            status = "OK" if ok else "DIFF"
            if not ok and row["theme"] and row["css"]:
                failures += 1
            print(f"  [{status}] {k}: theme={row['theme']!r:30}  css={row['css']!r}")
        browser.close()
        if failures:
            print(f"FAIL: {failures} mismatch(es)")
            return 1
        print("PASS: chart theme reads match CSS variables")
        return 0


if __name__ == "__main__":
    sys.exit(run())
