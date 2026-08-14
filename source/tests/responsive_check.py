"""
Responsive check — multi-viewport rendering, overflow detection, content visibility.

Capability: P2-A (Responsive Testing)
Tests each page at multiple viewport sizes:
  - Mobile S: 375x667
  - Mobile L: 414x896
  - Tablet: 768x1024
  - Laptop: 1366x900 (default)
  - Desktop: 1920x1080

Checks per viewport:
  1. No horizontal overflow (scrollWidth <= viewport width)
  2. Real content is still visible
  3. Screenshot saved for visual confirmation

Usage:
  python tests/responsive_check.py --pages all
  python tests/responsive_check.py --pages monitoring-overview --viewports 375,768,1920
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
RESPONSIVE_DIR = SCREENSHOT_DIR / "responsive"
RESPONSIVE_DIR.mkdir(parents=True, exist_ok=True)

PAGE_ROUTES = {
    "market-analysis": "/indicators-page",
    "monitoring-overview": "/monitoring-page",
    "market-structure": "/structure-page",
    "market-events": "/market-events-page",
    "macro-calendar": "/macro-calendar-page",
    "knowledge-base": "/knowledge-page",
    "ashare-etf": "/ashare-etf-page",
    "btc-derivatives": "/btc-derivatives-page",
    "ai-strategy": "/strategy-page",
    "gold-allocation": "/gold-allocation-page",
}

REAL_CONTENT_SELECTORS = {
    "monitoring-overview": ["#monitoring-topbar", ".monitoring-summary-surface"],
    "market-analysis": [".analysis-hero-grid", ".analysis-chart-grid"],
    "market-structure": [".structure-page"],
    "market-events": [".events-feed-shell", ".events-feed-card", "#market-events-root"],
    "macro-calendar": ["#macro-statusbar", "#macro-summary-cards"],
    "knowledge-base": [".knowledge-hero", ".knowledge-sections"],
    "ashare-etf": ["#etf-overview", "#etf-equity-curve"],
    "btc-derivatives": [".btc-derivatives-page", ".btc-chart-overview"],
    "ai-strategy": [".strategy-scan-page", ".strategy-v2-toolbar", "#strategy-scan-matrix"],
    "gold-allocation": [".gold-workbench-grid", ".gold-chart-grid", ".gold-governance-grid"],
}

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")

DEFAULT_VIEWPORTS = [
    {"name": "mobile-s", "width": 375, "height": 667},
    {"name": "mobile-l", "width": 414, "height": 896},
    {"name": "tablet", "width": 768, "height": 1024},
    {"name": "laptop", "width": 1366, "height": 900},
    {"name": "desktop", "width": 1920, "height": 1080},
    {"name": "desktop-2k", "width": 2560, "height": 1440},
]


def check_viewport(page, page_id: str, viewport: dict) -> dict:
    """Check a single page at a single viewport size."""
    findings: list[dict] = []

    # Check for horizontal overflow
    scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
    client_width = page.evaluate("() => document.documentElement.clientWidth")
    has_overflow = scroll_width > client_width + 1  # 1px tolerance

    if has_overflow:
        findings.append({
            "check": "horizontal-overflow",
            "severity": "FAIL",
            "detail": f"scrollWidth={scroll_width}px > viewport={client_width}px",
        })

    # Check real content visibility
    selectors = REAL_CONTENT_SELECTORS.get(page_id, [".card", "section"])
    content_visible = False
    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count > 0:
                # Also check it's actually visible (not display:none)
                is_visible = page.locator(sel).first.is_visible()
                if is_visible:
                    content_visible = True
                    break
        except Exception:
            pass

    if not content_visible:
        findings.append({
            "check": "content-visible",
            "severity": "WARN",
            "detail": "Real content selector not visible at this viewport",
        })

    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")

    return {
        "viewport": viewport["name"],
        "width": viewport["width"],
        "height": viewport["height"],
        "scroll_width": scroll_width,
        "client_width": client_width,
        "has_overflow": has_overflow,
        "content_visible": content_visible,
        "findings": findings,
        "verdict": "FAIL" if fail_count > 0 else "WARN" if warn_count > 0 else "PASS",
    }


def scan_page(page_id: str, route: str, viewports: list[dict]) -> dict:
    """Scan a single page across all viewports."""
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for vp in viewports:
            ctx = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = ctx.new_page()
            page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=30_000)

            # Wait for content
            selectors = REAL_CONTENT_SELECTORS.get(page_id, [".card", "section"])
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                for sel in selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            break
                    except Exception:
                        pass
                else:
                    time.sleep(0.1)
                    continue
                break

            page.wait_for_timeout(1000)

            vp_result = check_viewport(page, page_id, vp)

            # Screenshot
            screenshot_path = RESPONSIVE_DIR / f"{page_id}_{vp['width']}x{vp['height']}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            vp_result["screenshot"] = str(screenshot_path.relative_to(REPO_ROOT))

            results.append(vp_result)
            ctx.close()

        browser.close()

    # Summarize
    overflow_viewports = [r["viewport"] for r in results if r["has_overflow"]]
    fail_viewports = [r["viewport"] for r in results if r["verdict"] == "FAIL"]

    return {
        "page_id": page_id,
        "viewports": results,
        "overflow_viewports": overflow_viewports,
        "fail_viewports": fail_viewports,
        "verdict": "FAIL" if fail_viewports else "WARN" if overflow_viewports else "PASS",
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Responsive check — multi-viewport overflow + content visibility")
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all)",
    )
    p.add_argument(
        "--viewports",
        default=",".join(v["name"] for v in DEFAULT_VIEWPORTS),
        help="comma-separated viewport names (default: all 5)",
    )
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    # Resolve viewport names
    vp_names = [s.strip() for s in args.viewports.split(",") if s.strip()]
    viewports = [v for v in DEFAULT_VIEWPORTS if v["name"] in vp_names]
    if not viewports:
        print("no valid viewports specified", file=sys.stderr)
        return 2

    report = {"viewports_tested": [v["name"] for v in viewports], "per_page": [], "summary": {}}

    for pid in page_ids:
        print(f"[responsive] {pid} at {len(viewports)} viewports ...")
        result = scan_page(pid, PAGE_ROUTES[pid], viewports)
        for vp in result["viewports"]:
            tag = vp["verdict"]
            overflow = "OVERFLOW" if vp["has_overflow"] else "ok"
            print(f"  [{tag}] {vp['viewport']:>10} {vp['width']}x{vp['height']}  "
                  f"scrollW={vp['scroll_width']} content={'Y' if vp['content_visible'] else 'N'} {overflow}")
        report["per_page"].append(result)

    # Summary
    page_fails = sum(1 for r in report["per_page"] if r["verdict"] == "FAIL")
    total_overflow = sum(len(r["overflow_viewports"]) for r in report["per_page"])
    report["summary"] = {
        "total_pages": len(report["per_page"]),
        "pages_with_fails": page_fails,
        "total_overflow_viewports": total_overflow,
    }

    print()
    print("=" * 60)
    print(f"responsive: {page_fails} pages with overflow, {total_overflow} total overflow viewports")
    print("=" * 60)

    out_log = SCREENSHOT_DIR / "responsive_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    return 1 if page_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
