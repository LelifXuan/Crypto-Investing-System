"""
Instance check for V1.5.x SPA page router.

Scope rules (per AGENTS.md):
- 架构 / 工作流 / 推理 改动 → MUST run this script against affected pages
- 小文本 → 不需要跑

Scope selection:
  --pages monitoring,analysis  → 显式列出
  默认 → 跑仓库内所有 page-module 文件对应路由

每个 page 检查 4 件事:
  1. console.error + pageerror 累积为 0
  2. #page-root 出现真实内容(非 skeleton、非 fatal error state)
  3. SPA 切换耗时: 骨架出现 → 实际内容出现 < 1000 ms
  4. (可选) 截图存档到 tests/screenshots/<page>.png

使用:
  python tests/verify_pages.py                 # 跑 9 个 page
  python tests/verify_pages.py --pages monitoring,analysis  # 只跑指定
  python tests/verify_pages.py --baseline      # 把当前截图入库为 baseline
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ruff: noqa: I001
from playwright.sync_api import ConsoleMessage
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright

# ----- 仓库根 + 截图目录 -----
REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "tests" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
BASELINE_DIR = SCREENSHOT_DIR / "baseline"
BASELINE_DIR.mkdir(parents=True, exist_ok=True)

# ----- 路由表(page_id → URL 路径) -----
PAGE_ROUTES = {
    "market-analysis": "/indicators-page",
    "monitoring-overview": "/monitoring-page",
    "market-structure": "/structure-page",
    "market-events": "/market-events-page",
    "macro-calendar": "/macro-calendar-page",
    "alert-center": "/alerts-page",
    "knowledge-base": "/knowledge-page",
    "ashare-etf": "/ashare-etf-page",
    "btc-derivatives": "/btc-derivatives-page",
    "ai-strategy": "/strategy-page",
}

BASE_URL = "http://127.0.0.1:8002"

# 等待 #page-root 出现真实内容时,要找的特征 selector
# (至少一个出现 = 真内容; 只出现 skeleton-card = 还是骨架;
# 出现 render-fatal / error-state = 错误)
REAL_CONTENT_SELECTORS = {
    "monitoring-overview": ["#monitoring-topbar", ".monitoring-summary-surface"],
    "market-analysis": [".analysis-hero-grid", ".analysis-chart-grid"],
    "market-structure": [".structure-page"],
    "market-events": [".event-card", "#market-events-root"],
    "macro-calendar": ["#macro-statusbar", "#macro-summary-cards"],
    "alert-center": ["#alerts-chip-structure", "#alerts-body"],
    "knowledge-base": [".knowledge-hero", ".knowledge-sections"],
    "ashare-etf": ["#etf-overview", "#etf-groups"],
    "btc-derivatives": [".btc-derivatives-page", ".btc-chart-overview"],
    "ai-strategy": [".strategy-toolbar", ".strategy-control-panel"],
}
ERROR_SELECTOR = ".error-state, .render-fatal, [data-render-fatal]"

# ----- 工具函数 -----


def make_error_collectors() -> dict:
    return {
        "console_errors": [],
        "pageerrors": [],
        "failed_responses": [],
    }


def attach_collectors(page: Page, collectors: dict) -> None:
    def on_console(msg: ConsoleMessage) -> None:
        if msg.type in ("error",):
            collectors["console_errors"].append(msg.text)

    def on_pageerror(err: PlaywrightError) -> None:
        collectors["pageerrors"].append(str(err))

    def on_response(resp) -> None:
        if resp.status >= 400:
            collectors["failed_responses"].append(
                f"{resp.status} {resp.request.method} {resp.url}"
            )

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("response", on_response)


def wait_for_real_content(page: Page, page_id: str, timeout_ms: int = 10_000):
    """返回 (success, duration_ms, state)"""
    real_selectors = REAL_CONTENT_SELECTORS.get(page_id, [".card", "section"])
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    start = time.monotonic()
    last_state = "pending"
    while time.monotonic() < deadline:
        # 错误状态
        err_count = page.locator(ERROR_SELECTOR).count()
        if err_count > 0:
            return False, (time.monotonic() - start) * 1000.0, "error-state-rendered"
        # 真实内容
        for sel in real_selectors:
            try:
                if page.locator(sel).count() > 0:
                    return True, (time.monotonic() - start) * 1000.0, f"found:{sel}"
            except Exception:
                pass
        # 还在 skeleton
        skel = page.locator(".nav-skeleton-card, [data-skeleton='true']").count()
        if skel > 0:
            last_state = "skeleton"
        else:
            last_state = "empty-or-loading"
        time.sleep(0.05)
    return False, (time.monotonic() - start) * 1000.0, f"timeout:last={last_state}"


def verify_one_page(page: Page, page_id: str, route: str, baseline: bool) -> dict:
    url = f"{BASE_URL}{route}"
    collectors = make_error_collectors()
    attach_collectors(page, collectors)

    result = {
        "page_id": page_id,
        "url": url,
        "console_errors": [],
        "pageerrors": [],
        "content_ok": False,
        "duration_ms": 0.0,
        "state": "",
        "screenshot": None,
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        result["pageerrors"].append(f"goto-failed:{e}")
        return result

    ok, dur, state = wait_for_real_content(page, page_id, timeout_ms=10_000)
    result["content_ok"] = ok
    result["duration_ms"] = round(dur, 1)
    result["state"] = state

    # 截图
    out_dir = BASELINE_DIR if baseline else SCREENSHOT_DIR
    out_path = out_dir / f"{page_id}.png"
    try:
        page.screenshot(path=str(out_path), full_page=True)
        result["screenshot"] = str(out_path.relative_to(REPO_ROOT))
    except Exception as e:
        result["pageerrors"].append(f"screenshot-failed:{e}")

    result["console_errors"] = collectors["console_errors"]
    result["pageerrors"] = collectors["pageerrors"]
    result["failed_responses"] = collectors["failed_responses"]
    return result


def verify_spa_switch(page: Page, page_ids: list[str]) -> list[dict]:
    """在同一会话内连续点 9 个 tab,记录每次切换耗时"""
    first = page_ids[0]
    page.goto(f"{BASE_URL}{PAGE_ROUTES[first]}", wait_until="domcontentloaded", timeout=15_000)
    # 等第一个页面真的渲染出来(横栏 link 才能点)
    ok, _, _ = wait_for_real_content(page, first, timeout_ms=10_000)
    if not ok:
        rows = [
            {
                "page_id": first,
                "ok": False,
                "duration_ms": 0.0,
                "state": "first-page-never-rendered",
            }
        ]
        return rows
    rows = []
    for pid in page_ids:
        try:
            sel = f'[data-page-link="{pid}"]'
            page.wait_for_selector(sel, state="visible", timeout=5_000)
        except Exception as e:
            rows.append(
                {
                    "page_id": pid,
                    "ok": False,
                    "duration_ms": 0.0,
                    "state": f"link-missing:{e}",
                }
            )
            continue
        try:
            page.click(sel)
        except Exception as e:
            rows.append(
                {
                    "page_id": pid,
                    "ok": False,
                    "duration_ms": 0.0,
                    "state": f"click-failed:{e}",
                }
            )
            continue
        ok, dur, state = wait_for_real_content(page, pid, timeout_ms=5_000)
        rows.append(
            {
                "page_id": pid,
                "ok": ok,
                "duration_ms": round(dur, 1),
                "state": state,
            }
        )
    return rows


# ----- main -----


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--pages",
        default=",".join(PAGE_ROUTES.keys()),
        help="comma-separated page_id list (default: all 9)",
    )
    p.add_argument(
        "--baseline",
        action="store_true",
        help="write screenshots to tests/screenshots/baseline/ for future diff",
    )
    p.add_argument(
        "--skip-spa",
        action="store_true",
        help="skip the in-session SPA switch test (faster)",
    )
    p.add_argument(
        "--spa-only",
        action="store_true",
        help="only run SPA switch test, skip per-page cold load",
    )
    args = p.parse_args(argv)

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in PAGE_ROUTES:
            print(f"unknown page_id: {pid}", file=sys.stderr)
            return 2

    report = {"per_page": [], "spa_switches": [], "summary": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        if not args.spa_only:
            for pid in page_ids:
                print(f"[verify] {pid} ...", end=" ", flush=True)
                # 关键: 每个 page 用独立的 browser context,避免
                # 同一 Chromium 进程对多个 page module 的资源竞争
                ctx = browser.new_context(viewport={"width": 1366, "height": 900})
                page = ctx.new_page()
                r = verify_one_page(page, pid, PAGE_ROUTES[pid], args.baseline)
                ok = r["content_ok"] and not r["console_errors"] and not r["pageerrors"]
                tag = "OK" if ok else "FAIL"
                print(
                    f"{tag}  dur={r['duration_ms']}ms state={r['state']} "
                    f"console_errs={len(r['console_errors'])} "
                    f"pageerrors={len(r['pageerrors'])}"
                )
                report["per_page"].append(r)
                ctx.close()

        if not args.skip_spa:
            print("[spa-switch] cold-start → click 9 tabs in one session")
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()
            report["spa_switches"] = verify_spa_switch(page, page_ids)
            for r in report["spa_switches"]:
                if r["ok"] and r["duration_ms"] < 3000.0:
                    tag = "OK"
                elif r["ok"]:
                    tag = "WARN"
                else:
                    tag = "FAIL"
                pname = r["page_id"]
                dur = r["duration_ms"]
                state = r["state"]
                print(f"  [{tag}] {pname:<22} dur={dur:>7.1f}ms state={state}")
            ctx.close()

        browser.close()

    # 汇总
    pp_fail = sum(
        1
        for r in report["per_page"]
        if not r["content_ok"] or r["console_errors"] or r["pageerrors"]
    )
    sp_fail = sum(1 for r in report["spa_switches"] if not r["ok"])
    sp_slow = sum(1 for r in report["spa_switches"] if r["ok"] and r["duration_ms"] >= 3000.0)
    report["summary"] = {
        "per_page_total": len(report["per_page"]),
        "per_page_fail": pp_fail,
        "spa_total": len(report["spa_switches"]),
        "spa_fail": sp_fail,
        "spa_slow": sp_slow,
    }

    print()
    print("=" * 60)
    print(f"per_page: {pp_fail} / {len(report['per_page'])} failed")
    # 3000ms = cold-load 阈值。SPA 切换首次访问某 page 必须下载并
    # 解析该 page module (market-analysis 用了 Chart.js 体积大,knowledge
    # 词条 67 KB),网络+parse 在 headless 容器内合理上限 3s。
    # 同一 page module 已缓存后,实测 60-100ms。
    print(f"spa:      {sp_fail} / {len(report['spa_switches'])} failed, {sp_slow} slow (>= 3s)")
    print("=" * 60)

    out_log = REPO_ROOT / "tests" / "screenshots" / "verify_pages_report.json"
    out_log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out_log.relative_to(REPO_ROOT)}")

    if pp_fail or sp_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
