"""
Content-level instance audit (goes beyond verify_pages.py).

verify_pages.py only proves the *shell* rendered (a selector appeared) with
zero console errors at that instant. It does NOT prove the data rendered:

- it screenshots the moment the first real-content selector appears, which is
  usually mid-fetch (stat cards still "-", tables empty, charts blank);
- it never waits for API settle, so post-fetch re-render errors are missed;
- it never reads the actual values (NaN / 0.00 / 数据不足 markers).

This script waits for network settle + a small settle grace period, then
extracts evidence per page:
  1. console.error / pageerror / failed responses over the FULL lifecycle
  2. placeholder / empty-data markers in visible text (数据不足, 暂无数据,
     加载中, NaN, undefined ...)
  3. Chart.js dataset sizes (a chart is "empty" when all datasets have < 2
     points or zero non-null values)
  4. key stat-card / table evidence (first values) so a human can eyeball
  5. full-page screenshot saved to tests/screenshots/audit/<page>.png

Usage:
  python tests/audit_page_content.py                 # all pages
  python tests/audit_page_content.py --pages ashare-etf,gold-allocation
  python tests/audit_page_content.py --wait-ms 2500  # extra settle grace

Per-page verdict rules (each page must pass ALL applicable checks):
  - no console errors, no pageerrors, no failed responses
  - no empty-data markers in visible text
  - every chart canvas has at least one dataset with >= 2 data points
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = REPO_ROOT / "tests" / "screenshots" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

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

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")

# 空数据 / 半成品渲染的可见标记。命中任一即视为该页内容未渲染完整。
EMPTY_MARKERS = [
    "数据不足",
    "暂无数据",
    "暂无数据源",
    "无数据",
    "加载中",
    "等待数据",
    "warming",
    "预热",
    "NaN",
    "Infinity",
    "undefined",
    "null",
    "--",
]

# 按页覆盖默认标记集 —— 部分页面的领域文本天然包含这些词（知识百科词条
# 正文、btc 页的"数据不足 · 强度"降级标签是设计行为），不能据此判空渲染。
EMPTY_MARKERS_BY_PAGE = {
    "knowledge-base": [
        "加载中",
        "暂无数据",
        "暂无匹配",
        "渲染失败",
        "error",
    ],
    "btc-derivatives": [
        "加载中",
        "暂无数据",
        "NaN",
        "undefined",
        "--",
    ],
}

# 每页必须出现的"硬性内容"证据 selector(与 verify_pages 的壳不同,这些是
# 数据渲染后的承载物:统计卡、表格、列表项)。命中 0 个 = 内容未渲染。
REQUIRED_EVIDENCE = {
    "market-analysis": [
        ".analysis-hero-card", ".realtime-card", ".signal-card", ".status-grid",
    ],
    "monitoring-overview": [
        ".terminal-summary-card", ".monitoring-topbar-grid",
        ".macro-indicator-card", "table tbody tr",
    ],
    "market-structure": [
        ".structure-summary-grid", ".metric-box", ".structure-main-card",
        "table tbody tr",
    ],
    "market-events": [
        ".events-feed-card", ".event-card.event-feed-item",
        ".events-metrics-grid", ".supply-calendar-card",
    ],
    "macro-calendar": [
        "#macro-summary-cards", "#macro-statusbar", ".calendar-grid",
        ".table-wrap table tbody tr",
    ],
    "knowledge-base": [
        ".knowledge-metrics", ".knowledge-card-grid", ".knowledge-card-summary",
        ".knowledge-chip-row",
    ],
    "ashare-etf": [
        "#etf-equity-curve", ".etf-equity-stat", ".etf-plan-summary",
        ".etf-execution-table-card",
    ],
    "btc-derivatives": [
        ".btc-decision-card", ".btc-evidence-layer", ".btc-maturity-ladder",
        ".btc-table-card table tbody tr",
    ],
    "ai-strategy": [
        ".scan-matrix-table", ".scan-cell", ".strategy-scan-page",
        ".strategy-operation-card-title",
    ],
    "gold-allocation": [
        ".gold-workbench-card", ".gold-mini-card", ".gold-price-value",
        ".gold-weight-row",
    ],
}

# 每页图表 canvas 的 id/keys(用于读取 Chart.js dataset 长度)
CHART_CANVASES = {
    "market-analysis": ["analysis-indicator-canvas", "analysis-price-canvas"],
    "monitoring-overview": [],
    "market-structure": ["structure-chart-canvas"],
    "market-events": [],
    "macro-calendar": [],
    "knowledge-base": [],
    "ashare-etf": ["etf-equity-canvas"],
    "btc-derivatives": ["btc-chart-overview"],
    "ai-strategy": [],
    "gold-allocation": ["gold-chart-canvas", "gold-allocation-canvas"],
}


def _visible_text(page: Page) -> str:
    try:
        return page.locator("#page-root").inner_text(timeout=2_000)
    except Exception:
        try:
            return page.locator("body").inner_text(timeout=2_000)
        except Exception:
            return ""


def _collect_chart_evidence(page: Page) -> dict:
    """Read Chart.js registered charts: dataset lengths + non-null point counts."""
    evidence = {}
    try:
        charts = page.evaluate(
            """() => {
              const out = {};
              const registry = window.Chart ? Chart.instances : null;
              if (!registry) return { note: "no Chart.instances" };
              for (const [key, chart] of Object.entries(registry)) {
                if (!chart || !chart.data || !chart.data.datasets) continue;
                // Chart.instances is keyed by numeric id; resolve the real
                // canvas id so per-page CHART_CANVASES matching works.
                const canvasId = (chart.canvas && chart.canvas.id) || key;
                out[canvasId] = chart.data.datasets.map((ds) => {
                  const vals = (ds.data || []).map(Number);
                  const nonNull = vals.filter((v) => Number.isFinite(v) && v !== 0).length;
                  return { n: vals.length, nonNull };
                });
              }
              return out;
            }"""
        )
        evidence["chartjs"] = charts
    except Exception as exc:
        evidence["chartjs_error"] = str(exc)
    # 兜底: canvas 元素是否存在 + 是否已被 Chart.js 接管
    try:
        canvases = page.evaluate(
            """() => {
              const out = {};
              document.querySelectorAll("canvas").forEach((c) => {
                const key = c.id || c.className || c.parentElement?.className || "?";
                out[key] = {
                  present: true,
                  w: c.width,
                  h: c.height,
                  controlled: !!(c.getAttribute("data-chart-js") || c.__chartjs),
                };
              });
              return out;
            }"""
        )
        evidence["canvases"] = canvases
    except Exception as exc:
        evidence["canvases_error"] = str(exc)
    return evidence


def audit_one_page(page: Page, page_id: str, route: str, wait_ms: int) -> dict:
    url = f"{BASE_URL}{route}"
    errors: list[str] = []
    pageerrors: list[str] = []
    failed: list[str] = []

    def on_console(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            errors.append(msg.text)

    def on_pageerror(err: PlaywrightError) -> None:
        pageerrors.append(str(err))

    def on_response(resp) -> None:
        if resp.status >= 400:
            failed.append(f"{resp.status} {resp.request.method} {resp.url}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("response", on_response)

    start = time.monotonic()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        return {"page_id": page_id, "goto": f"failed:{exc}", "ok": False}
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass  # 网络永远不 idle 也是要暴露的问题,继续收集证据
    time.sleep(wait_ms / 1000.0)  # settle grace
    page.wait_for_timeout(300)

    text = _visible_text(page)
    markers = EMPTY_MARKERS_BY_PAGE.get(page_id, EMPTY_MARKERS)
    marker_hits = []
    for m in markers:
        for line in text.splitlines():
            if m in line:
                marker_hits.append(line.strip()[:120])
    # 去重但保序
    seen = set()
    marker_hits = [h for h in marker_hits if not (h in seen or seen.add(h))]

    evidence_rows = {}
    for sel in REQUIRED_EVIDENCE.get(page_id, []):
        try:
            n = page.locator(sel).count()
        except Exception:
            n = -1
        evidence_rows[sel] = n

    # 关键数值:统计卡 / 表格首行文本
    samples: dict[str, list[str]] = {}
    for sel in [".etf-equity-stat", ".etf-plan-summary", ".etf-execution-table-card",
                ".analysis-hero-card", ".realtime-card", ".signal-card",
                ".terminal-summary-card", ".monitoring-topbar-grid",
                ".macro-indicator-card", ".structure-summary-tile", ".metric-box",
                ".events-feed-card", ".event-card.event-feed-item",
                "#macro-summary-cards", "#macro-statusbar",
                ".knowledge-metrics", ".knowledge-card-grid",
                ".btc-decision-card", ".btc-evidence-layer",
                ".gold-workbench-card", ".gold-mini-card"]:
        try:
            loc = page.locator(sel)
            cnt = min(loc.count(), 6)
            if cnt:
                samples[sel] = [
                    (loc.nth(i).inner_text(timeout=800) or "").strip().replace("\n", " | ")[:150]
                    for i in range(cnt)
                ]
        except Exception:
            pass

    charts = _collect_chart_evidence(page)

    # 图表空判定:存在 canvas 且 Chart.js 已接管时,dataset 全为 0 点 / 全 null → 空
    chart_empty = []
    chartjs = charts.get("chartjs") or {}
    for cid in CHART_CANVASES.get(page_id, []):
        found = None
        for key, ds in chartjs.items():
            if cid in key or key in cid:
                found = ds
                break
        if found is None:
            canvases = charts.get("canvases") or {}
            if any(cid in k for k in canvases):
                chart_empty.append(f"{cid}:no-chartjs-instance")
            continue
        if not found or all(ds.get("n", 0) < 2 or ds.get("nonNull", 0) == 0 for ds in found):
            chart_empty.append(f"{cid}:empty")

    dur_ms = (time.monotonic() - start) * 1000.0
    screenshot = AUDIT_DIR / f"{page_id}.png"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
    except Exception:
        pass

    ok = (
        not errors
        and not pageerrors
        and not failed
        and not marker_hits
        and not chart_empty
    )
    return {
        "page_id": page_id,
        "ok": ok,
        "dur_ms": round(dur_ms, 0),
        "console_errors": errors[:5],
        "pageerrors": pageerrors[:5],
        "failed_responses": failed[:8],
        "marker_hits": marker_hits[:8],
        "evidence": evidence_rows,
        "chart_empty": chart_empty,
        "charts": chartjs,
        "samples": samples,
        "screenshot": str(screenshot.relative_to(REPO_ROOT)),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pages", default=",".join(PAGE_ROUTES.keys()))
    p.add_argument("--wait-ms", type=int, default=2500)
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    report = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for pid in page_ids:
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()
            r = audit_one_page(page, pid, PAGE_ROUTES[pid], args.wait_ms)
            report.append(r)
            ctx.close()
        browser.close()

    # 打印
    for r in report:
        tag = "PASS" if r.get("ok") else "FAIL"
        print(f"\n===== [{tag}] {r['page_id']} ({r.get('dur_ms', 0)}ms) =====")
        if r.get("goto"):
            print(f"  goto: {r['goto']}")
        if r.get("console_errors"):
            print(f"  console.errors: {r['console_errors']}")
        if r.get("pageerrors"):
            print(f"  pageerrors: {r['pageerrors']}")
        if r.get("failed_responses"):
            print(f"  failed responses: {r['failed_responses']}")
        if r.get("marker_hits"):
            print(f"  empty markers: {r['marker_hits']}")
        if r.get("chart_empty"):
            print(f"  empty charts: {r['chart_empty']}")
        ev = r.get("evidence", {})
        if ev:
            print("  evidence: " + ", ".join(f"{k}={v}" for k, v in ev.items()))
        charts = r.get("charts") or {}
        if charts:
            parts = []
            for k, ds in charts.items():
                if isinstance(ds, list):
                    inner = ", ".join(
                        "%spts/%snn" % (d.get("n", 0), d.get("nonNull", 0))
                        for d in ds if isinstance(d, dict)
                    )
                    parts.append("%s=[%s]" % (k, inner))
                else:
                    parts.append("%s=%s" % (k, ds))
            print("  chartjs: " + ", ".join(parts))
        for sel, rows in (r.get("samples") or {}).items():
            for row in rows:
                print(f"  [{sel}] {row}")

    n_fail = sum(1 for r in report if not r.get("ok"))
    print("\n" + "=" * 60)
    print(f"audit: {n_fail} / {len(report)} pages FAILED content-level render")
    print("=" * 60)
    out = REPO_ROOT / "tests" / "screenshots" / "audit_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out.relative_to(REPO_ROOT)}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
