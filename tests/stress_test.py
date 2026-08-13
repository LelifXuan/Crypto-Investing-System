"""
Stress test — rapid-click simulation for interaction-heavy pages.

Regular verify_pages.py waits 3-5s between actions and can't catch freezing/loading
issues. This script fires rapid clicks (100-200ms intervals) to reproduce the
real-user experience of switching instruments, timeframes, and refreshing data.

Usage:
    python tests/stress_test.py --page market-structure
    python tests/stress_test.py --page market-analysis
    python tests/stress_test.py --page ai-strategy
    python tests/stress_test.py  # all stress-testable pages

Known issues (2026-08-11):
    - market-structure: rapid instrument/tf switching → blank chart (canvas=0, loading=0)
    - market-analysis: rapid symbol button clicks → loading stuck (loading>0 after 5s)
    - ai-strategy: cold start shows empty workbench, requires manual generate clicks

Regression flow (2026-08-13): while /strategy/scan is still pending, clicking
another SPA page must navigate immediately instead of waiting for the scan.
"""
import argparse
import sys
import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("playwright not installed: pip install playwright", file=sys.stderr)
    sys.exit(2)

import os
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")
VIEWPORT = {"width": 2560, "height": 1440}


def stress_test_strategy_pending_navigation(browser) -> dict:
    """Keep the cold scan pending and verify the SPA can leave immediately."""
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    pageerrors = []
    page.on("pageerror", lambda err: pageerrors.append(str(err)))
    page.add_init_script(
        """
        const realFetch = window.fetch.bind(window);
        window.fetch = (input, init = {}) => {
          const url = String(input?.url || input);
          if (!url.includes('/strategy/scan')) return realFetch(input, init);
          return new Promise((resolve, reject) => {
            const abort = () => reject(new DOMException('Aborted', 'AbortError'));
            if (init.signal?.aborted) abort();
            else init.signal?.addEventListener('abort', abort, { once: true });
          });
        };
        """
    )
    result = {"page_id": "ai-strategy-pending-navigation", "verdict": "PASS", "issues": []}
    try:
        page.goto(f"{BASE_URL}/monitoring-page", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector(
            "#monitoring-topbar, .monitoring-summary-surface",
            timeout=10_000,
        )
        page.locator('[data-page-link="ai-strategy"]').click()
        page.wait_for_selector(".strategy-scan-page", timeout=3_000)
        started = time.perf_counter()
        page.locator('[data-page-link="market-events"]').click()
        page.wait_for_selector(".events-feed-shell", timeout=3_000)
        elapsed_ms = (time.perf_counter() - started) * 1000
        result["navigation_ms"] = round(elapsed_ms, 1)
        result["final_url"] = page.url
        if elapsed_ms >= 3000:
            result["verdict"] = "FAIL"
            result["issues"].append(f"pending-scan navigation took {elapsed_ms:.1f} ms")
        if pageerrors:
            result["verdict"] = "FAIL"
            result["issues"].extend(pageerrors[:10])
    except Exception as error:
        result["verdict"] = "ERROR"
        result["issues"].append(f"Exception: {error}")
    finally:
        ctx.close()
    return result

# Which pages support stress testing and what to click
STRESS_PAGES = {
    "market-structure": {
        "route": "/structure-page",
        "description": "形态结构 — 快速切换标的/时间周期",
        "actions": [
            {
                "type": "dropdown",
                "selector": "[data-dropdown-id='structure-instrument']",
                "items_selector": "[role='listbox'] [role='option']",
                "label": "instrument",
            },
            {
                "type": "dropdown",
                "selector": "[data-dropdown-id='structure-timeframe']",
                "items_selector": "[role='listbox'] [role='option']",
                "label": "timeframe",
            },
        ],
        "expected_canvas": False,  # structure uses <img> not <canvas>
        "expected_img": "img[alt='形态结构图']",
        "check_selector": "img[alt='形态结构图']",
    },
    "market-analysis": {
        "route": "/indicators-page",
        "description": "技术指标 — 快速切换标的按钮 + 刷新",
        "actions": [
            {
                "type": "buttons",
                "selector": "button.symbol-btn, button[class*='instrument'], button[class*='pair']",
                "label": "symbol",
            },
            {
                "type": "click",
                "selector": "button:has-text('刷新分析'), button:has-text('刷新')",
                "label": "refresh",
            },
        ],
        "expected_canvas": True,
        "check_selector": "canvas",
    },
    "ai-strategy": {
        "route": "/strategy-page",
        "description": "AI策略 — 冷启动 + 机会矩阵点击 + 抽拉面板",
        "actions": [
            {
                "type": "click",
                "selector": ".page-guide-fab",
                "label": "guide-fab",
            },
            {
                "type": "matrix-cells",
                "selector": ".scan-cell-btn",
                "label": "matrix-cell",
            },
            {
                "type": "click",
                "selector": "button:has-text('刷新扫描'), button:has-text('刷新')",
                "label": "refresh-scan",
            },
        ],
        "expected_canvas": False,
        "check_selector": "#strategy-detail-panel, [class*='operation'], [class*='strategy-card']",
    },
}


def stress_test_page(browser, page_id: str, config: dict, rapid_clicks: int = 10) -> dict:
    """Run stress test on a single page."""
    result = {
        "page_id": page_id,
        "description": config["description"],
        "actions": [],
        "before": {},
        "after": {},
        "verdict": "PASS",
        "issues": [],
    }

    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    pageerrors = []
    page.on("pageerror", lambda err: pageerrors.append(str(err)))

    try:
        # Load page and wait for initial content
        page.goto(f"{BASE_URL}{config['route']}", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4000)

        # Capture initial state
        before_state = _get_page_state(page, config)
        result["before"] = before_state

        # --- RAPID CLICKING ---
        for action_cfg in config["actions"]:
            action_type = action_cfg["type"]
            label = action_cfg["label"]

            if action_type == "dropdown":
                _rapid_dropdown_switch(page, action_cfg, rapid_clicks, result)
            elif action_cfg["type"] == "buttons":
                _rapid_buttons_click(page, action_cfg, rapid_clicks, result)
            elif action_cfg["type"] == "click":
                _rapid_click(page, action_cfg, rapid_clicks, result)
            elif action_cfg["type"] == "matrix-cells":
                _rapid_matrix_cells(page, action_cfg, rapid_clicks, result)

        # Wait for debounce + potential async settle
        # Pages with debouncing need: debounce_delay (300ms) + API_timeout
        page.wait_for_timeout(8000)

        # Capture final state
        after_state = _get_page_state(page, config)
        result["after"] = after_state

        # --- ISSUE DETECTION ---
        _detect_issues(result, before_state, after_state, config)

        result["console_errors"] = console_errors[:10]
        result["pageerrors"] = pageerrors[:10]

    except Exception as e:
        result["verdict"] = "ERROR"
        result["issues"].append(f"Exception: {e}")
    finally:
        ctx.close()

    return result


def _get_page_state(page, config: dict) -> dict:
    """Capture current page state for comparison."""
    return page.evaluate(
        """(checkSel) => {
            var loading = document.querySelectorAll('[class*="loading"], [class*="spinner"], [class*="skeleton"]').length;
            var canvas = document.querySelectorAll('canvas').length;
            var checkEl = checkSel ? document.querySelector(checkSel) : null;
            var heading = document.querySelector('h2');
            return {
                loading: loading,
                canvas: canvas,
                checkVisible: checkEl ? checkEl.offsetParent !== null : null,
                heading: heading ? heading.textContent.trim().substring(0, 40) : 'N/A'
            };
        }""",
        config.get("check_selector"),
    )


def _rapid_dropdown_switch(page, action_cfg: dict, count: int, result: dict):
    """Rapidly switch between dropdown items.

    2026-08-11: pages now debounce dropdown changes (300ms delay). The stress
    test must wait for the debounce to fire before opening the next dropdown,
    otherwise the dropdown closes before the debounce fires.
    """
    selector = action_cfg["selector"]
    items_selector = action_cfg["items_selector"]
    label = action_cfg["label"]

    # First, get available items
    try:
        page.click(selector, timeout=3000)
        page.wait_for_timeout(300)
        items = page.query_selector_all(items_selector)
        if not items:
            result["actions"].append({"label": label, "status": "no-items-found"})
            return
    except PWTimeout:
        result["actions"].append({"label": label, "status": "dropdown-not-found"})
        return

    item_count = len(items)

    # Rapidly switch through items (cycle back to start)
    # With debounce: click item → wait for debounce (300ms) → open dropdown → repeat
    for i in range(min(count, item_count * 2)):
        try:
            t0 = time.monotonic()
            # Click item
            items[i % item_count].click(timeout=2000)
            elapsed = (time.monotonic() - t0) * 1000

            # Wait for debounce to fire (300ms) + settle time
            page.wait_for_timeout(400)

            # Re-open dropdown for next iteration
            if i < min(count, item_count * 2) - 1:
                try:
                    page.click(selector, timeout=2000)
                    page.wait_for_timeout(200)
                    # Refresh item handles (DOM may have changed)
                    items = page.query_selector_all(items_selector)
                    if not items:
                        break
                except Exception:
                    break

            result["actions"].append({
                "label": f"{label}[{i}]",
                "ms": round(elapsed, 1),
                "ok": True,
            })
        except Exception as e:
            result["actions"].append({
                "label": f"{label}[{i}]",
                "ok": False,
                "error": str(e)[:80],
            })


def _rapid_buttons_click(page, action_cfg: dict, count: int, result: dict):
    """Rapidly click a group of buttons (e.g., symbol selector buttons)."""
    selector = action_cfg["selector"]
    label = action_cfg["label"]

    buttons = page.query_selector_all(selector)
    if not buttons:
        # Fallback: try to find any clickable elements in the control bar
        result["actions"].append({"label": label, "status": "buttons-not-found", "selector": selector})
        return

    btn_count = len(buttons)
    for i in range(min(count, btn_count * 2)):
        try:
            t0 = time.monotonic()
            buttons[i % btn_count].click(timeout=2000)
            elapsed = (time.monotonic() - t0) * 1000
            page.wait_for_timeout(100)  # very rapid

            # Refresh handles
            buttons = page.query_selector_all(selector)
            if not buttons:
                break

            result["actions"].append({
                "label": f"{label}[{i % btn_count}]",
                "ms": round(elapsed, 1),
                "ok": True,
            })
        except Exception as e:
            result["actions"].append({
                "label": f"{label}[{i}]",
                "ok": False,
                "error": str(e)[:80],
            })


def _rapid_click(page, action_cfg: dict, count: int, result: dict):
    """Rapidly click the same element multiple times."""
    selector = action_cfg["selector"]
    label = action_cfg["label"]

    for i in range(count):
        try:
            t0 = time.monotonic()
            page.click(selector, timeout=2000)
            elapsed = (time.monotonic() - t0) * 1000
            page.wait_for_timeout(80)  # extremely rapid

            result["actions"].append({
                "label": f"{label}[{i}]",
                "ms": round(elapsed, 1),
                "ok": True,
            })
        except Exception as e:
            result["actions"].append({
                "label": f"{label}[{i}]",
                "ok": False,
                "error": str(e)[:80],
            })


def _rapid_matrix_cells(page, action_cfg: dict, count: int, result: dict):
    """Click matrix cells to open strategy detail panel, then close and repeat.

    For AI strategy page: each .scan-cell-btn should open a #strategy-detail-panel
    slide-in drawer. We click a cell, wait for the panel to appear, check its
    state, then close it and click the next cell.
    """
    selector = action_cfg["selector"]
    label = action_cfg["label"]

    cells = page.query_selector_all(f"{selector}:not([disabled])")
    if not cells:
        result["actions"].append({"label": label, "status": "matrix-cells-not-found"})
        return

    cell_count = len(cells)
    issues = []

    for i in range(min(count, cell_count)):
        try:
            # A persisted page guide may be open and cover the first matrix
            # cells. Close it before testing the matrix workflow itself.
            guide = page.query_selector(".page-guide-fab[aria-expanded='true']")
            if guide:
                guide.click(timeout=2000)
                page.wait_for_timeout(250)
            t0 = time.monotonic()
            cells[i].click(timeout=3000)
            page.wait_for_timeout(500)

            # Check if detail panel opened
            panel = page.query_selector("#strategy-detail-panel")
            panel_open = panel is not None
            loading = page.query_selector_all('[class*="loading"], [class*="spinner"]')
            loading_count = len(loading)

            # Check for degraded/invalid data indicators
            body_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
            has_invalid_prices = "价位缺失" in body_text or "几何关系无效" in body_text
            has_zero_rr = "盈亏比 0:1" in body_text

            elapsed = (time.monotonic() - t0) * 1000

            action_result = {
                "label": f"{label}[{i}]",
                "ms": round(elapsed, 1),
                "ok": True,
                "panelOpened": panel_open,
                "loading": loading_count,
            }
            if has_invalid_prices:
                action_result["invalidPrices"] = True
                issues.append(f"Cell {i}: 价位缺失/几何关系无效")
            if has_zero_rr:
                action_result["zeroRiskReward"] = True
                issues.append(f"Cell {i}: 盈亏比 0:1")

            result["actions"].append(action_result)

            # Close panel before next cell
            if panel_open:
                close_btn = page.query_selector("#strategy-detail-close")
                if close_btn:
                    page.evaluate("() => document.querySelector('#strategy-detail-close')?.click()")
                    page.wait_for_selector("#strategy-detail-overlay", state="detached", timeout=2000)
                cells = page.query_selector_all(f"{selector}:not([disabled])")

        except Exception as e:
            result["actions"].append({
                "label": f"{label}[{i}]",
                "ok": False,
                "error": str(e)[:80],
            })

    if issues:
        result.setdefault("matrix_issues", []).extend(issues)


def _detect_issues(result: dict, before: dict, after: dict, config: dict):
    """Detect known stress-test issues by comparing before/after states."""
    issues = []

    # Issue 1: Loading stuck (loading count > 0 after 5s settle)
    if after.get("loading", 0) > before.get("loading", 0):
        issues.append(
            f"LOADING_STUCK: loading={after['loading']} after 5s settle "
            f"(was {before.get('loading', 0)} before stress test)"
        )
        result["verdict"] = "FAIL"

    # Issue 2: Canvas/chart disappeared
    if config.get("expected_canvas") and after.get("canvas", 0) == 0 and before.get("canvas", 0) > 0:
        issues.append(
            f"CHART_VANISHED: canvas went from {before['canvas']} to 0 after rapid switching"
        )
        result["verdict"] = "FAIL"

    # Issue 3: A previously visible stable element disappeared. Optional
    # surfaces such as a closed detail drawer are allowed to be absent both
    # before and after the interaction sequence.
    if config.get("check_selector") and before.get("checkVisible") is True and after.get("checkVisible") is False:
        issues.append(
            f"CHECK_ELEMENT_HIDDEN: '{config['check_selector']}' not visible after stress test"
        )
        result["verdict"] = "FAIL"

    # Issue 4: High latency on individual actions (> 2s per click)
    slow_actions = [a for a in result["actions"] if a.get("ok") and a.get("ms", 0) > 2000]
    if slow_actions:
        issues.append(
            f"SLOW_RESPONSE: {len(slow_actions)} actions took > 2000ms "
            f"(max: {max(a['ms'] for a in slow_actions):.0f}ms)"
        )
        if result["verdict"] == "PASS":
            result["verdict"] = "WARN"

    # Issue 5: Failed actions
    failed_actions = [a for a in result["actions"] if a.get("ok") is False]
    if failed_actions:
        issues.append(
            f"ACTION_FAILED: {len(failed_actions)}/{len(result['actions'])} actions failed "
            f"(first error: {failed_actions[0].get('error', 'unknown')})"
        )
        result["verdict"] = "FAIL"

    # Issue 6: Matrix cell data invalid (AI strategy page)
    matrix_issues = result.get("matrix_issues", [])
    if matrix_issues:
        invalid_cells = [a for a in result["actions"] if a.get("invalidPrices") or a.get("zeroRiskReward")]
        issues.append(
            f"INVALID_STRATEGY_DATA: {len(invalid_cells)}/{len(result['actions'])} cells "
            f"show invalid prices or 0:1 risk/reward"
        )
        result["verdict"] = "FAIL"

    # Issue 7: Matrix cell panel not opening
    panel_actions = [a for a in result["actions"] if "panelOpened" in a]
    if panel_actions:
        not_opened = [a for a in panel_actions if not a["panelOpened"]]
        if not_opened:
            issues.append(
                f"PANEL_NOT_OPENING: {len(not_opened)}/{len(panel_actions)} cell clicks "
                f"did not open strategy detail panel"
            )
            result["verdict"] = "FAIL"

    result["issues"] = issues


def main():
    parser = argparse.ArgumentParser(
        description="Stress test — rapid-click simulation for interaction-heavy pages"
    )
    parser.add_argument(
        "--pages",
        default=",".join(STRESS_PAGES.keys()),
        help=f"comma-separated page IDs (default: all). Available: {', '.join(STRESS_PAGES.keys())}",
    )
    parser.add_argument(
        "--rapid-clicks",
        type=int,
        default=10,
        help="number of rapid clicks per action (default: 10)",
    )
    parser.add_argument(
        "--viewport",
        default="2560x1440",
        help="viewport as WxH (default: 2560x1440)",
    )
    args = parser.parse_args()

    page_ids = [s.strip() for s in args.pages.split(",") if s.strip()]
    for pid in page_ids:
        if pid not in STRESS_PAGES:
            print(f"unknown page_id: {pid} (available: {', '.join(STRESS_PAGES.keys())})", file=sys.stderr)
            return 2

    # Parse viewport
    try:
        vp_w, vp_h = args.viewport.lower().split("x")
        viewport = {"width": int(vp_w), "height": int(vp_h)}
    except ValueError:
        print(f"invalid viewport: {args.viewport}", file=sys.stderr)
        return 2

    report = {
        "viewport": viewport,
        "rapid_clicks": args.rapid_clicks,
        "per_page": [],
        "summary": {},
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for pid in page_ids:
            config = STRESS_PAGES[pid]
            print(f"[stress] {pid}: {config['description']} ...", end=" ", flush=True)

            result = stress_test_page(browser, pid, config, args.rapid_clicks)

            tag = result["verdict"]
            issue_summary = ""
            if result["issues"]:
                issue_summary = f" issues={len(result['issues'])}"
            action_count = len(result["actions"])
            fail_count = len([a for a in result["actions"] if not a.get("ok")])

            print(f"{tag}  actions={action_count} failed={fail_count}{issue_summary}")

            for issue in result["issues"]:
                print(f"  ⚠ {issue}")

            report["per_page"].append(result)

            if pid == "ai-strategy":
                print("[stress] ai-strategy: pending scan -> SPA exit ...", end=" ", flush=True)
                navigation_result = stress_test_strategy_pending_navigation(browser)
                print(
                    f"{navigation_result['verdict']}  "
                    f"navigation={navigation_result.get('navigation_ms', 'n/a')}ms"
                )
                for issue in navigation_result["issues"]:
                    print(f"  !! {issue}")
                report["per_page"].append(navigation_result)

    # Summary
    fail_count = len([r for r in report["per_page"] if r["verdict"] in {"FAIL", "ERROR"}])
    warn_count = len([r for r in report["per_page"] if r["verdict"] == "WARN"])
    pass_count = len([r for r in report["per_page"] if r["verdict"] == "PASS"])

    report["summary"] = {
        "total": len(report["per_page"]),
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
        "verdict": "FAIL" if fail_count > 0 else "WARN" if warn_count > 0 else "PASS",
    }

    print(f"\n[stress] summary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
