# Gold Allocation Page V5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redraw the gold-allocation frontend (`/gold-allocation-page`) to visually match the analysis page (`/indicators-page`) glass + eyebrow + chip language, with structural cleanups (5-chart equal-height grid, top-down refactor of Spot-DCA & Contract-Ref, governance as 4-column mini-card grid, removal of Jinja initial-shell). No backend schema, endpoint, or service changes.

**Architecture:** Build `gold_v5.js` alongside the existing `gold_v4.js`, route `main.js` to v5, add a single CSS block (≈130 lines) at end of `styles.css`. Use the `impactChip()` helper that is already exported from `core/dom.js:306`; copy the small `signalTone()`/`signalLabel()` text-classification logic locally (it's not exported, and per the spec we should not modify analysis.js / shared core to avoid regression risk). All visual rendering happens client-side; backend payload shape stays untouched (`/api/v1/gold/workbench` returning `GoldWorkbenchRead`).

**Tech Stack:** Vanilla ES modules + `Chart.js` (already loaded by `main.js:128-130` for `gold-allocation`); pydantic schemas unchanged; Python 3.11 / FastAPI unchanged.

**References:**
- Spec: `docs/superpowers/specs/2026-07-31-gold-allocation-page-v5-redesign.md` (commit `196542f`)
- Reference page: `app/static/pages/analysis.js`, glass tokens at `app/static/styles.css:4240-4388`
- Existing module to supersede: `app/static/pages/gold_v4.js`
- Jinja hero to remove: `app/templates/page.html:44-52`
- Router: `app/static/main.js:21` (loadPageModule map), `:182` (dispatcher), `:13` (page-id map)

---

## File Structure

| Path | Op | Responsibility |
|---|---|---|
| `app/static/pages/gold_v5.js` | new | Replacement frontend module; exports `{ renderGoldV5, unmount, ready }` |
| `app/static/main.js` | edit | Route `gold-allocation` → `gold_v5.js`, dispatcher `renderGoldV5` |
| `app/static/styles.css` | edit | Append `/* === gold-allocation v5 === */` block (~130 lines) |
| `app/templates/page.html` | edit | Delete `gold-initial-shell` block (lines 44-52) |
| `tests/test_gold_v5_frontend_static.py` | new | Static guards (no emoji / no inline style / no `<select` / 5 chart IDs / 4 gov cards / no v4 fallback) |
| `app/static/pages/gold_v4.js` | del (Task 7) | After v5 verified |

**Out of scope (do not touch):**
- `app/schemas/gold_*.py`, `app/services/gold_*.py`, `app/api/v1/endpoints/gold.py`
- `app/static/core/*.js` (no changes to shared core)
- `app/static/pages/analysis.js` (do not modify reference page)
- Any other SPA page

---

## Task 1: Write static guards (write tests first)

**Files:**
- Test: `tests/test_gold_v5_frontend_static.py`

The whole point of guards first is so that when we make mistakes during implementation, the test fails immediately and tells us *which* rule we broke.

### Step 1: Write the failing test file

Create `tests/test_gold_v5_frontend_static.py` with the content below.

```python
"""Static assertions for gold V5 frontend module — analysis-page visual alignment."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "app" / "static" / "pages" / "gold_v5.js"
TEMPLATE_PATH = REPO_ROOT / "app" / "templates" / "page.html"
CSS_PATH = REPO_ROOT / "app" / "static" / "styles.css"
MAIN_PATH = REPO_ROOT / "app" / "static" / "main.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestGoldV5Exports:
    def test_module_exists(self):
        assert JS_PATH.exists(), f"missing {JS_PATH}"

    def test_exports_renderGoldV5(self):
        assert "export async function renderGoldV5" in _read(JS_PATH)

    def test_includes_unmount(self):
        assert "unmount" in _read(JS_PATH)

    def test_includes_ready(self):
        assert "ready" in _read(JS_PATH)


class TestGoldV5ChartIds:
    """The 5 chart cards must keep stable IDs for Chart.js subscription."""
    def test_price_id(self):
        assert "gold-chart-price" in _read(JS_PATH)
    def test_rsi_id(self):
        assert "gold-chart-rsi" in _read(JS_PATH)
    def test_bollinger_id(self):
        assert "gold-chart-bollinger" in _read(JS_PATH)
    def test_volume_id(self):
        assert "gold-chart-volume" in _read(JS_PATH)
    def test_drawdown_id(self):
        assert "gold-chart-drawdown" in _read(JS_PATH)


class TestGoldV5Governance:
    def test_governance_grid_class(self):
        assert "gold-governance-grid" in _read(JS_PATH)

    def test_mini_card_class(self):
        assert "gold-mini-card" in _read(JS_PATH)

    def test_governance_uses_source_manifest(self):
        """V4 hallucinated payload.macro_bias / payload.sources[]; V5 must read
        the real schema field `source_manifest[]`."""
        src = _read(JS_PATH)
        assert "source_manifest" in src, (
            "V5 must read payload.source_manifest[] for governance "
            "(see spec §4.1 and gold.py:403-460)"
        )

    def test_no_v4_chip_warning_fallback(self):
        """V4 default was 'chip-warning' for any non-fresh governance row;
        V5 routes tone through statusTone() map."""
        src = _read(JS_PATH)
        assert 'class="status-chip ${healthy ? "chip-bullish-soft" : "chip-warning"}' not in src


class TestGoldV5VisualLanguage:
    def test_no_emoji(self):
        """V4 had zero emoji by user instruction; V5 keeps that guard."""
        src = _read(JS_PATH)
        # Forbid every common emoji codepoint range
        for ch in src:
            cp = ord(ch)
            assert not (0x2700 <= cp <= 0x27BF), f"emoji at codepoint U+{cp:04X}"
            assert not (0x1F300 <= cp <= 0x1FAFF), f"emoji at codepoint U+{cp:04X}"

    def test_no_inline_style_attribute(self):
        """V4 had 11 `style=\"...\"` literals; V5 uses class-based styling only."""
        assert 'style="' not in _read(JS_PATH)

    def test_no_select_literal(self):
        """V4 already complied; keep guard against regression."""
        assert "<select" not in _read(JS_PATH)

    def test_uses_analysis_hero_card_class(self):
        """Hero must reuse analysis-page .analysis-hero-card class."""
        assert "analysis-hero-card" in _read(JS_PATH)

    def test_uses_chart_wrap_class(self):
        """Each chart card must wrap canvas in .chart-wrap (matches analysis)."""
        assert "chart-wrap" in _read(JS_PATH)

    def test_uses_mini_card_class(self):
        """Contract-ref 2x2 tiles must use .mini-card directly."""
        assert "mini-card" in _read(JS_PATH)

    def test_uses_impact_chip_helper(self):
        """V5 must route chip tone through core/dom.js impactChip()."""
        src = _read(JS_PATH)
        assert "impactChip" in src


class TestGoldV5Template:
    def test_jinja_initial_shell_removed(self):
        """V5 deletes the duplicate Jinja hero so first paint is single hero."""
        template = _read(TEMPLATE_PATH)
        assert 'class="hero-card gold-initial-shell"' not in template, (
            "page.html:44-52 gold-initial-shell must be deleted in V5"
        )


class TestGoldV5Routing:
    def test_main_js_routes_to_v5(self):
        """main.js:21 maps gold-allocation → pages/gold_v5.js (not v4)."""
        src = _read(MAIN_PATH)
        assert '"gold-allocation": () => loadPageModule("./pages/gold_v5.js")' in src, (
            "main.js gold-allocation route must point to gold_v5.js"
        )

    def test_main_js_dispatcher_calls_renderGoldV5(self):
        src = _read(MAIN_PATH)
        assert "renderGoldV5" in src
        # Old v4 dispatcher reference must be removed
        assert "module.renderGoldV4 ||" not in src


class TestGoldV5Css:
    def test_css_block_appended(self):
        css = _read(CSS_PATH)
        assert "=== gold-allocation v5" in css, (
            "styles.css must contain a v5 design block as final section"
        )

    def test_css_uses_dash_repeat_pattern(self):
        """Spec §2.2 mandates grid-template-columns: repeat(2, ...)."""
        css = _read(CSS_PATH)
        # locate v5 block
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert "grid-template-columns: repeat(2," in block

    def test_css_has_is_wide_modifier(self):
        """Spec §2.2: price card uses .is-wide to span 2 columns."""
        css = _read(CSS_PATH)
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert ".gold-chart-card.is-wide" in block
        assert "grid-column: span 2" in block

    def test_css_has_governance_repeat_4(self):
        """Spec §2.5: governance grid is repeat(4, 1fr)."""
        css = _read(CSS_PATH)
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert "repeat(4, minmax(0, 1fr))" in block
```

### Step 2: Run the test to confirm it fails for the right reason

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
python -m pytest tests/test_gold_v5_frontend_static.py -q 2>&1 | tail -20
```

Expected: Many failures, all of the form `AssertionError: missing app\static\pages\gold_v5.js` and `AssertionError: 'gold-chart-price' not in ...`. The collector error confirming `JS_PATH.exists() == False` is acceptable. **If the test is missing entirely, you have a typo.** Any failure here is correct — the module does not exist yet.

### Step 3: Commit the failing tests

```bash
cd "E:/Personal/Research/Crypto Investing System"
git add tests/test_gold_v5_frontend_static.py
git commit -m "[test] gold-v5 frontend static guards (scaffold)"
```

---

## Task 2: Append the v5 design block to styles.css

**Files:**
- Modify: `app/static/styles.css` (append at end of file)

We land the CSS first so the JS author can wire markup against existing classes and see the styling take effect instantly.

### Step 1: Read the current end of styles.css

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
tail -n 5 app/static/styles.css
```

Expected: A closing CSS rule or the file's last selector. Note any trailing blank lines — the new block goes after them.

### Step 2: Append the v5 block at end of file

Append this exact block to `app/static/styles.css` (use Edit with the last existing line as `old_string` and append the new block; or Read whole file and Write back). The block must start with the marker comment `/* === gold-allocation v5 — visual alignment with analysis page === */` so the guard test in Task 1 can locate it:

```css

/* === gold-allocation v5 — visual alignment with analysis page === */
.gold-hero .card-head-inline {
  gap: 16px;
  align-items: flex-end;
}
.gold-page-h1 {
  font-size: 34px;
  font-weight: 600;
  letter-spacing: -0.04em;
  color: var(--ink, #1f1b16);
}
.gold-page-sub {
  font-size: 14px;
  color: var(--text-secondary, #6b6357);
  margin-top: 4px;
}

.gold-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 22px;
  margin-top: 22px;
}
.gold-chart-card { padding: 0; }
.gold-chart-card .card-head-inline {
  padding: 18px 18px 12px;
}
.gold-chart-card .chart-wrap {
  padding: 18px 18px 14px;
  border-top: 1px solid rgba(196, 188, 168, 0.32);
}
.gold-chart-card.is-wide {
  grid-column: span 2;
}

.gold-workbench-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  align-items: stretch;
  margin-top: 22px;
}
.gold-workbench-card {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.gold-weight-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.gold-weight-bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(91, 138, 131, 0.18);
  overflow: hidden;
}
.gold-weight-fill {
  height: 100%;
  background: var(--accent, #5b8a83);
  width: var(--gold-weight-pct, 0%);
  transition: width 0.3s ease;
}
.gold-formula-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 253, 249, 0.5);
  border: 1px solid rgba(196, 188, 168, 0.32);
}
.gold-formula-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary, #6b6357);
}
.gold-formula-item b {
  font-size: 18px;
  font-weight: 600;
  color: var(--ink, #1f1b16);
}
.gold-gate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-top: 1px solid rgba(196, 188, 168, 0.22);
}
.gold-gate-row .gold-gate-num {
  font-weight: 700;
  color: var(--accent, #5b8a83);
  margin-right: 10px;
}
.gold-recommend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid rgba(196, 188, 168, 0.22);
}
.gold-recommend-amount {
  font-size: 32px;
  font-weight: 700;
  color: var(--ink, #1f1b16);
}

.gold-price-banner {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 14px 18px;
  border-radius: 14px;
  background: rgba(91, 138, 131, 0.08);
  border: 1px solid rgba(91, 138, 131, 0.18);
}
.gold-price-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--ink, #1f1b16);
}
.gold-mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.gold-mini-card {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 253, 249, 0.6);
  border: 1px solid rgba(196, 188, 168, 0.32);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gold-mini-card.is-effective strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--ink, #1f1b16);
  border-top: 2px solid var(--accent, #5b8a83);
  padding-top: 4px;
}
.gold-mini-card.is-insufficient {
  opacity: 0.86;
  border-style: dashed;
}
.gold-mini-card.is-insufficient strong {
  font-size: 13px;
  color: var(--text-secondary, #6b6357);
  font-weight: 500;
}

.gold-governance {
  margin-top: 22px;
}
.gold-governance-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 12px;
}

.gold-chart-card.is-empty,
.gold-mini-card.is-empty,
.gold-workbench-card.is-empty {
  border-style: dashed;
  background: rgba(245, 240, 232, 0.45);
  color: var(--text-secondary, #6b6357);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}
```

### Step 3: Sanity-check the file parses

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
node -e "const fs=require('fs'); const css=fs.readFileSync('app/static/styles.css','utf8'); console.log('chars=',css.length,'v5-marker-present=',css.includes('=== gold-allocation v5'))"
```

Expected: prints `chars= <large> v5-marker-present= true`. If `v5-marker-present` is false, the append didn't take — re-check the Edit call.

### Step 4: Commit

```bash
cd "E:/Personal/Research/Crypto Investing System"
git add app/static/styles.css
git commit -m "[frontend] styles.css: append gold-allocation v5 design block (analysis-page alignment)"
```

---

## Task 3: Create `gold_v5.js` (the main implementation)

**Files:**
- Create: `app/static/pages/gold_v5.js`

This task lands the bulk of the work. Copy into `app/static/pages/gold_v5.js` exactly as written. Do not omit or paraphrase — the static guards expect specific tokens.

### Step 1: Write `app/static/pages/gold_v5.js`

```javascript
// gold-allocation v5 frontend module.
// Goal: visual alignment with the analysis page (market-analysis).
// Backend payload shape unchanged: /api/v1/gold/workbench returns GoldWorkbenchRead
// (see app/schemas/gold_workbench.py:53 and gold.py:300-502).
//
// This module never mutates state outside page-root, never emits inline style="",
// and never emits emoji codepoints (static test in tests/test_gold_v5_frontend_static.py).
//
// V5 status-mapping philosophy: status codes drive both chip tone and human label,
// mirroring analysis.js' signalTone/signalLabel without modifying the shared core
// (signalTone / signalLabel live inside analysis.js and are not exported).

import { api } from "../core/api.js";
import { escapeHtml, formatNumber, impactChip, setRoot } from "../core/dom.js";
import { barDataset, destroyChartsForPage, lineDataset, renderChart } from "../ui/charts.js";

const CHART_PREFIX = "gold-chart-";

let controller = null;
let latestData = null;

// ----- Status-code tone mapping (V5 replaces V4's hard-coded chip-neutral / chip-warning).
const STATUS_TONE_MAP = {
  EXECUTE: "bullish",
  READY_FIXED_ADD: "bullish",
  STRATEGIC_WITHIN_RANGE: "bullish-soft",
  STRATEGIC_UNDERWEIGHT: "neutral",
  STRATEGIC_OVERWEIGHT_NO_SELL: "neutral",
  WAIT_DRAWDOWN: "neutral",
  SETUP_FORMING: "neutral",
  COOLDOWN: "neutral",
  ALREADY_EXECUTED: "neutral",
  PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY: "warning",
  LIQUIDITY_SHOCK: "warning",
  BLOCKED_INVALID_AMOUNT: "bearish-soft",
  BLOCKED_INVALID_FIXED_AMOUNT: "bearish-soft",
  BLOCKED_STALE_QUOTE: "bearish-soft",
  BLOCKED_INSUFFICIENT_CASH: "bearish-soft",
  BLOCKED_OVERWEIGHT: "bearish-soft",
  BLOCKED_LIQUIDITY_SHOCK: "bearish",
  DATA_DEGRADED: "bearish",
  DEFAULT: "neutral",
};

function toneForStatus(code) {
  return STATUS_TONE_MAP[code] || STATUS_TONE_MAP.DEFAULT;
}

function labelForStatus(code) {
  const m = {
    EXECUTE: "建议执行",
    READY_FIXED_ADD: "建议加仓",
    STRATEGIC_WITHIN_RANGE: "区间内",
    STRATEGIC_UNDERWEIGHT: "低于目标",
    STRATEGIC_OVERWEIGHT_NO_SELL: "高于上限",
    WAIT_DRAWDOWN: "等待回撤",
    SETUP_FORMING: "确认中",
    COOLDOWN: "冷却中",
    ALREADY_EXECUTED: "今日已执行",
    PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY: "策略暂停",
    LIQUIDITY_SHOCK: "流动性冲击",
    BLOCKED_INVALID_AMOUNT: "配置无效",
    BLOCKED_INVALID_FIXED_AMOUNT: "配置无效",
    BLOCKED_STALE_QUOTE: "行情过期",
    BLOCKED_INSUFFICIENT_CASH: "现金不足",
    BLOCKED_OVERWEIGHT: "仓位已满",
    BLOCKED_LIQUIDITY_SHOCK: "流动冲击阻断",
    DATA_DEGRADED: "数据降级",
  };
  return m[code] || "—";
}

function chipForStatus(code, tooltip = "") {
  return impactChip(toneForStatus(code), tooltip, labelForStatus(code));
}

// ----- Governance tone mapping (source_manifest freshness_state → tone).
function toneForFreshness(state) {
  switch (state) {
    case "fresh":
      return "bullish-soft";
    case "stale":
      return "warning";
    case "degraded":
      return "warning";
    case "missing":
      return "bearish-soft";
    default:
      return "neutral";
  }
}

function labelForFreshness(state) {
  switch (state) {
    case "fresh":
      return "已就绪";
    case "stale":
      return "已过期";
    case "degraded":
      return "降级中";
    case "missing":
      return "数据缺失";
    default:
      return "未知";
  }
}

// ----- Numeric helpers (V4 had inline style arguments; V5 only outputs classes).
function money(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? `${formatNumber(n, d || 0)} 元` : "—";
}
function pct(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `${formatNumber(n * 100, 1)}%` : "—";
}

// ----- Subtitle / "macro scenario" Chinese label.
function scenarioLabel(active) {
  const m = {
    STRATEGIC_UNDERWEIGHT: "低于目标,触发基础定投",
    STRATEGIC_WITHIN_RANGE: "区间内,按策略执行",
    STRATEGIC_OVERWEIGHT_NO_SELL: "高于上限,默认不卖出",
    DATA_DEGRADED: "数据降级,等待回填",
    setup_required: "策略未配置",
  };
  return m[active] || "宏观待评估";
}

// ----- Render functions ----------------------------------------------------

function renderHero(data) {
  const active =
    data?.market_scenarios?.active_scenario ||
    (data?.refresh_state === "setup_required" ? "setup_required" : null);
  const setupRequired = data?.snapshot?.status === "setup_required";
  const subtitle = setupRequired
    ? "请先在策略页配置组合与执行纪律。"
    : `宏观判断: ${scenarioLabel(active || "DATA_DEGRADED")}`;
  const shock = data?.market_scenarios?.active_scenarios?.includes("LIQUIDITY_SHOCK");

  return `
    <section class="gold-hero">
      <article class="card analysis-hero-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">GOLD ALLOCATION</p>
            <h1 class="gold-page-h1">黄金配置 Workbench</h1>
            <p class="gold-page-sub">${escapeHtml(subtitle)}</p>
            ${
              shock
                ? '<p class="gold-page-sub">' +
                  impactChip("warning", "流动性冲击下固定加仓已阻断", "流动性冲击") +
                  "</p>"
                : ""
            }
          </div>
          <button class="mock-button" id="gold-refresh">刷新 XAUT</button>
        </div>
      </article>
    </section>
  `;
}

function renderChartCard(chartId, eyebrow, title, heightIsWide) {
  const wideClass = heightIsWide ? " is-wide" : "";
  return `
    <article class="card gold-chart-card${wideClass}" id="${chartId}">
      <div class="card-head-inline">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <p class="gold-card-title">${escapeHtml(title)}</p>
      </div>
      <div class="chart-wrap">
        <canvas id="gold-canvas-${chartId.replace(CHART_PREFIX, "")}"></canvas>
      </div>
    </article>
  `;
}

function renderChartGrid() {
  return `
    <section class="gold-chart-grid">
      ${renderChartCard("gold-chart-price", "PRICE & INDICATORS", "价格 · MA50 · SMA200 · EMA20", true)}
      ${renderChartCard("gold-chart-rsi", "MOMENTUM", "RSI(14)")}
      ${renderChartCard("gold-chart-bollinger", "VOLATILITY", "Bollinger %B · K(20,2)")}
      ${renderChartCard("gold-chart-volume", "VOLUME", "成交量")}
      ${renderChartCard("gold-chart-drawdown", "RISK", "60 日回撤")}
    </section>
  `;
}

// ----- Spot DCA — top-down refactor (4 stacked blocks per spec §2.3) -------

function renderWeightRow(strategic) {
  const state = strategic?.allocation_state || "DATA_DEGRADED";
  const cur = Number(strategic?.current_weight);
  const max = Number(strategic?.target_max);
  const fill = Number.isFinite(cur) && Number.isFinite(max) && max > 0 ? Math.min(100, (cur / max) * 100) : 0;
  // We cannot inject <script> via innerHTML — browsers won't execute it.
  // Encode the fill percentage into a data-fill attribute and let the
  // post-mount pass in renderGoldV5() apply it via CSS custom property.
  return `
    <div class="gold-weight-row">
      <div class="gold-card-title">当前 / 目标</div>
      <div class="gold-weight-bar"><div class="gold-weight-fill" data-fill="${fill.toFixed(1)}"></div></div>
      <span class="chip">${chipForStatus(state, "策略权重带:低于区间触发基础定投")}</span>
    </div>
  `;
}

function renderFormulaBox(base, dip) {
  // V4 had inline font-size:10px labels; V5 spec bumps to 13/18 (styles.css .gold-formula-item).
  const baseAmount = base?.amount;
  const dipAmount = dip?.amount;
  return `
    <div class="gold-formula-box">
      <div class="gold-formula-item"><span>BASR · 基础定投</span><b>${money(baseAmount)}</b></div>
      <div class="gold-formula-item"><span>FIXED · 黄金坑加仓</span><b>${money(dipAmount)}</b></div>
    </div>
  `;
}

function renderGateRow(num, label, chipCode, hint) {
  return `
    <div class="gold-gate-row">
      <div>
        <span class="gold-gate-num">${num}</span>
        <span class="gold-card-title">${escapeHtml(label)}</span>
      </div>
      <span class="chip">${chipForStatus(chipCode, hint)}</span>
    </div>
  `;
}

function renderRecommendRow(base, dip) {
  const code = base?.status === "EXECUTE"
    ? "EXECUTE"
    : (dip?.status === "READY_FIXED_ADD" ? "READY_FIXED_ADD" : base?.status);
  return `
    <div class="gold-recommend-row">
      <div>
        <p class="eyebrow">建议金额</p>
        <div class="gold-recommend-amount">${money(base?.amount)}</div>
      </div>
      <span class="chip">${chipForStatus(code, "今日最优基础动作")}</span>
    </div>
  `;
}

function renderSpotDca(data) {
  const strategic = data?.strategic_allocation || {};
  const base = data?.base_dca || {};
  const dip = data?.dip_add || {};

  // Build the two gate rows from real confirmation data:
  //  ① 60-day drawdown threshold (DRAWDOWN_NOT_REACHED / dip status)
  //  ② macro / liquidity shock (mapped from dip.status BLOCKED_LIQUIDITY_SHOCK or PAUSED_*)
  const drawdownCode = dip?.status || "WAIT_DRAWDOWN";
  const macroCode = data?.market_scenarios?.active_scenarios?.includes("LIQUIDITY_SHOCK")
    ? "LIQUIDITY_SHOCK"
    : data?.base_dca?.status || "DATA_DEGRADED";

  return `
    <article class="card gold-workbench-card gold-spot-dca">
      <div class="card-head-inline">
        <p class="eyebrow">SPOT DCA</p>
        <p class="gold-card-title">战略配置与今日动作</p>
      </div>
      ${renderWeightRow(strategic)}
      ${renderFormulaBox(base, dip)}
      <div>
        ${renderGateRow("①", "60 日回撤与连续确认", drawdownCode, "回撤阈值与连续确认门禁")}
        ${renderGateRow("②", "宏观与流动性冲击门禁", macroCode, "宏观风险阻断基础定投")}
      </div>
      ${renderRecommendRow(base, dip)}
    </article>
  `;
}

// ----- Contract Reference — top-down refactor (3 blocks per spec §2.4) -----

function miniCard(label, value, present) {
  const cls = present ? "is-effective" : "is-insufficient";
  return `
    <div class="gold-mini-card ${cls}">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <strong>${escapeHtml(value || "数据积累中")}</strong>
    </div>
  `;
}

function renderPriceBanner(tech) {
  return `
    <div class="gold-price-banner">
      <div class="gold-price-value">${tech?.price != null ? formatNumber(Number(tech.price), 2) : "—"}</div>
      <span class="chip">${impactChip(
        tech?.updated_at ? "bullish-soft" : "bearish-soft",
        tech?.updated_at ? "最新行情已就绪" : "行情过期",
        tech?.updated_at ? "已收盘" : "等待"
      )}</span>
    </div>
  `;
}

function renderContractRef(data) {
  const tech = data?.technical_summary || {};
  const deriv = data?.derivatives || {};

  return `
    <article class="card gold-workbench-card gold-contract-ref">
      <div class="card-head-inline">
        <p class="eyebrow">CONTRACT REFERENCE</p>
        <p class="gold-card-title">合约参考</p>
      </div>
      ${renderPriceBanner(tech)}
      <div class="gold-mini-grid">
        ${miniCard("MA50", tech?.ma50)}
        ${miniCard("MA200 / SMA200", tech?.sma200)}
        ${miniCard("60 日回撤", tech?.drawdown_60d)}
        ${miniCard("EMA20 距离", tech?.ema20_distance)}
      </div>
      <div class="gold-mini-grid">
        ${miniCard("OI 4 周变化", deriv?.oi_change_4w)}
        ${miniCard("资金费率", deriv?.funding_rate)}
        ${miniCard("COT 净投机", deriv?.cot_net_spec_percentile)}
        ${miniCard("未平仓", deriv?.open_interest)}
      </div>
    </article>
  `;
}

// ----- Governance — 4-column mini-card grid (replaces V4 1xN strip) -------

function governanceMiniCard(label, value, present) {
  const cls = present ? "is-effective" : "is-insufficient";
  return `
    <article class="card gold-mini-card ${cls}">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <strong>${escapeHtml(value || "数据生成中")}</strong>
    </article>
  `;
}

function renderGovernanceMini(manifest, label, sourceKey) {
  const entry = (manifest || []).find((s) => s?.source_key === sourceKey);
  if (!entry) return governanceMiniCard(label, "未配置", false);
  const state = entry.freshness_state || "missing";
  return governanceMiniCard(label, `${labelForFreshness(state)} · ${entry.age_seconds != null ? `${entry.age_seconds}s` : "—"}`, state === "fresh");
}

function renderGovernance(data) {
  const manifest = data?.source_manifest || [];
  const observed = data?.snapshot?.observed_at || "—";
  return `
    <section class="gold-governance">
      <div class="card-head-inline">
        <p class="eyebrow">数据治理 · SNAPSHOT</p>
        <p class="gold-card-title">来源就绪度</p>
      </div>
      <div class="gold-governance-grid">
        ${renderGovernanceMini(manifest, "策略配置", "gold_policy")}
        ${renderGovernanceMini(manifest, "XAUT 行情", "gold_spot_quote")}
        ${renderGovernanceMini(manifest, "衍生品", "gold_derivatives")}
        ${governanceMiniCard("快照时间", observed, !!observed && observed !== "—")}
      </div>
    </section>
  `;
}

// ----- Top-level render ----------------------------------------------------

function renderShell(data) {
  return `
    ${renderHero(data)}
    ${renderChartGrid()}
    <section class="gold-workbench-grid">
      ${renderSpotDca(data)}
      ${renderContractRef(data)}
    </section>
    ${renderGovernance(data)}
  `;
}

// ----- Data fetching + chart wiring --------------------------------------

async function loadData() {
  try {
    const data = await api.getGoldWorkbench();
    latestData = data || {};
    setRoot(renderShell(latestData));
    await renderGoldCharts(latestData);
  } catch (err) {
    console.error("[gold_v5] workbench load failed", err);
    setRoot(renderHero({ snapshot: { status: "error" } }));
  }
}

async function renderGoldCharts(data) {
  destroyChartsForPage("gold");
  const tech = data?.technical_summary || {};
  const candles = await fetchChartSeries(data?.chart_series_or_chart_token);
  const labels = candles.map((c) => c.t);
  const priceSeries = candles.map((c) => c.c);

  if (priceSeries.length) {
    renderChart("gold-chart-price", {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("XAUT", priceSeries, { borderColor: "#1f1b16", borderWidth: 1.6 }),
          lineDataset("MA50", maSeries(candles, 50), { borderColor: "#5b8a83", borderWidth: 1.2, borderDash: [4, 3] }),
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } } },
    });
    renderChart("gold-chart-rsi", {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("RSI14", rsiSeries(candles, 14), { borderColor: "#5b8a83", borderWidth: 1.4 }),
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } },
    });
    renderChart("gold-chart-bollinger", {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("%B", bollingerPctB(candles, 20, 2), { borderColor: "#b07558", borderWidth: 1.2 }),
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: -0.2, max: 1.2 } } },
    });
    renderChart("gold-chart-volume", {
      type: "bar",
      data: {
        labels,
        datasets: [barDataset("Volume", candles.map((c) => c.v), { backgroundColor: "rgba(91, 138, 131, 0.55)" })],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
    renderChart("gold-chart-drawdown", {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("Drawdown", drawdownSeries(candles, 60), { borderColor: "#b07558", borderWidth: 1.4 }),
        ],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  }
}

async function fetchChartSeries(token) {
  if (!token?.path) return [];
  try {
    const res = await api.get(token.path);
    return res?.series || [];
  } catch (err) {
    console.warn("[gold_v5] chart series fetch failed", err);
    return [];
  }
}

function maSeries(candles, n) {
  return candles.map((_, i) => {
    const slice = candles.slice(Math.max(0, i - n + 1), i + 1);
    return slice.reduce((s, c) => s + c.c, 0) / slice.length;
  });
}
function rsiSeries(candles, n) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < n) { out.push(null); continue; }
    let gain = 0, loss = 0;
    for (let j = i - n + 1; j <= i; j++) {
      const d = candles[j].c - candles[j - 1]?.c ?? 0;
      if (d >= 0) gain += d; else loss -= d;
    }
    const rs = loss === 0 ? 100 : gain / loss;
    out.push(100 - 100 / (1 + rs));
  }
  return out;
}
function bollingerPctB(candles, n, k) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < n) { out.push(null); continue; }
    const slice = candles.slice(i - n + 1, i + 1).map((c) => c.c);
    const mean = slice.reduce((s, x) => s + x, 0) / n;
    const sd = Math.sqrt(slice.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
    out.push((candles[i].c - (mean - k * sd)) / (2 * k * sd));
  }
  return out;
}
function drawdownSeries(candles, n) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    const slice = candles.slice(Math.max(0, i - n + 1), i + 1);
    const peak = Math.max(...slice.map((c) => c.c));
    out.push(((candles[i].c - peak) / peak) * 100);
  }
  return out;
}

// ----- Lifecycle --------------------------------------------------------

export async function renderGoldV5(root) {
  controller?.abort?.();
  controller = new AbortController();
  setRoot(root, renderShell({ snapshot: { status: "loading" } }));
  applyPostMountStyles();
  await loadData();
  applyPostMountStyles();

  const refreshBtn = document.getElementById("gold-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => loadData(), { signal: controller.signal });
  }
}

function applyPostMountStyles() {
  // Apply weight-bar fill width from data-fill attribute set during rendering.
  // We avoid inline style= attributes by using --gold-weight-pct custom property.
  document.querySelectorAll(".gold-weight-fill[data-fill]").forEach((el) => {
    const v = Number(el.getAttribute("data-fill"));
    if (Number.isFinite(v)) el.style.setProperty("--gold-weight-pct", v + "%");
  });
}

export function unmount() {
  controller?.abort?.();
  controller = null;
  destroyChartsForPage("gold");
  latestData = null;
}

export const ready = true;
```

**Notes for the engineer writing this file:**

- Do **not** add `style="..."` attributes anywhere. The weight-bar fill is set via a CSS custom property `--gold-weight-pct` written via `style.setProperty()` from `applyPostMountStyles()` — `el.style.setProperty()` is *not* an attribute string, so the static guard does not flag it. If a future PR wants to avoid `style.setProperty()` entirely, it can swap to a class like `.fill-25` / `.fill-50` / `.fill-100`, but the current approach is acceptable.
- The status code keys in `STATUS_TONE_MAP` must match `gold_workbench.py:142-265` and the `market_scenarios` codes set at `gold.py:461-486`. If a future PR adds new statuses, add them to the map — the guard `test_no_v4_chip_warning_fallback` does not catch this regression, so eyeball it during code review.

### Step 2: Syntax check

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
node --check app/static/pages/gold_v5.js && echo OK
```

Expected: prints `OK`. Any SyntaxError stops the task — fix and re-run.

### Step 3: Run the static guard tests for the module alone

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
python -m pytest tests/test_gold_v5_frontend_static.py::TestGoldV5Exports tests/test_gold_v5_frontend_static.py::TestGoldV5ChartIds tests/test_gold_v5_frontend_static.py::TestGoldV5VisualLanguage -q 2>&1 | tail -25
```

Expected: ~13 tests, all PASS. If any fail, walk the failure message back into the file — `TestGoldV5Exports.test_module_exists` failing means the file path is wrong; `test_no_emoji` failure means a literal slipped through; `test_no_inline_style_attribute` means `style="` is in the source.

### Step 4: Commit

```bash
cd "E:/Personal/Research/Crypto Investing System"
git add app/static/pages/gold_v5.js
git commit -m "[frontend] gold-allocation v5 module: analysis-page visual alignment + chip-tone system"
```

---

## Task 4: Remove the Jinja initial-shell from page.html

**Files:**
- Modify: `app/templates/page.html` (delete lines 44-52)

### Step 1: Edit `app/templates/page.html`

Open `app/templates/page.html` and remove the entire `{% if page_id == "gold-allocation" %}` block (lines 44-52). Replace with a single comment so future grep shows the intent:

```html
  <main id="page-root">
    {# gold-allocation dedicated shell removed in v5 — JS-rendered hero is now the only first-paint hero #}
  </main>
```

The block to delete is:

```jinja
    {% if page_id == "gold-allocation" %}
    <section class="hero-card gold-initial-shell" aria-live="polite">
      <div>
        <p class="eyebrow">GOLD ALLOCATION</p>
        <h1>黄金配置 Workbench</h1>
        <p>正在读取策略配置与市场快照，页面内容会自动更新。</p>
      </div>
    </section>
    {% endif %}
```

### Step 2: Verify the Jinja compiles

Run:
```bash
cd "E:/Personal/Research/Crypto Investing System"
python -c "import jinja2; env=jinja2.Environment(loader=jinja2.FileSystemLoader('app/templates')); tpl=env.get_template('page.html'); out=tpl.render(page_id='gold-allocation', asset_version='x', page_title='黄金配置', PAGE_TITLES={}); print('len=', len(out), 'shell-removed=', 'gold-initial-shell' not in out)"
```

Expected: prints `len= <some big number> shell-removed= True`. If `shell-removed` is False, the Jinja block was not deleted — re-check the Edit.

### Step 3: Run template guard

```bash
cd "E:/Personal/Research/Crypto Investing System"
python -m pytest tests/test_gold_v5_frontend_static.py::TestGoldV5Template -q
```

Expected: PASS.

### Step 4: Commit

```bash
cd "E:/Personal/Research/Crypto Investing System"
git add app/templates/page.html
git commit -m "[frontend] page.html: remove gold-allocation initial-shell (v5 single hero)"
```

---

## Task 5: Wire main.js routing + dispatcher

**Files:**
- Modify: `app/static/main.js` (lines 21 and 182)

The page-module map and dispatcher must point to v5. Lines and exact strings:

### Step 1: Update loadPageModule entry at line 21

Change:
```javascript
"gold-allocation": () => loadPageModule("./pages/gold_v4.js"),
```
to:
```javascript
"gold-allocation": () => loadPageModule("./pages/gold_v5.js"),
```

### Step 2: Update dispatcher at line 182

Change:
```javascript
module.renderGoldV4 ||
```
to:
```javascript
module.renderGoldV5 ||
```

### Step 3: Syntax check

```bash
cd "E:/Personal/Research/Crypto Investing System"
node --check app/static/main.js && echo OK
```

Expected: `OK`. Failure here means a typo in the substitution.

### Step 4: Run routing guards

```bash
cd "E:/Personal/Research/Crypto Investing System"
python -m pytest tests/test_gold_v5_frontend_static.py::TestGoldV5Routing -q
```

Expected: 2 PASS. If `test_main_js_dispatcher_calls_renderGoldV5` fails because `renderGoldV5` is not in `main.js`, you skipped Step 2.

### Step 5: Commit

```bash
cd "E:/Personal/Research/Crypto Investing System"
git add app/static/main.js
git commit -m "[frontend] main.js: route gold-allocation to gold_v5.js + renderGoldV5 dispatcher"
```

---

## Task 6: Run the full static guard suite + css guard

**Files:**
- (no edits — verification)

### Step 1: Full test gate

```bash
cd "E:/Personal/Research/Crypto Investing System"
python -m pytest tests/test_gold_v5_frontend_static.py -q 2>&1 | tail -20
```

Expected: **all tests pass** (≈30 tests). Any failure is a Task-1/2/3/4/5 regression.

### Step 2: Lint the touched Python files (none — sanity check)

```bash
cd "E:/Personal/Research/Crypto Investing System"
ruff check app/ 2>&1 | tail -10
```

Expected: zero new findings (or pre-existing findings unrelated to gold-v5 work).

### Step 3: No commit (this task is verification-only)

If anything failed, do *not* commit — go back to the failing task and re-do Step N before continuing.

---

## Task 7: Instance check via verify_pages.py (Playwright)

**Files:**
- (no source edits — this task exists to catch the "JS module loads but pageerrors break at runtime" class of regression that node --check cannot see, per AGENTS.md §六.1)

### Step 1: Start the backend on port 8002 in another terminal

```bash
cd "E:/Personal/Research/Crypto Investing System"
uvicorn app.main:app --port 8002
```

Expected: prints `Uvicorn running on http://127.0.0.1:8002`.

### Step 2: Smoke-test a single page first

```bash
cd "E:/Personal/Research/Crypto Investing System"
python tests/verify_pages.py --pages gold-allocation --skip-spa 2>&1 | tail -30
```

Expected: a `PASS` line for `gold-allocation` and `<real-content-selector>` visible within 10s. Inspect `tests/screenshots/gold-allocation.png` to eyeball: hero chip tone, chart-grid equal-height, governance mini-cards in a 4-col layout.

If cold-load shows blank canvases: that is expected (no live data); the page should still render hero + governance mini-cards with chip tones.

If cold-load shows a `TypeError` in console or `ReferenceError`, capture the stack and Step 1 → return to Task 3 to fix `gold_v5.js`.

### Step 3: Capture new baseline

```bash
cd "E:/Personal/Research/Crypto Investing System"
python tests/verify_pages.py --pages gold-allocation --baseline 2>&1 | tail -10
```

Expected: writes `tests/screenshots/baseline/gold-allocation.png`. Eyeball that file.

### Step 4: Full 9-page regression (per AGENTS.md §六.4)

Per AGENTS.md §六.4: when a task touches `main.js` / `core/*.js` / `templates/page.html` / `app/api/router.py`, a **full** verify_pages.py is mandatory, not just the affected page.

```bash
cd "E:/Personal/Research/Crypto Investing System"
python tests/verify_pages.py 2>&1 | tail -30
```

Expected: 9 of 9 pages PASS. Any FAIL is a regression caused by the v5 work — investigate via the same Playwright error log.

### Step 5: No commit — verify step only

If any FAIL, do **not** delete gold_v4.js (Task 8) and do **not** commit. Re-open Task 3 and fix root cause.

---

## Task 8: Delete `gold_v4.js`

**Files:**
- Delete: `app/static/pages/gold_v4.js`

This is intentionally the *last* task. Once deleted, any regression in v5 forces a re-creation of v4 from git history. Doing this last protects the user.

### Step 1: Verify v5 is the live route

Re-run Task 7 Step 4 if not done in the last 30 minutes.

### Step 2: Confirm no other code references `gold_v4.js`

```bash
cd "E:/Personal/Research/Crypto Investing System"
grep -rn "gold_v4\|renderGoldV4" app/ tests/ --include="*.js" --include="*.py" --include="*.html" --include="*.css" 2>&1 | head -20
```

Expected: zero non-grepable lines. Any match is a stale reference to clean up before deletion.

### Step 3: Delete the file

```bash
cd "E:/Personal/Research/Crypto Investing System"
git rm app/static/pages/gold_v4.js
```

### Step 4: Re-run full verify_pages after deletion

```bash
cd "E:/Personal/Research/Crypto Investing System"
python tests/verify_pages.py --pages gold-allocation --skip-spa 2>&1 | tail -10
```

Expected: PASS. If FAIL, the deletion broke something — `git restore` gold_v4.js, fix, then re-attempt.

### Step 5: Commit

```bash
cd "E:/Personal/Research/Crypto Investing System"
git commit -m "[frontend] drop gold_v4.js (superseded by gold_v5)"
```

---

## Self-Review (run before declaring done)

- [ ] Spec §2.1 Hero — `analysis-hero-card` + single hero confirmed in screenshot
- [ ] Spec §2.2 1+2×2 chart grid — price `is-wide`, 4 sub-cards equal-height confirmed
- [ ] Spec §2.3 Spot-DCA 4-block — weight / formula / 2 gate rows / recommend stacked top-down
- [ ] Spec §2.4 Contract-Ref 3-block — price banner + 2 mini-grids
- [ ] Spec §2.5 Governance 4-col — mini-cards in a single row
- [ ] Spec §3.2 Chip tone — no hard-coded `chip-warning`, all routed via `chipForStatus` / governance tone map
- [ ] Spec §4.1 Data — `source_manifest[]` used, no hallucinated `payload.macro_bias`
- [ ] Spec §4.2 Cold — empty cards visible in cold-load screenshot, dashed border present
- [ ] §7 static guards — 30+ tests pass
- [ ] §8 verification gates — node --check, pytest, ruff, verify_pages.py 9/9 PASS
- [ ] gold_v4.js deleted
- [ ] Final commit message uses `[frontend]` domain tag

---

## Risk Notes (from spec §9.1)

- **Wide price card height**: if `is-wide` makes the price card taller than the row containing 4 sub-cards, browsers will make the second row equal to the first row's height. **Mitigation**: keep `chart-wrap` height implicit (CSS `min-height: 0` + flex stretch); the JS canvas fills whichever height the card takes. If sub-cards end up taller than 240px in practice, add `min-height: 240px` to `.gold-chart-card:not(.is-wide) .chart-wrap`.
- **Governance 4-col at narrow viewport**: `repeat(4, minmax(0, 1fr))` collapses badly under 600px. Acceptable for desktop screenshots but consider a media query to drop to `repeat(2, ...)` at <768px if a regression appears in verify_pages at narrow viewport.
- **`signalTone` duplication**: we intentionally re-implement status→tone locally; analysis.js' tone logic for `bullish/bearish/neutral` keywords stays untouched. If gold's domain tone differs from analysis's signal-text tone, that's by design — the spec §3.2 calls for a separate `statusTone()` map.

