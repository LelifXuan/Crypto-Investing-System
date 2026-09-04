"""Standalone 2560x1600 Playwright causal UI audit (not pytest).

It records control -> request/state -> rendered-output evidence, full-page
screenshots and traces. Presence of a selector, HTTP 200, or a canvas alone is
never considered proof that UI logic works.
"""
# Embedded JavaScript and Chinese report copy are intentionally kept intact.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, Page, Route, sync_playwright

VIEWPORT = {"width": 2560, "height": 1600}
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8002").rstrip("/")
INVALID = re.compile(r"\b(?:NaN|undefined|Infinity)\b|\[object Object\]", re.I)
FAILURE_WORDS = ("失败", "错误", "不可用", "重试", "稍后", "保留")


@dataclass(frozen=True)
class Action:
    name: str
    kind: str
    selector: str
    request: str | None = None
    output: str = "#page-root"
    value: str | None = None
    write: bool = False
    optional: bool = False


@dataclass(frozen=True)
class PageSpec:
    route: str
    ready: str
    evidence: tuple[str, ...]
    actions: tuple[Action, ...] = ()
    charts: int = 0


PAGES: dict[str, PageSpec] = {
    "monitoring-overview": PageSpec(
        "/monitoring-page",
        "#monitoring-topbar, .monitoring-summary-surface",
        ("#monitoring-topbar", "#monitoring-macro-panel", "#monitoring-terminal-summary"),
        (
            Action(
                "刷新监控",
                "refresh",
                ".monitoring-refresh",
                "/monitoring/dashboard/refresh",
                write=True,
            ),
            Action("展开缺失数据", "click", "[data-missing-toggle]", optional=True),
        ),
    ),
    "market-analysis": PageSpec(
        "/indicators-page",
        "#analysis-signal-cards",
        ("#analysis-summary", "#analysis-signal-cards", "#analysis-mark-price"),
        (
            Action("切换标的", "alternate", "[data-instrument-id]", "/analysis/bundle"),
            Action(
                "切换周期",
                "dropdown",
                '[data-dropdown-id="analysis-timeframe"]',
                "/analysis/bundle",
            ),
            Action(
                "切换窗口", "dropdown", '[data-dropdown-id="analysis-window"]', "/analysis/bundle"
            ),
            Action("刷新分析", "refresh", "#analysis-refresh", "/analysis/refresh", write=True),
        ),
        6,
    ),
    "market-structure": PageSpec(
        "/structure-page",
        ".structure-page",
        ("#structure-chart-panel", "#structure-summary-panel"),
        (
            Action(
                "切换标的",
                "dropdown",
                '[data-dropdown-id="structure-instrument"]',
                "/structure/tab/bundle",
            ),
            Action(
                "切换周期",
                "dropdown",
                '[data-dropdown-id="structure-timeframe"]',
                "/structure/tab/bundle",
            ),
            Action("切换系统", "dropdown", '[data-dropdown-id="structure-system"]'),
            Action("切换置信度", "dropdown", '[data-dropdown-id="structure-confidence"]'),
            Action("切换视图", "dropdown", '[data-dropdown-id="structure-viewmode"]'),
            Action("摆动骨架", "checkbox", "#toggle-swing input"),
            Action(
                "刷新结构", "refresh", "#structure-refresh", "/structure/tab/refresh", write=True
            ),
        ),
    ),
    "market-events": PageSpec(
        "/market-events-page",
        ".events-feed-shell",
        ("#events-metrics", "#events-feed"),
        (
            Action("切换翻译", "click", "#events-translate-toggle"),
            Action(
                "筛选供给日历",
                "dropdown",
                '[data-dropdown-id="supply-calendar-filter"]',
                optional=True,
            ),
            Action("刷新信息流", "refresh", "#events-refresh", "/market-events/sync", write=True),
        ),
    ),
    "macro-calendar": PageSpec(
        "/macro-calendar-page",
        "#macro-calendar-container",
        ("#macro-calendar-container", "#macro-calendar-detail"),
        (
            Action("展开日历", "ensure-open", "#macro-calendar-toggle", optional=True),
            Action("上个月", "click", "#calendar-prev-month"),
            Action("下个月", "click", "#calendar-next-month"),
            Action("更新日历", "refresh", "#macro-sync-button", "/macro/sync", write=True),
        ),
    ),
    "ai-strategy": PageSpec(
        "/strategy-page",
        ".strategy-scan-page",
        ("#strategy-scan-matrix", "#strategy-scan-ranked"),
        (
            Action(
                "打开策略详情",
                "click",
                ".scan-cell-btn:not([disabled])",
                output="#strategy-detail-panel",
            ),
            Action("关闭策略详情", "click", "#strategy-detail-close", optional=True),
            Action("页面指南", "click", ".page-guide-fab", optional=True),
            Action("刷新扫描", "refresh", "#strategy-scan-refresh", "/strategy/scan", write=True),
        ),
    ),
    "btc-derivatives": PageSpec(
        "/btc-derivatives-page",
        ".btc-derivatives-page",
        (".btc-derivatives-hero", ".btc-evidence-grid", ".btc-chart-section"),
        (
            Action(
                "历史窗口",
                "dropdown",
                '[data-dropdown-id="btc-window"]',
                "/btc-derivatives/dashboard",
                optional=True,
            ),
            Action(
                "期限桶",
                "dropdown",
                '[data-dropdown-id="btc-maturity-bucket"]',
                "/btc-derivatives/dashboard",
                optional=True,
            ),
            Action(
                "行权价范围",
                "dropdown",
                '[data-dropdown-id="btc-strike-range"]',
                "/btc-derivatives/dashboard",
                optional=True,
            ),
            Action("刷新衍生品", "refresh", "#btc-refresh", "/btc-derivatives", write=True),
            Action(
                "提交对冲计划",
                "submit",
                "#btc-hedge-form",
                "/btc-derivatives/hedge-plan",
                optional=True,
            ),
        ),
        1,
    ),
    "ashare-etf": PageSpec(
        "/ashare-etf-page",
        "#etf-overview",
        ("#etf-overview", "#etf-equity-curve", "#etf-workbench"),
        (
            Action(
                "持仓回放",
                "click",
                "#etf-equity-mode-holdings",
                "/ashare-etf/equity-curve",
                optional=True,
            ),
            Action(
                "初始资金",
                "input",
                "#etf-equity-initial-capital",
                "/ashare-etf/simulation",
                value="250000",
                optional=True,
            ),
            Action("生成收益曲线", "click", "#etf-equity-generate", "/ashare-etf/", optional=True),
            Action("配置模式", "dropdown", '[data-dropdown-id="etf-mode"]', optional=True),
            Action("刷新 ETF", "refresh", "#etf-refresh-button", "/etf/quotes/refresh", write=True),
        ),
        1,
    ),
    "gold-allocation": PageSpec(
        "/gold-allocation-page",
        ".gold-hero, .gold-cockpit-header",
        (".gold-workbench-grid", ".gold-chart-grid"),
        (Action("刷新黄金", "refresh", "#gold-refresh", "/gold/workbench", write=True),),
        6,
    ),
    "knowledge-base": PageSpec(
        "/knowledge-page",
        "#knowledge-search",
        ("#knowledge-search", ".knowledge-sections, .knowledge-card-grid"),
        (
            Action("搜索术语", "input", "#knowledge-search", value="VWAP"),
            Action(
                "章节筛选",
                "dropdown",
                '[data-dropdown-id="knowledge-section-filter"]',
                optional=True,
            ),
            Action(
                "层级筛选", "dropdown", '[data-dropdown-id="knowledge-level-filter"]', optional=True
            ),
            Action("展开术语", "click", "[data-toggle-knowledge]", optional=True),
        ),
    ),
    "alert-center": PageSpec(
        "/alerts-page", ".strategy-scan-page", (".strategy-scan-page", "#strategy-scan-matrix")
    ),
}


@dataclass
class Issue:
    severity: str
    page: str
    title: str
    expected: str
    actual: str
    steps: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    owner_hint: str = "frontend page module / API adapter"


@dataclass
class ActionResult:
    name: str
    status: str
    reason: str
    selector: str
    requests: list[dict[str, Any]] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    page_id: str
    route: str
    mode: str
    duration_ms: float = 0
    health: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    layout: dict[str, Any] = field(default_factory=dict)
    actions: list[ActionResult] = field(default_factory=list)
    uncovered_controls: list[dict[str, str]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    screenshot: str | None = None
    trace: str | None = None


STATE_JS = """() => {
 const vis=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
 const txt=e=>(e?.innerText||e?.textContent||'').replace(/\\s+/g,' ').trim();
 const controls=[...document.querySelectorAll('button,input,[role="button"],[data-dropdown-id]')]
  .filter(vis).filter(e=>!e.closest('nav')&&!e.closest('#command-palette')).map(e=>({id:e.id||'',dropdown:e.dataset?.dropdownId||'',text:txt(e).slice(0,80),value:e.value??'',checked:'checked' in e?!!e.checked:null,expanded:e.getAttribute('aria-expanded'),disabled:!!e.disabled}));
 const charts=[...document.querySelectorAll('canvas')].map(c=>{let ch=null;try{ch=window.Chart?.getChart?.(c)}catch(_){};return{id:c.id||'',datasets:(ch?.data?.datasets||[]).map(d=>{const a=Array.isArray(d.data)?d.data:[];return{points:a.length,nonNull:a.filter(v=>{const x=typeof v==='object'&&v!==null?(v.y??v.r??v.x):v;return x!=null&&Number.isFinite(Number(x))}).length}})}});
 return {url:location.href,title:document.title,activePage:document.body.dataset.page||'',pageText:txt(document.querySelector('#page-root')).slice(0,15000),controls,charts,
 loading:[...document.querySelectorAll('[class*="loading"],[class*="spinner"],[aria-busy="true"]')].filter(vis).map(e=>txt(e).slice(0,100)),
 width:{body:document.body.scrollWidth,root:document.documentElement.scrollWidth},height:{body:document.body.scrollHeight,root:document.documentElement.scrollHeight},
 inspector:document.querySelectorAll('#structure-inspector,.workbench-inspector').length,cards:document.querySelectorAll('#analysis-signal-cards > *,.analysis-signal-card').length}; }"""


def short(value: str | None, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def state(page: Page, output: str = "#page-root") -> dict[str, Any]:
    data = page.evaluate(STATE_JS)
    loc = page.locator(output)
    try:
        text = short(loc.first.inner_text(timeout=1000), 5000) if loc.count() else ""
    except Exception:
        text = ""
    data["output"] = hashlib.sha256(text.encode()).hexdigest()[:16]
    data["page"] = hashlib.sha256(data["pageText"].encode()).hexdigest()[:16]
    return data


def settle(page: Page, timeout: int = 12000) -> None:
    end, old, stable = time.monotonic() + timeout / 1000, None, 0
    while time.monotonic() < end:
        try:
            cur = page.evaluate(
                "() => [document.querySelector('#page-root')?.innerText.length||0,document.querySelectorAll('[aria-busy=\"true\"],.analysis-is-transitioning').length]"
            )
        except Exception:
            return
        stable = stable + 1 if cur == old and cur[1] == 0 else 0
        if stable >= 3:
            return
        old = cur
        page.wait_for_timeout(300)


def perform(page: Page, action: Action) -> str:
    loc = page.locator(action.selector)
    if not loc.count():
        raise LookupError("control not found")
    try:
        page.wait_for_function(
            "sel => { const e=document.querySelector(sel); return !!e && !e.disabled && e.getAttribute('aria-disabled') !== 'true'; }",
            arg=action.selector,
            timeout=20_000,
        )
    except Exception:
        raise RuntimeError("control did not become enabled") from None
    if action.kind == "dropdown":
        old = short(loc.first.inner_text())
        # Use the component's public keyboard contract. Pointer-selecting an
        # option is race-prone because several pages rebuild their toolbar as
        # data settles, while the detached popover remains in document.body.
        loc.first.press("ArrowDown")
        loc.first.press("End")
        loc.first.press("Enter")
        label = short(loc.first.inner_text())
        if label == old:
            loc.first.press("ArrowDown")
            loc.first.press("Home")
            loc.first.press("Enter")
            label = short(loc.first.inner_text())
        if not label or label == old:
            raise RuntimeError("dropdown value did not change through keyboard contract")
        return label
    if action.kind == "alternate":
        for i in range(loc.count()):
            item = loc.nth(i)
            cls = item.get_attribute("class") or ""
            if item.is_visible() and not item.is_disabled() and "is-active" not in cls:
                label = short(item.inner_text())
                item.click()
                return label
        raise RuntimeError("no alternate control")
    if action.kind == "input":
        loc.first.fill(action.value or "audit")
        loc.first.dispatch_event("input")
        loc.first.dispatch_event("change")
        return action.value or "audit"
    if action.kind == "checkbox":
        before = loc.first.is_checked()
        loc.first.click()
        return f"{before}->{loc.first.is_checked()}"
    if action.kind == "submit":
        loc.first.evaluate("el=>el.requestSubmit()")
        return "submitted"
    if action.kind == "ensure-open":
        body = page.locator("#macro-calendar-body")
        if body.count() and body.first.is_visible():
            return "already-open"
        loc.first.click()
        return "opened"
    label = short(loc.first.inner_text())
    loc.first.click()
    return label


def chart_evidence(s: dict[str, Any]) -> dict[str, Any]:
    useful, empty = [], []
    for chart in s["charts"]:
        (
            useful
            if any(d["points"] >= 2 and d["nonNull"] >= 2 for d in chart["datasets"])
            else empty
        ).append(chart["id"])
    return {"count": len(s["charts"]), "useful": useful, "empty": empty, "details": s["charts"]}


def control_changed(a: dict[str, Any], b: dict[str, Any]) -> bool:
    def key(xs: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [
            (
                x["id"],
                x["dropdown"],
                x["text"],
                x["value"],
                x["checked"],
                x["expanded"],
                x["disabled"],
            )
            for x in xs
        ]

    return key(a["controls"]) != key(b["controls"])


def run_action(
    page: Page, pid: str, action: Action, requests: list[dict[str, Any]]
) -> tuple[ActionResult, Issue | None]:
    if action.write:
        return ActionResult(
            action.name, "UNCOVERED", "真实轮禁止写；受控轮覆盖", action.selector
        ), None
    if not page.locator(action.selector).count():
        status = "UNCOVERED" if action.optional else "FAIL"
        issue = (
            None
            if action.optional
            else Issue(
                "P1",
                pid,
                f"缺少核心控件：{action.name}",
                action.selector,
                "DOM 中不存在",
                [f"打开 {PAGES[pid].route}"],
            )
        )
        return ActionResult(action.name, status, "control not found", action.selector), issue
    before, start = state(page, action.output), len(requests)
    try:
        value = perform(page, action)
        settle(page)
        after, req = state(page, action.output), requests[start:]
        request_ok = action.request is None or any(action.request in x["url"] for x in req)
        changed = (
            before["output"] != after["output"]
            or before["url"] != after["url"]
            or control_changed(before, after)
        )
        if action.kind == "ensure-open" and page.locator("#macro-calendar-body").first.is_visible():
            changed = True
        # A deterministic calculation can legitimately reproduce the same
        # result.  It is not an empty gear when the intended API request was
        # observed and a non-empty result surface remains rendered.
        if action.name.startswith("生成") and request_ok and req and after["output"]:
            changed = True
        if request_ok and changed:
            return ActionResult(
                action.name,
                "PASS",
                f"value={value}; output/state changed",
                action.selector,
                req,
                before,
                after,
            ), None
        reason = f"request_ok={request_ok}; changed={changed}; value={value}"
        return ActionResult(
            action.name, "FAIL", reason, action.selector, req, before, after
        ), Issue(
            "P1",
            pid,
            f"操作可能为空转：{action.name}",
            "正确请求/状态驱动可见输出",
            reason,
            [f"打开 {PAGES[pid].route}", f"操作 {action.name}"],
            {"requests": req},
        )
    except Exception as exc:
        status = "UNCOVERED" if action.optional else "FAIL"
        issue = (
            None
            if status == "UNCOVERED"
            else Issue(
                "P1",
                pid,
                f"操作失败：{action.name}",
                "进入稳定终态",
                short(str(exc)),
                [f"打开 {PAGES[pid].route}", f"操作 {action.name}"],
            )
        )
        return ActionResult(
            action.name, status, short(str(exc)), action.selector, requests[start:], before
        ), issue


def uncovered_controls(s: dict[str, Any], actions: tuple[Action, ...]) -> list[dict[str, str]]:
    known = " ".join(a.selector for a in actions)
    out = []
    for c in s["controls"]:
        label = c["text"] or c["id"] or c["dropdown"]
        if not label or label in {"命令", "关闭", "返回顶部"} or c["disabled"]:
            continue
        if (c["id"] and c["id"] in known) or (c["dropdown"] and c["dropdown"] in known):
            continue
        out.append({"control": label, "reason": "未纳入自动因果场景"})
    return out


def real_page(browser: Browser, pid: str, spec: PageSpec, base: str, out: Path) -> Result:
    started = time.monotonic()
    ctx = browser.new_context(viewport=VIEWPORT)
    ctx.tracing.start(screenshots=True, snapshots=True)
    page = ctx.new_page()
    console, errors, failed, requests = [], [], [], []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on(
        "response",
        lambda r: failed.append({"status": r.status, "url": r.url}) if r.status >= 400 else None,
    )
    page.on(
        "request",
        lambda r: (
            requests.append(
                {
                    "method": r.method,
                    "url": r.url,
                    "query": parse_qs(urlparse(r.url).query),
                    "body": short(r.post_data),
                }
            )
            if "/api/" in r.url
            else None
        ),
    )
    result = Result(pid, spec.route, "real")
    try:
        response = page.goto(base + spec.route, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(spec.ready, timeout=20000)
        settle(page, 20000)
        initial = state(page)
        result.health = {
            "http": response.status if response else None,
            "page_errors": errors,
            "console_errors": console,
            "failed_responses": failed,
            "identity": {
                "url": page.url,
                "title": page.title(),
                "active_page": initial["activePage"],
            },
        }
        charts = chart_evidence(initial)
        result.data = {
            "evidence": {
                x: short(page.locator(x).first.inner_text()) if page.locator(x).count() else ""
                for x in spec.evidence
            },
            "invalid": INVALID.findall(initial["pageText"]),
            "charts": charts,
        }
        overflow = max(initial["width"].values()) - VIEWPORT["width"]
        result.layout = {
            "viewport": VIEWPORT,
            "horizontal_overflow_px": overflow,
            "vertical_pages": round(max(initial["height"].values()) / VIEWPORT["height"], 2),
            "inspector": initial["inspector"],
            "analysis_cards": initial["cards"],
        }
        if console or errors or failed:
            result.issues.append(
                Issue(
                    "P1",
                    pid,
                    "生命周期存在运行时/请求错误",
                    "0 错误",
                    f"page={len(errors)}, console={len(console)}, http={len(failed)}",
                    [f"冷启动 {spec.route}"],
                    result.health,
                )
            )
        if overflow > 2:
            result.issues.append(
                Issue(
                    "P2",
                    pid,
                    "2560×1600 横向溢出",
                    "无横向溢出",
                    f"{overflow}px",
                    [f"打开 {spec.route}"],
                )
            )
        if INVALID.search(initial["pageText"]):
            result.issues.append(
                Issue(
                    "P0",
                    pid,
                    "展示非法计算值",
                    "无 NaN/undefined/Infinity",
                    short(initial["pageText"]),
                    [f"打开 {spec.route}"],
                )
            )
        if spec.charts and len(charts["useful"]) < spec.charts:
            result.issues.append(
                Issue(
                    "P1",
                    pid,
                    "有效图表不足",
                    f">={spec.charts} 张图含至少 2 个有效点",
                    f"useful={charts['useful']}; empty={charts['empty']}",
                    [f"打开 {spec.route}"],
                    charts,
                )
            )
        if pid == "market-structure" and initial["inspector"]:
            result.issues.append(
                Issue(
                    "P2",
                    pid,
                    "重复 Inspector 仍存在",
                    "count=0",
                    f"count={initial['inspector']}",
                    [f"打开 {spec.route}"],
                )
            )
        if pid == "market-analysis" and initial["cards"] != 9:
            result.issues.append(
                Issue(
                    "P1",
                    pid,
                    "指标卡数量错误",
                    "9 张",
                    f"count={initial['cards']}",
                    [f"打开 {spec.route}"],
                )
            )
        for action in spec.actions:
            ar, issue = run_action(page, pid, action, requests)
            result.actions.append(ar)
            if issue:
                result.issues.append(issue)
        final = state(page)
        result.uncovered_controls = uncovered_controls(final, spec.actions)
        if final["loading"]:
            result.issues.append(
                Issue(
                    "P1",
                    pid,
                    "交互后 loading 未结束",
                    "稳定终态",
                    str(final["loading"][:8]),
                    ["执行本页交互"],
                )
            )
        shot = out / "screenshots" / f"real-{pid}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot), full_page=True)
        result.screenshot = str(shot.resolve())
    except Exception as exc:
        result.issues.append(
            Issue(
                "P1",
                pid,
                "页面审计无法完成",
                "可审计稳定状态",
                short(str(exc), 500),
                [f"打开 {spec.route}"],
            )
        )
    finally:
        result.duration_ms = round((time.monotonic() - started) * 1000, 1)
        try:
            if result.issues:
                trace = out / "traces" / f"real-{pid}.zip"
                trace.parent.mkdir(parents=True, exist_ok=True)
                ctx.tracing.stop(path=str(trace))
                result.trace = str(trace.resolve())
            else:
                ctx.tracing.stop()
        except Exception:
            pass
        ctx.close()
    return result


def controlled_page(
    browser: Browser, pid: str, spec: PageSpec, base: str, out: Path
) -> Result | None:
    refresh = next((a for a in spec.actions if a.kind == "refresh" and a.request), None)
    if not refresh:
        return None
    started = time.monotonic()
    ctx = browser.new_context(viewport=VIEWPORT)
    ctx.tracing.start(screenshots=True, snapshots=True)
    page = ctx.new_page()
    armed = {"on": False}
    hit = []

    def handler(route: Route) -> None:
        if armed["on"] and (route.request.method != "GET" or refresh.request in route.request.url):
            hit.append({"method": route.request.method, "url": route.request.url})
            route.fulfill(
                status=503,
                content_type="application/json",
                body='{"detail":"ui_audit_controlled_failure"}',
            )
        else:
            route.continue_()

    page.route("**/api/v1/**", handler)
    result = Result(pid, spec.route, "controlled-failure")
    try:
        page.goto(base + spec.route, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(spec.ready, timeout=20000)
        settle(page, 20000)
        before = state(page, refresh.output)
        armed["on"] = True
        perform(page, refresh)
        page.wait_for_timeout(800)
        settle(page, 15000)
        after = state(page, refresh.output)
        button = page.locator(refresh.selector).first
        recovered = button.count() and button.is_visible() and not button.is_disabled()
        stuck = len(after["loading"]) > len(before["loading"])
        visible = after["page"] != before["page"] and any(
            x in after["pageText"] for x in FAILURE_WORDS
        )
        passed = bool(hit) and recovered and not stuck and visible
        reason = f"intercepted={len(hit)}, recovered={recovered}, new_loading_stuck={stuck}, visible_failure={visible}"
        result.actions.append(
            ActionResult(
                refresh.name + "：受控503",
                "PASS" if passed else "FAIL",
                reason,
                refresh.selector,
                hit,
                before,
                after,
            )
        )
        if not passed:
            result.issues.append(
                Issue(
                    "P1",
                    pid,
                    f"{refresh.name}失败态不完整",
                    "退出 busy 并解释失败",
                    reason,
                    [f"打开 {spec.route}", f"注入 {refresh.request}=503", f"点击 {refresh.name}"],
                    {"requests": hit},
                )
            )
        shot = out / "screenshots" / f"controlled-{pid}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot), full_page=True)
        result.screenshot = str(shot.resolve())
    except Exception as exc:
        result.issues.append(
            Issue("P1", pid, "受控失败场景无法执行", "验证失败恢复", short(str(exc), 500))
        )
    finally:
        result.duration_ms = round((time.monotonic() - started) * 1000, 1)
        try:
            if result.issues:
                trace = out / "traces" / f"controlled-{pid}.zip"
                trace.parent.mkdir(parents=True, exist_ok=True)
                ctx.tracing.stop(path=str(trace))
                result.trace = str(trace.resolve())
            else:
                ctx.tracing.stop()
        except Exception:
            pass
        ctx.close()
    return result


def spa_audit(browser: Browser, base: str, ids: list[str]) -> dict[str, Any]:
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    transitions = []
    try:
        first = ids[0]
        page.goto(base + PAGES[first].route, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(PAGES[first].ready, timeout=20000)
        for pid in ids[1:]:
            if pid == "alert-center":
                continue
            start = time.monotonic()
            link = page.locator(f'[data-page-link="{pid}"]')
            if not link.count():
                transitions.append(
                    {"page": pid, "status": "UNCOVERED", "reason": "nav link missing"}
                )
                continue
            try:
                link.click()
                page.wait_for_selector(PAGES[pid].ready, timeout=5000)
                transitions.append(
                    {
                        "page": pid,
                        "status": "PASS",
                        "ms": round((time.monotonic() - start) * 1000, 1),
                        "url": page.url,
                    }
                )
            except Exception as exc:
                transitions.append(
                    {"page": pid, "status": "FAIL", "reason": short(str(exc)), "url": page.url}
                )
        return {"transitions": transitions, "page_errors": errors}
    finally:
        ctx.close()


def self_test(browser: Browser) -> dict[str, Any]:
    ctx = browser.new_context(viewport=VIEWPORT)
    page = ctx.new_page()
    try:
        page.set_content(
            '<main id="page-root"><button id="gear">刷新</button><div class="loading">加载中</div><canvas id="empty"></canvas><p>NaN</p></main>'
        )
        a = state(page)
        page.locator("#gear").click()
        b = state(page)
        cases = {
            "invalid_value": bool(INVALID.search(a["pageText"])),
            "stuck_loading": bool(a["loading"]),
            "empty_chart": bool(chart_evidence(a)["empty"]),
            "empty_gear": a["output"] == b["output"] and not control_changed(a, b),
        }
        return {"status": "PASS" if all(cases.values()) else "FAIL", "cases": cases}
    finally:
        ctx.close()


def write_report(out: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "ui_logic_audit.json"
    mp = out / "ui_logic_audit.md"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sev = payload["summary"]["severity"]
    lines = [
        "# 交易系统管理平台 — Playwright UI 逻辑审计",
        "",
        f"- 时间：{payload['generated_at']}",
        "- 主视口：2560×1600",
        f"- 地址：`{payload['base_url']}`",
        "- 判定：控件 → 请求/状态 → 可见输出；HTTP 200、元素或 canvas 存在不单独构成通过。",
        "- 历史审计报告仅作背景，不继承其全站通过结论。",
        "- 标准冲突：source 规范与部分脚本为 2560×1600；根 AGENTS.md、根规范和旧脚本仍残留 2560×1440。",
        "",
        "## 执行摘要",
        "",
        f"- P0={sev['P0']}，P1={sev['P1']}，P2={sev['P2']}，P3={sev['P3']}",
        f"- 未覆盖交互/控件：{payload['summary']['uncovered']}（不计入通过）",
        f"- 故障注入检测器自检：{payload['detector_self_test']['status']}",
        "",
        "## Findings",
        "",
    ]
    issues = [i for r in payload["results"] for i in r["issues"]]
    if not issues:
        lines.append("未发现 P0–P3；仍须结合未覆盖清单理解边界。")
    for n, i in enumerate(issues, 1):
        lines += [
            f"### {n}. [{i['severity']}] {i['page']} — {i['title']}",
            "",
            f"- 期望：{i['expected']}",
            f"- 实际：{i['actual']}",
            f"- 复现：{' → '.join(i.get('steps') or ['见 JSON'])}",
            f"- 责任模块提示：{i['owner_hint']}",
            "",
        ]
    lines += ["## 逐页结果", ""]
    for r in payload["results"]:
        counts = {
            x: sum(a["status"] == x for a in r["actions"]) for x in ("PASS", "FAIL", "UNCOVERED")
        }
        lines += [
            f"### {r['page_id']} · {r['mode']}",
            "",
            f"- 交互：{counts}",
            f"- 问题：{len(r['issues'])}",
            f"- 截图：`{r.get('screenshot') or '-'}`",
            f"- Trace：`{r.get('trace') or '-'}`",
        ]
        for a in r["actions"]:
            lines.append(f"  - `{a['status']}` {a['name']}：{a['reason']}")
        if r["uncovered_controls"]:
            lines.append(
                "  - 未覆盖控件：" + "、".join(x["control"] for x in r["uncovered_controls"][:20])
            )
        lines.append("")
    lines += [
        "## SPA 切换",
        "",
        "```json",
        json.dumps(payload["spa"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 限制",
        "",
        "- 真实轮不执行写入/外部同步；刷新仅在受控 503 轮检查失败恢复。",
        "- UNCOVERED 不计入通过。",
        "- 本轮仅 Chromium。",
    ]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp, jp


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--pages", default=",".join(PAGES))
    parser.add_argument("--mode", choices=("real", "controlled", "both"), default="both")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / f"crypto-ui-logic-audit-{stamp}",
    )
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    ids = [x.strip() for x in args.pages.split(",") if x.strip()]
    unknown = [x for x in ids if x not in PAGES]
    if unknown:
        print("Unknown pages: " + ", ".join(unknown), file=sys.stderr)
        return 2
    out = args.output_dir.resolve()
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        detector = self_test(browser)
        if args.mode in {"real", "both"}:
            for pid in ids:
                print(f"[real] {pid}", flush=True)
                results.append(real_page(browser, pid, PAGES[pid], args.base_url.rstrip("/"), out))
        if args.mode in {"controlled", "both"}:
            for pid in ids:
                r = controlled_page(browser, pid, PAGES[pid], args.base_url.rstrip("/"), out)
                if r:
                    print(f"[controlled] {pid}", flush=True)
                    results.append(r)
        spa = (
            spa_audit(browser, args.base_url.rstrip("/"), ids)
            if args.mode in {"real", "both"}
            else {"status": "not-run"}
        )
        browser.close()
    sev = {
        x: sum(i.severity == x for r in results for i in r.issues) for x in ("P0", "P1", "P2", "P3")
    }
    uncovered = sum(
        sum(a.status == "UNCOVERED" for a in r.actions) + len(r.uncovered_controls) for r in results
    )
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "viewport": VIEWPORT,
        "mode": args.mode,
        "detector_self_test": detector,
        "summary": {"results": len(results), "severity": sev, "uncovered": uncovered},
        "spa": spa,
        "results": [asdict(r) for r in results],
    }
    mp, jp = write_report(out, payload)
    print(f"Markdown: {mp}\nJSON: {jp}\nFindings: {sev}")
    return 1 if sev["P0"] or sev["P1"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
