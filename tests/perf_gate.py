"""
Performance gate — long tasks, LCP, CLS, bundle size, DOM complexity.

Capability: P1-B (Performance Gate)
Collects performance metrics via Playwright's Performance API + resource timing.

Checks per page:
  1. Long Task duration (> 100ms WARN, > 200ms FAIL)
  2. DOM node count (> 3000 WARN, > 5000 FAIL)
  3. LCP — Largest Contentful Paint (> 2.5s WARN, > 4s FAIL)
  4. CLS — Cumulative Layout Shift (> 0.1 WARN, > 0.25 FAIL)
  5. FCP — First Contentful Paint (> 1.8s WARN, > 3s FAIL)
  6. JS bundle total size (> 500KB WARN, > 1MB FAIL)
  7. CSS file size (> 200KB WARN, > 500KB FAIL)
  8. Total HTTP requests (> 50 WARN, > 100 FAIL)

Usage:
  python tests/perf_gate.py --pages all
  python tests/perf_gate.py --pages monitoring-overview --threshold-lcp 3.0
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
STATIC_DIR = REPO_ROOT / "app" / "static"

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

# Thresholds
DEFAULT_THRESHOLDS = {
    "long_task_warn": 100,    # ms
    "long_task_fail": 200,    # ms
    "dom_nodes_warn": 3000,
    "dom_nodes_fail": 5000,
    "lcp_warn": 2500,         # ms
    "lcp_fail": 4000,         # ms
    "cls_warn": 0.1,
    "cls_fail": 0.25,
    "fcp_warn": 1800,         # ms
    "fcp_fail": 3000,         # ms
    "js_size_warn": 500,      # KB
    "js_size_fail": 1000,     # KB
    "css_size_warn": 200,     # KB
    "css_size_fail": 500,     # KB
    "requests_warn": 50,
    "requests_fail": 100,
}


def scan_page(page, page_id: str, thresholds: dict) -> dict:
    """Collect performance metrics for a single page."""
    findings: list[dict] = []

    # Inject long task observer
    page.add_init_script(
        """
        window.__perfLongTasks = [];
        window.__perfCLS = 0;
        window.__perfLCP = 0;
        window.__perfFCP = 0;
        if (typeof PerformanceObserver !== "undefined") {
          try {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) {
                window.__perfLongTasks.push(entry.duration);
              }
            }).observe({ type: "longtask", buffered: true });
          } catch (_) {}
          try {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) {
                if (entry.value > window.__perfCLS) window.__perfLCP = entry.value;
              }
            }).observe({ type: "largest-contentful-paint", buffered: true });
          } catch (_) {}
          try {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) {
                window.__perfCLS += entry.value;
              }
            }).observe({ type: "layout-shift", buffered: true });
          } catch (_) {}
          try {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) {
                if (entry.name === "first-contentful-paint") {
                  window.__perfFCP = entry.startTime;
                }
              }
            }).observe({ type: "paint", buffered: true });
          } catch (_) {}
        }
        """
    )

    page.goto(f"{BASE_URL}{PAGE_ROUTES[page_id]}", wait_until="domcontentloaded", timeout=30_000)

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

    page.wait_for_timeout(2000)  # extra settle for LCP

    # Collect metrics
    metrics = page.evaluate("""() => {
      const longTasks = window.__perfLongTasks || [];
      const resources = performance.getEntriesByType('resource');
      const domNodes = document.querySelectorAll('*').length;
      const jsResources = resources.filter(r => r.name.endsWith('.js') || r.initiatorType === 'script');
      const cssResources = resources.filter(r => r.name.endsWith('.css') || r.initiatorType === 'stylesheet');
      const totalJsSize = jsResources.reduce((sum, r) => sum + (r.transferSize || 0), 0);
      const totalCssSize = cssResources.reduce((sum, r) => sum + (r.transferSize || 0), 0);

      return {
        longTaskMax: Math.max(0, ...longTasks),
        longTaskCount: longTasks.length,
        domNodes,
        lcp: window.__perfLCP || 0,
        cls: window.__perfCLS || 0,
        fcp: window.__perfFCP || 0,
        totalJsSize,
        totalCssSize,
        jsResourceCount: jsResources.length,
        cssResourceCount: cssResources.length,
        totalRequests: resources.length,
      };
    }""")

    # Evaluate against thresholds
    # 1. Long Task
    lt = metrics["longTaskMax"]
    if lt > thresholds["long_task_fail"]:
        findings.append({"check": "long-task", "severity": "FAIL", "detail": f"Max long task: {lt:.0f}ms > {thresholds['long_task_fail']}ms"})
    elif lt > thresholds["long_task_warn"]:
        findings.append({"check": "long-task", "severity": "WARN", "detail": f"Max long task: {lt:.0f}ms > {thresholds['long_task_warn']}ms"})

    # 2. DOM nodes
    dn = metrics["domNodes"]
    if dn > thresholds["dom_nodes_fail"]:
        findings.append({"check": "dom-nodes", "severity": "FAIL", "detail": f"DOM nodes: {dn} > {thresholds['dom_nodes_fail']}"})
    elif dn > thresholds["dom_nodes_warn"]:
        findings.append({"check": "dom-nodes", "severity": "WARN", "detail": f"DOM nodes: {dn} > {thresholds['dom_nodes_warn']}"})

    # 3. LCP
    lcp = metrics["lcp"]
    if lcp > thresholds["lcp_fail"]:
        findings.append({"check": "lcp", "severity": "FAIL", "detail": f"LCP: {lcp:.0f}ms > {thresholds['lcp_fail']}ms"})
    elif lcp > thresholds["lcp_warn"]:
        findings.append({"check": "lcp", "severity": "WARN", "detail": f"LCP: {lcp:.0f}ms > {thresholds['lcp_warn']}ms"})

    # 4. CLS
    cls = metrics["cls"]
    if cls > thresholds["cls_fail"]:
        findings.append({"check": "cls", "severity": "FAIL", "detail": f"CLS: {cls:.3f} > {thresholds['cls_fail']}"})
    elif cls > thresholds["cls_warn"]:
        findings.append({"check": "cls", "severity": "WARN", "detail": f"CLS: {cls:.3f} > {thresholds['cls_warn']}"})

    # 5. FCP
    fcp = metrics["fcp"]
    if fcp > thresholds["fcp_fail"]:
        findings.append({"check": "fcp", "severity": "FAIL", "detail": f"FCP: {fcp:.0f}ms > {thresholds['fcp_fail']}ms"})
    elif fcp > thresholds["fcp_warn"]:
        findings.append({"check": "fcp", "severity": "WARN", "detail": f"FCP: {fcp:.0f}ms > {thresholds['fcp_warn']}ms"})

    # 6. JS size
    js_kb = metrics["totalJsSize"] / 1024
    if js_kb > thresholds["js_size_fail"]:
        findings.append({"check": "js-size", "severity": "FAIL", "detail": f"JS: {js_kb:.0f}KB > {thresholds['js_size_fail']}KB"})
    elif js_kb > thresholds["js_size_warn"]:
        findings.append({"check": "js-size", "severity": "WARN", "detail": f"JS: {js_kb:.0f}KB > {thresholds['js_size_warn']}KB"})

    # 7. CSS size
    css_kb = metrics["totalCssSize"] / 1024
    if css_kb > thresholds["css_size_fail"]:
        findings.append({"check": "css-size", "severity": "FAIL", "detail": f"CSS: {css_kb:.0f}KB > {thresholds['css_size_fail']}KB"})
    elif css_kb > thresholds["css_size_warn"]:
        findings.append({"check": "css-size", "severity": "WARN", "detail": f"CSS: {css_kb:.0f}KB > {thresholds['css_size_warn']}KB"})

    # 8. Requests
    req = metrics["totalRequests"]
    if req > thresholds["requests_fail"]:
        findings.append({"check": "requests", "severity": "FAIL", "detail": f"Requests: {req} > {thresholds['requests_fail']}"})
    elif req > thresholds["requests_warn"]:
        findings.append({"check": "requests", "severity": "WARN", "detail": f"Requests: {req} > {thresholds['requests_warn']}"})

    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")

    return {
        "page_id": page_id,
        "metrics": {
            "long_task_max_ms": round(lt, 1),
            "long_task_count": metrics["longTaskCount"],
            "dom_nodes": dn,
            "lcp_ms": round(lcp, 1),
            "cls": round(cls, 4),
            "fcp_ms": round(fcp, 1),
            "js_size_kb": round(js_kb, 1),
            "css_size_kb": round(css_kb, 1),
            "total_requests": req,
        },
        "findings": findings,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "verdict": "FAIL" if fail_count > 0 else "WARN" if warn_count > 0 else "PASS",
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Performance gate — long tasks, LCP, CLS, bundle size")
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all)",
    )
    p.add_argument("--threshold-lcp", type=float, help="LCP warn threshold ms")
    p.add_argument("--threshold-cls", type=float, help="CLS warn threshold")
    p.add_argument("--threshold-long-task", type=float, help="Long task warn threshold ms")
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    # Build thresholds (allow CLI overrides)
    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.threshold_lcp:
        thresholds["lcp_warn"] = args.threshold_lcp
    if args.threshold_cls:
        thresholds["cls_warn"] = args.threshold_cls
    if args.threshold_long_task:
        thresholds["long_task_warn"] = args.threshold_long_task

    report = {"thresholds": thresholds, "per_page": [], "summary": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for pid in page_ids:
            print(f"[perf] measuring {pid} ...", end=" ", flush=True)
            ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
            page = ctx.new_page()
            result = scan_page(page, pid, thresholds)
            tag = result["verdict"]
            m = result["metrics"]
            print(f"{tag}  LCP={m['lcp_ms']:.0f}ms CLS={m['cls']:.3f} "
                  f"DOM={m['dom_nodes']} JS={m['js_size_kb']:.0f}KB "
                  f"longtask={m['long_task_max_ms']:.0f}ms")
            report["per_page"].append(result)
            ctx.close()

        browser.close()

    # Summary
    total_fail = sum(r["fail_count"] for r in report["per_page"])
    total_warn = sum(r["warn_count"] for r in report["per_page"])
    page_fails = sum(1 for r in report["per_page"] if r["verdict"] == "FAIL")
    page_warns = sum(1 for r in report["per_page"] if r["verdict"] == "WARN")
    report["summary"] = {
        "total_pages": len(report["per_page"]),
        "pages_with_fails": page_fails,
        "pages_with_warns": page_warns,
        "total_fail_findings": total_fail,
        "total_warn_findings": total_warn,
    }

    print()
    print("=" * 60)
    print(f"perf gate: {page_fails} FAIL, {page_warns} WARN pages | "
          f"{total_fail} fails, {total_warn} warns total")
    print("=" * 60)

    out_log = SCREENSHOT_DIR / "perf_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    return 1 if page_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
