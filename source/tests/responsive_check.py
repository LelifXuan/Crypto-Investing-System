"""
Responsive check — multi-viewport rendering, overflow detection, content visibility.

Capability: P2-A (Responsive Testing)
Tests each page at multiple viewport sizes:
  - Main acceptance: 2560x1440; 2560x1600 high-screen cross-check only
  - Operator breakpoints: 1500x900, 1280x720, 1100x800, 800x900
  - Mobile/tablet: 390x844, 768x1024

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
RESPONSIVE_DIR = Path(os.getenv("RESPONSIVE_OUTPUT_DIR", str(SCREENSHOT_DIR / "responsive")))
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
    {"name": "operator-sheet", "width": 800, "height": 900},
    {"name": "operator-drawer", "width": 1100, "height": 800},
    {"name": "operator-desktop", "width": 1500, "height": 900},
    {"name": "mobile-s", "width": 390, "height": 844},
    {"name": "mobile-l", "width": 414, "height": 896},
    {"name": "tablet", "width": 768, "height": 1024},
    # 2026-08-27: 1280x720 is one of the breakpoints the design handbook §11.1
    # lists as required. Knowledge-base three-rail grid is exactly 240+720+240
    # + 2x40 gap = 1280px, so a 1280-wide viewport is the natural regression
    # point for the §13.2 #5 overflow debt. Inserted between tablet and laptop
    # so the default suite still climbs monotonically.
    {"name": "laptop-1280", "width": 1280, "height": 720},
    {"name": "laptop", "width": 1366, "height": 900},
    {"name": "desktop", "width": 1920, "height": 1080},
    # 2560x1440 is the canonical visual baseline. The 1600-high viewport is
    # retained immediately after it as a high-screen cross-check.
    {"name": "desktop-2k", "width": 2560, "height": 1440},
    {"name": "desktop-2k-1600", "width": 2560, "height": 1600},
]


def check_viewport(page, page_id: str, viewport: dict) -> dict:
    """Check a single page at a single viewport size."""
    findings: list[dict] = []

    # Check for horizontal overflow
    scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
    client_width = page.evaluate("() => document.documentElement.clientWidth")
    has_overflow = scroll_width > client_width + 1  # 1px tolerance

    if has_overflow:
        findings.append(
            {
                "check": "horizontal-overflow",
                "severity": "FAIL",
                "detail": f"scrollWidth={scroll_width}px > viewport={client_width}px",
            }
        )

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
        findings.append(
            {
                "check": "content-visible",
                "severity": "WARN",
                "detail": "Real content selector not visible at this viewport",
            }
        )

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
            # Playwright's async path writer intermittently raises EINVAL on
            # Windows/Python 3.14 after writing large full-page PNGs. Keep
            # capture and filesystem I/O separate so the verification result
            # is deterministic and the bytes are written by pathlib.
            screenshot_path.write_bytes(page.screenshot(full_page=True))
            try:
                screenshot_display_path = screenshot_path.relative_to(REPO_ROOT)
            except ValueError:
                screenshot_display_path = screenshot_path
            vp_result["screenshot"] = str(screenshot_display_path)

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


def check_knowledge_overflow_at_1280(page_results: dict) -> dict | None:
    """Dedicated 1280x720 guard for the §13.2 #5 knowledge-base overflow debt.

    The .knowledge-workspace three-rail grid measures exactly
    240 + 720 + 240 + 2x40 gap = 1280px, which is the natural
    regression point. We surface a single WARN line whenever the
    default responsive scan also catches it, but we do NOT upgrade
    to FAIL — that would expand this gate beyond the §13.2 #1
    (token ownership) scope of the current change. Fixing the
    overflow itself is scheduled for the next UI round.
    """
    for vp in page_results.get("viewports", []):
        if vp.get("width") == 1280 and vp.get("height") == 720:
            return {
                "viewport": vp["viewport"],
                "scroll_width": vp["scroll_width"],
                "client_width": vp["client_width"],
                "has_overflow": vp["has_overflow"],
                "note": "design handbook §13.2 #5 — fix scheduled next round",
            }
    return None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Responsive check — multi-viewport overflow + content visibility"
    )
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all)",
    )
    p.add_argument(
        "--viewports",
        default=",".join(v["name"] for v in DEFAULT_VIEWPORTS),
        help="comma-separated viewport names (default: all configured viewports)",
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
            print(
                f"  [{tag}] {vp['viewport']:>10} {vp['width']}x{vp['height']}  "
                f"scrollW={vp['scroll_width']} "
                f"content={'Y' if vp['content_visible'] else 'N'} {overflow}"
            )
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
    print(
        f"responsive: {page_fails} pages with overflow, {total_overflow} total overflow viewports"
    )
    print("=" * 60)

    # Dedicated guard: knowledge-base @ 1280x720. WARN only, not FAIL — fixing
    # the underlying overflow is part of the §13.2 #5 debt scheduled for the
    # next UI round. We surface the finding so the regression cannot silently
    # come back, but we don't block the current token-ownership change on it.
    kb_result = next(
        (r for r in report["per_page"] if r["page_id"] == "knowledge-base"),
        None,
    )
    if kb_result is not None:
        guard = check_knowledge_overflow_at_1280(kb_result)
        if guard is not None and guard["has_overflow"]:
            print(
                f"[KB-1280] knowledge-base overflows at 1280x720 "
                f"(scrollWidth={guard['scroll_width']}px > viewport={guard['client_width']}px) "
                f"— {guard['note']}"
            )
            report.setdefault("kb_1280_overflow", []).append(guard)

    out_log = Path(
        os.getenv(
            "RESPONSIVE_REPORT_PATH",
            str(SCREENSHOT_DIR / "responsive_report.json"),
        )
    )
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        display_path = out_log.relative_to(REPO_ROOT)
    except ValueError:
        display_path = out_log
    print(f"report saved: {display_path}")

    return 1 if page_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
