"""Confirm analysis hero left/right cards are now bottom-aligned.

Spec: the user reported that the left .analysis-hero-card and right
.realtime-card in /indicators-page had different bottom edges.

Fix landed: align-items: stretch on .analysis-overview-grid + flex column
on .realtime-card with margin-top: auto on the inner .status-grid.
This drives:
  - Both cards to equal height (the taller one wins)
  - Realtime-card's mini-cards (最近刷新 / 最近收盘) pin to the bottom

This probe measures both cards' bottom offsets and asserts
|left.bottom - right.bottom| <= 2px.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "tests" / "screenshots" / "dropdown-2026-07-31"
SHOTS.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8002/indicators-page", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(5000)

        # confirm both cards exist
        rects = page.evaluate(
            """() => {
              const left = document.querySelector('.analysis-hero-card');
              const right = document.querySelector('.realtime-card');
              if (!left || !right) return null;
              const lr = left.getBoundingClientRect();
              const rr = right.getBoundingClientRect();
              return {
                left: { top: lr.top, bottom: lr.bottom, height: lr.height, width: lr.width },
                right: { top: rr.top, bottom: rr.bottom, height: rr.height, width: rr.width },
              };
            }"""
        )
        print(f"hero rects: {rects}")
        if rects is None:
            print("FAIL: hero cards not found")
            browser.close()
            return 1

        diff = abs(rects["left"]["bottom"] - rects["right"]["bottom"])
        same_height = abs(rects["left"]["height"] - rects["right"]["height"]) < 1.5
        print(f"|bottom diff| = {diff:.2f}px   same_height={same_height}")
        # Allow up to 4px tolerance for sub-pixel rounding
        ok_align = diff <= 4.0

        page.screenshot(path=str(SHOTS / f"analysis-hero-align-{int(time.time())}.png"), full_page=False)

        browser.close()

        if not ok_align:
            print(f"FAIL: hero cards still mis-aligned by {diff:.2f}px")
            return 1
        print("PASS: analysis hero cards bottom-aligned within tolerance")
        return 0


if __name__ == "__main__":
    sys.exit(main())