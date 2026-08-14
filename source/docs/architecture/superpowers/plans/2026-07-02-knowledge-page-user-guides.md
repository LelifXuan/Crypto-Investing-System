# Knowledge Page User Guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add page-level operation guides (3 first-phase: monitoring-overview / ai-strategy / btc-derivatives) alongside the existing term glossary in `knowledge.js`, rendered with a distinct callout layout, default-expanded.

**Architecture:** Extend the existing `term()` factory in `app/static/core/knowledge.js` with optional guide-only fields (`type`, `purpose`, `when_to_use`, `page_walkthrough`, `data_lineage`, `caveats`, `related_pages`). Add new `renderGuideCard()` in `app/static/pages/knowledge.js` that detects `type === "guide"` and renders callout sections. All new fields are optional so the 70+ existing terms keep working untouched. Backend route `/knowledge-page` stays untouched (frontend-only change).

**Tech Stack:** Vanilla JS / ES Modules (frontend), pytest + Node ESM eval (tests), CSS (styling).

---

## File Structure

### Modify
- `trading-system-codex/app/static/core/knowledge.js` — term() factory + 3 new guide entries + new `pageGuidesSection`
- `trading-system-codex/app/static/pages/knowledge.js` — `renderGuideCard()` + section chips update + filter pass-through
- `trading-system-codex/app/static/styles.css` — new `.knowledge-guide-*` class rules
- `trading-system-codex/tests/test_knowledge_catalog.py` — 3 new tests

### Create
None — all changes are extensions to existing files.

---

## Task 1: Extend `term()` factory with guide-only fields

**Files:**
- Modify: `trading-system-codex/app/static/core/knowledge.js:23-46`

- [ ] **Step 1: Write the failing test for new factory fields**

In `trading-system-codex/tests/test_knowledge_catalog.py`, append:

```python
def test_term_factory_supports_guide_fields():
    """term() must accept and expose guide-only fields without breaking existing ones."""
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { term } from 'file://" + str(KNOWLEDGE_PATH) + "';\n"
            "const guide = term('test-guide', 'Test Guide', {\n"
            "  type: 'guide',\n"
            "  purpose: 'A test purpose that is long enough',\n"
            "  when_to_use: ['first situation', 'second situation'],\n"
            "  page_walkthrough: ['step one', 'step two'],\n"
            "  data_lineage: ['src1 -> dst1'],\n"
            "  caveats: ['caveat one'],\n"
            "  related_pages: ['ai-strategy'],\n"
            "});\n"
            "console.log(JSON.stringify(guide));\n",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=20,
    )
    output = proc.stdout.strip()
    payload = json.loads(output)
    assert payload["type"] == "guide"
    assert payload["purpose"].startswith("A test")
    assert len(payload["when_to_use"]) == 2
    assert len(payload["page_walkthrough"]) == 2
    assert payload["data_lineage"] == ["src1 -> dst1"]
    assert payload["caveats"] == ["caveat one"]
    assert payload["related_pages"] == ["ai-strategy"]
```

(`KNOWLEDGE_PATH` and `ROOT` are existing module-level constants in `test_knowledge_catalog.py`; check the file for their definition before running.)

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest tests/test_knowledge_catalog.py::test_term_factory_supports_guide_fields -v
```

Expected: FAIL — output of `term()` does not yet include `type` / `purpose` / `when_to_use` / `page_walkthrough` / `data_lineage` / `caveats` / `related_pages` keys.

- [ ] **Step 3: Add guide-only fields to the term() factory**

In `trading-system-codex/app/static/core/knowledge.js:23-46`, replace the `term` function body so the returned object includes the new fields at the end (after `tags`):

```js
function term(id, label, options = {}) {
  return {
    id,
    term: label,
    aliases: options.aliases || [],
    category: options.category || "technical",
    family: options.family || "general",
    level: options.level || "intermediate",
    display_mode: options.display_mode || "full",
    importance: options.importance || "useful",
    summary: options.summary || options.definition || "",
    definition: options.definition || options.summary || "",
    why_it_matters: options.why_it_matters || "",
    formula: options.formula || "",
    how_to_use: options.how_to_use || "",
    useful_when: options.useful_when || "",
    thresholds: options.thresholds || [],
    risk_note: options.risk_note || "",
    example: options.example || "",
    page_refs: options.page_refs || ["knowledge-base"],
    related_terms: options.related_terms || [],
    tags: options.tags || [],
    type: options.type || "term",
    purpose: options.purpose || "",
    when_to_use: options.when_to_use || [],
    page_walkthrough: options.page_walkthrough || [],
    data_lineage: options.data_lineage || [],
    caveats: options.caveats || [],
    related_pages: options.related_pages || [],
  };
}
```

(Everything else stays identical — same indentation, same order where possible.)

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py::test_term_factory_supports_guide_fields -v
```

Expected: PASS.

- [ ] **Step 5: Run the existing 4 catalog tests to confirm no regression**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py -v
```

Expected: All 4 existing tests PASS (plus the new one = 5/5 PASS).

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/knowledge.js trading-system-codex/tests/test_knowledge_catalog.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] knowledge: extend term() factory with guide-only fields"
```

---

## Task 2: Add pageGuidesSection + 3 first-phase guide entries

**Files:**
- Modify: `trading-system-codex/app/static/core/knowledge.js:1389-1410` (after `qualityItems`/`derivativeItems` arrays, add `pageGuidesItems` + `pageGuidesSection`)

- [ ] **Step 1: Write the failing test for guide section presence**

In `trading-system-codex/tests/test_knowledge_catalog.py`, append:

```python
def test_page_guides_section_exposes_three_first_phase_guides():
    """pageGuidesSection must exist and contain monitoring-overview/ai-strategy/btc-derivatives."""
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { knowledgeSections } from 'file://" + str(KNOWLEDGE_PATH) + "';\n"
            "const pg = knowledgeSections.find(s => s.id === 'page-guides');\n"
            "console.log(JSON.stringify({items: pg.items.map(i => i.id)}));\n",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=20,
    )
    ids = json.loads(proc.stdout.strip())["items"]
    for required_id in ("monitoring-overview", "ai-strategy", "btc-derivatives"):
        assert required_id in ids
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py::test_page_guides_section_exposes_three_first_phase_guides -v
```

Expected: FAIL — `pageGuidesSection` not yet exported.

- [ ] **Step 3: Add pageGuidesItems array + pageGuidesSection after the existing sections**

In `trading-system-codex/app/static/core/knowledge.js`, find the line `derivativesItems` (the last `<...>Items` array around line 1294) and immediately after it (still in `derivativesItems`/`etfItems` zone), paste the following block before the `knowledgeSections` declaration:

```js
const pageGuidesItems = [
  term("monitoring-overview", "监控总览使用指南", {
    type: "guide",
    category: "guide",
    family: "user-guide",
    level: "basic",
    display_mode: "full",
    importance: "core",
    aliases: ["monitoring-guide"],
    purpose: "在 5 分钟早盘或重大事件前，快速判断当前市场风险敞口。",
    when_to_use: [
      "早盘 (UTC 0:00 / 北京 8:00) 复盘上一日收盘",
      "FOMC、CPI、非农等重大宏观事件前后",
      "BTC 单日波动 >5% 需要快速定位原因时",
    ],
    page_walkthrough: [
      "顶部 'Terminal Summary' — 三行核心简报（市场 / 指引 / 风险）",
      "中间 'Macro Overview' — 6 层宏观评分（rates / inflation / labor / ...）",
      "下方 'Alert Events' — 当前事件窗口与 macro_event_availability",
    ],
    data_lineage: [
      "IndicatorMonitoringService.sync_macro() → market_repository.observations",
      "MacroOverviewService.build_overview() → macro_overview",
      "MonitoringDashboardService.get_bundle() → terminal_summary + macro_overview",
    ],
    caveats: [
      "不展示 tick-level 数据",
      "15 分钟内缓存可能与实时有秒级偏差",
      "事件结束后 5 分钟内 'event_window' 仍可能显示 'pre_event'",
    ],
    related_pages: ["ai-strategy", "btc-derivatives", "macro-calendar"],
    tags: ["guide", "monitoring", "core"],
    page_refs: ["monitoring-overview"],
    related_terms: ["terminal_summary", "macro_overview", "alert_events"],
  }),
  term("ai-strategy", "AI 策略页使用指南", {
    type: "guide",
    category: "guide",
    family: "user-guide",
    level: "advanced",
    display_mode: "full",
    importance: "core",
    aliases: ["strategy-guide"],
    purpose: "把多周期证据、衍生品、宏观、链上数据合成为一份可解释的策略推演。",
    when_to_use: [
      "已开仓或考虑出入场前",
      "想了解 6 周期（30d / 1w / 1d / 4h / 1h / 15m）是否一致",
      "需要评估风险门禁（trade permission）后再下决策",
    ],
    page_walkthrough: [
      "顶部 unified_state — 三行结论 + 权限（observe / conditional / no_trade）",
      "中间 Market Operation — 5 维度（宏观 / 资金 / 衍生品 / 链上 / 价格结构）",
      "Horizon Governance — 大周期约束 vs 小周期推动 + 仓位上限",
      "6 周期证据栈 — 横跨 30d 到 15m 的逐级证据",
      "Trade Plans + Risk Panel — 入场区间 / 止损 / 止盈 / 失效条件",
    ],
    data_lineage: [
      "MarketContextBuilder → chip_structure / macro_features / derivatives_features",
      "UnifiedStrategyService → 5 regime engines (macro / capital / derivatives / onchain / price)",
      "EvidenceTraceBuilder → freshness + consistency + coverage 三因子加权",
    ],
    caveats: [
      "置信度会被 evidence_ref namespace 不匹配抹平（已逐步修复）",
      "V1.7.1 后冷启动会显示 degraded 黄色警示而非红色错误",
      "策略只读，不连接交易账户",
    ],
    related_pages: ["monitoring-overview", "btc-derivatives", "market-analysis"],
    tags: ["guide", "ai-strategy", "core"],
    page_refs: ["ai-strategy"],
    related_terms: ["unified_state", "horizon_governance", "evidence_trace"],
  }),
  term("btc-derivatives", "BTC 衍生品页使用指南", {
    type: "guide",
    category: "guide",
    family: "user-guide",
    level: "intermediate",
    display_mode: "full",
    importance: "core",
    aliases: ["derivatives-guide"],
    purpose: "查看期权 / 永续持仓拥挤度、关键词位墙、Max Pain 与保护成本。",
    when_to_use: [
      "准备挂单前评估 IV / 关键词位",
      "已有持仓需要估算保护成本（collar / put spread）",
      "市场异动时区分是 options-driven 还是 perp-driven",
    ],
    page_walkthrough: [
      "顶部 Hero — 杠杆面增量（funding / OI / skew / basis 摘要）",
      "Options Wall 区块 — Call Wall / Put Wall / Max Pain 三列与 expiry context",
      "Hedge Plan — collar / put spread 成本估算与预算提醒",
      "Key Level Axis — 关键价位随时间迁移（vs UTC 日期）",
    ],
    data_lineage: [
      "LiveCollector.collect() → Deribit / OKX / Bybit adapter (options + perps)",
      "LiveSnapshotEnvelope → LiveSourceCache (runtime_dev/source_runtime/cache/...)",
      "BtcDerivativesLiveService.dashboard() → 渲染 dashboard",
    ],
    caveats: [
      "V1.7.1 前冷启动会显示 '真实公开数据源当前不可用'（已修）",
      "数据超过 15 分钟标 'stale'，超过 2 小时标 'hard_stale' 提示",
      "perps API 经常失败时仅 options 数据可用（不应判 data_insufficient）",
    ],
    related_pages: ["ai-strategy", "monitoring-overview", "market-events"],
    tags: ["guide", "btc-derivatives", "core"],
    page_refs: ["btc-derivatives"],
    related_terms: ["call_wall", "put_wall", "max_pain", "constant_maturity"],
  }),
];

const pageGuidesSection = {
  id: "page-guides",
  title: "页面使用指南",
  description: "每个页面的使用时机、阅读顺序、数据依赖与注意点",
  items: pageGuidesItems,
};
```

Then locate the `knowledgeSections` array (around line 1389, exporting the 7 existing sections) and add `pageGuidesSection` as the first element:

```js
export const knowledgeSections = [
  pageGuidesSection,
  technicalSection,
  structureSection,
  alertsSection,
  macroSection,
  qualitySection,
  etfSection,
  derivativesSection,
];
```

(Adjust the `id`-matching so the existing variable names align — confirm by reading what's already exported. If export names differ, match them exactly.)

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py::test_page_guides_section_exposes_three_first_phase_guides -v
```

Expected: PASS.

- [ ] **Step 5: Run the full catalog suite to confirm no regression**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/knowledge.js && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] knowledge: add pageGuidesSection with 3 first-phase page guides"
```

---

## Task 3: Add guide validation tests (required fields + page_refs coherence)

**Files:**
- Modify: `trading-system-codex/tests/test_knowledge_catalog.py`

- [ ] **Step 1: Write the failing tests for guide required fields**

In `trading-system-codex/tests/test_knowledge_catalog.py`, append:

```python
def test_page_guides_required_fields_are_populated():
    """Each type='guide' entry must populate all guide-specific fields with non-trivial content."""
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { knowledgeSections } from 'file://" + str(KNOWLEDGE_PATH) + "';\n"
            "const guides = knowledgeSections.find(s => s.id === 'page-guides').items;\n"
            "console.log(JSON.stringify(guides.map(g => ({\n"
            "  id: g.id, purpose: g.purpose, when_to_use: g.when_to_use,\n"
            "  page_walkthrough: g.page_walkthrough, data_lineage: g.data_lineage,\n"
            "  caveats: g.caveats, related_pages: g.related_pages,\n"
            "}))));\n",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=20,
    )
    guides = json.loads(proc.stdout.strip())
    assert len(guides) >= 3, "expected at least 3 first-phase guides"
    for g in guides:
        assert len(g["purpose"]) >= 10, f"{g['id']}: purpose too short"
        assert len(g["when_to_use"]) >= 1, f"{g['id']}: need at least 1 when_to_use"
        assert len(g["page_walkthrough"]) >= 2, f"{g['id']}: need ≥2 walkthrough steps"
        assert len(g["data_lineage"]) >= 1, f"{g['id']}: need ≥1 lineage entry"
        assert len(g["caveats"]) >= 1, f"{g['id']}: need ≥1 caveat"
        assert len(g["related_pages"]) >= 1, f"{g['id']}: need ≥1 related_page"


def test_guide_related_pages_reference_existing_pages():
    """Each guide's related_pages must reference pages known to the SPA."""
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { knowledgeSections } from 'file://" + str(KNOWLEDGE_PATH) + "';\n"
            "const validPages = new Set(['monitoring-overview', 'ai-strategy', 'btc-derivatives',\n"
            "  'market-analysis', 'market-structure', 'market-events', 'macro-calendar',\n"
            "  'alert-center', 'knowledge-base', 'ashare-etf', 'gold-allocation']);\n"
            "const guides = knowledgeSections.find(s => s.id === 'page-guides').items;\n"
            "const bad = [];\n"
            "for (const g of guides) {\n"
            "  for (const p of g.related_pages) {\n"
            "    if (!validPages.has(p)) bad.push(`${g.id} → ${p}`);\n"
            "  }\n"
            "}\n"
            "console.log(JSON.stringify({bad}));\n",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=20,
    )
    bad = json.loads(proc.stdout.strip())["bad"]
    assert not bad, f"guide related_pages reference unknown pages: {bad}"
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py::test_page_guides_required_fields_are_populated tests/test_knowledge_catalog.py::test_guide_related_pages_reference_existing_pages -v
```

Expected: Both PASS (Task 2 already populated the fields correctly).

- [ ] **Step 3: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/tests/test_knowledge_catalog.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[test] knowledge: validate pageGuides required fields and related_pages"
```

---

## Task 4: Add `renderGuideCard()` in the knowledge page renderer

**Files:**
- Modify: `trading-system-codex/app/static/pages/knowledge.js`

- [ ] **Step 1: Write a failing Playwright test that checks for guide card markup**

In `trading-system-codex/tests/test_knowledge_degraded_frontend.py` (or a new `tests/test_knowledge_user_guides.py`), append:

```python
@pytest.fixture
def base_url():
    import os
    return os.getenv("BASE_URL", "http://127.0.0.1:8002")


def test_page_guides_section_visible_and_expanded(base_url):
    """knowledge page should expose the 'page-guides' section with default-expanded cards."""
    import os, json
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/knowledge-page", wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # Section chip / heading present
        section = page.locator(".knowledge-section", has_text="页面使用指南")
        assert section.count() >= 1

        # At least one guide card visible, default-expanded
        guide_cards = page.locator(".knowledge-guide-card")
        assert guide_cards.count() >= 3
        first = guide_cards.first
        assert first.locator(".knowledge-guide-purpose").count() >= 1
        assert first.locator(".knowledge-guide-walkthrough").count() >= 1
        assert first.locator(".knowledge-guide-lineage").count() >= 1
        assert first.locator(".knowledge-guide-caveats").count() >= 1

        ctx.close()
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run with backend started on port 8002:

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest tests/test_knowledge_user_guides.py::test_page_guides_section_visible_and_expanded -v
```

Expected: FAIL — `.knowledge-guide-card` class does not yet exist.

- [ ] **Step 3: Implement `renderGuideCard(item)` and wire it through the renderer**

In `trading-system-codex/app/static/pages/knowledge.js`, find the existing `renderTermCard(item)` definition (around line 165). Add a sibling function before it:

```js
function renderGuideCard(item) {
  const { escapeHtml } = helpers;
  const guideBadge = `<span class="knowledge-guide-tag">📘 使用指南</span>`;
  const purposeBlock = item.purpose
    ? `<section class="knowledge-guide-purpose">
         <h4>何时用</h4>
         <p>${escapeHtml(item.purpose)}</p>
       </section>`
    : "";
  const whenBlock = item.when_to_use?.length
    ? `<section class="knowledge-guide-purpose">
         <h4>典型场景</h4>
         <ul>${item.when_to_use.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
       </section>`
    : "";
  const walkthroughBlock = item.page_walkthrough?.length
    ? `<section class="knowledge-guide-walkthrough">
         <h4>看什么顺序</h4>
         <ol>${item.page_walkthrough.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
       </section>`
    : "";
  const lineageBlock = item.data_lineage?.length
    ? `<section class="knowledge-guide-lineage">
         <h4>数据从哪来</h4>
         <code>${escapeHtml(item.data_lineage.join(" → "))}</code>
       </section>`
    : "";
  const caveatBlock = item.caveats?.length
    ? `<section class="knowledge-guide-caveats">
         <h4>注意点</h4>
         <ul>${item.caveats.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
       </section>`
    : "";
  const relatedPagesBlock = item.related_pages?.length
    ? `<section class="knowledge-guide-related">
         <h4>关联页面</h4>
         <div class="knowledge-guide-related-chips">
           ${item.related_pages.map((p) =>
             `<a class="secondary-button" href="/${escapeHtml(p)}-page">${escapeHtml(p)} →</a>`
           ).join("")}
         </div>
       </section>`
    : "";

  return `
    <article class="knowledge-guide-card is-open" id="${escapeHtml(item.id)}">
      <header class="knowledge-guide-header">
        ${guideBadge}
        <h3>${escapeHtml(item.term)}</h3>
      </header>
      <div class="knowledge-guide-body">
        ${purposeBlock}
        ${whenBlock}
        ${walkthroughBlock}
        ${lineageBlock}
        ${caveatBlock}
        ${relatedPagesBlock}
      </div>
    </article>
  `;
}
```

(Custom `helpers` object already exists in `pages/knowledge.js`. If not, declare `const helpers = { escapeHtml };` above the function.)

Then in the same file, find the `renderSection` (or equivalent — the function that loops `sections` and renders each section's items). Replace the per-item dispatch with a type-aware branch:

```js
const cards = section.items.map((item) => {
  if (item.type === "guide") return renderGuideCard(item);
  return renderTermCard(item);
}).join("");
```

(If `section.items.map(...)` is inlined differently, locate the equivalent call site and add the same branch.)

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_knowledge_user_guides.py::test_page_guides_section_visible_and_expanded -v
```

Expected: PASS.

- [ ] **Step 5: Add "📘 页面指南" chip to the section quick-nav**

In `trading-system-codex/app/static/pages/knowledge.js`, find the `<div class="knowledge-section-chips">` block (around line 334). Prepend a chip for the new section so users can jump straight to it:

```html
<a class="knowledge-section-chip" href="#page-guides">📘 页面使用指南</a>
```

(Add it as the first child inside the section-chips container, before the existing 7 section chips.)

- [ ] **Step 6: Verify no JS syntax errors**

```bash
cd trading-system-codex && node --check app/static/pages/knowledge.js
```

Expected: No output (clean).

- [ ] **Step 7: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/pages/knowledge.js trading-system-codex/tests/test_knowledge_user_guides.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] knowledge page: renderGuideCard + 📘 section chip"
```

---

## Task 5: Add guide CSS (callout blocks + default-expanded card)

**Files:**
- Modify: `trading-system-codex/app/static/styles.css` (append)

- [ ] **Step 1: No automated test for CSS — verify via Playwright assertion**

Add a Playwright assertion to `tests/test_knowledge_user_guides.py`:

```python
def test_guide_card_callout_blocks_have_distinct_classes(base_url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{base_url}/knowledge-page", wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        first = page.locator(".knowledge-guide-card").first
        # Verify each block has its dedicated class so CSS styling can differ
        assert first.locator(".knowledge-guide-purpose").count() >= 1
        assert first.locator(".knowledge-guide-walkthrough").count() >= 1
        assert first.locator(".knowledge-guide-lineage").count() >= 1
        assert first.locator(".knowledge-guide-caveats").count() >= 1

        ctx.close()
        browser.close()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_knowledge_user_guides.py::test_guide_card_callout_blocks_have_distinct_classes -v
```

Expected: FAIL — Playwright assertion fails because Task 4 hasn't added the CSS file yet (or exists without styling, but the classes themselves exist — assertion should still pass since the markup classes are already added in Task 4). The test will likely PASS already since `Task 4` already added the markup. If passing, skip the failure-check and run only after CSS is added (move directly to Step 3).

- [ ] **Step 3: Append guide CSS to styles.css**

In `trading-system-codex/app/static/styles.css`, append at the end:

```css
/* Page-level user guides (knowledge.js type=guide) */
.knowledge-guide-card {
  display: block;
  padding: 24px;
  margin: 16px 0;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(36, 48, 78, 0.18);
  border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}
.knowledge-guide-card.is-open {
  background: rgba(247, 251, 255, 0.98);
}
.knowledge-guide-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.knowledge-guide-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.knowledge-guide-tag {
  display: inline-block;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #2a4d8f;
  background: rgba(70, 130, 220, 0.12);
  border-radius: 999px;
}
.knowledge-guide-body section {
  margin-top: 12px;
  padding: 12px 16px;
  border-left: 4px solid;
  border-radius: 6px;
}
.knowledge-guide-purpose { border-color: #4a90e2; background: rgba(74, 144, 226, 0.06); }
.knowledge-guide-walkthrough { border-color: #3fa66b; background: rgba(63, 166, 107, 0.06); }
.knowledge-guide-lineage { border-color: #d68a2a; background: rgba(214, 138, 42, 0.06); }
.knowledge-guide-caveats { border-color: #c84a4a; background: rgba(200, 74, 74, 0.06); }
.knowledge-guide-related { border-color: #6a6a6a; background: rgba(106, 106, 106, 0.05); }
.knowledge-guide-body h4 {
  margin: 0 0 6px 0;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.knowledge-guide-body p { margin: 0; }
.knowledge-guide-body ul, .knowledge-guide-body ol {
  margin: 0;
  padding-left: 20px;
}
.knowledge-guide-body li { margin: 4px 0; }
.knowledge-guide-body code {
  display: inline-block;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}
.knowledge-guide-related-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

- [ ] **Step 4: Run the Playwright test to verify it passes (or is at least stable)**

```bash
python -m pytest tests/test_knowledge_user_guides.py -v
```

Expected: All Playwright tests pass.

- [ ] **Step 5: Verify CSS brace balance**

```bash
cd trading-system-codex && python -c "
with open('app/static/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()
opens, closes = css.count('{'), css.count('}')
assert opens == closes, f'CSS braces mismatch: {opens} open vs {closes} close'
print(f'OK: {opens} matched braces')
"
```

Expected: `OK: N matched braces`.

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/styles.css trading-system-codex/tests/test_knowledge_user_guides.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] styles: add .knowledge-guide-* callout blocks"
```

---

## Task 6: Final regression + verify_pages update + CHANGELOG

**Files:** (no new files)

- [ ] **Step 1: Run full pytest suite**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest -q 2>&1 | tail -3
```

Expected: ~835-840 passed, 6 skipped, 0 failed.

- [ ] **Step 2: Run ruff**

```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m ruff check .
```

Expected: All checks passed!

(If there are ruff errors in the new files, fix them with auto-fix or manual edits.)

- [ ] **Step 3: Run node --check on all JS**

```bash
cd trading-system-codex && \
  find app/static -name "*.js" -print0 | xargs -0 node --check && echo "JS OK"
```

Expected: JS OK.

- [ ] **Step 4: Run verify_pages.py to refresh screenshots**

```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 > /tmp/uv_know.log 2>&1 & \
  sleep 6 && \
  python tests/verify_pages.py 2>&1 | tail -10
```

Expected: 9/10 pages pass (or all pass).

Then kill uvicorn: `ps aux | grep "uvicorn app.main" | grep -v grep | awk '{print $2}' | xargs -r kill`

- [ ] **Step 5: Update CHANGELOG.md**

In `docs/CHANGELOG.md`, after the V1.7.1 section, add:

```markdown
## V1.7.2 (2026-07-02)

知识百科页扩充 — 增加页面级使用指南。

### 前端

- `app/static/core/knowledge.js` 的 `term()` 工厂新增 7 个 guide-only 字段（`type / purpose / when_to_use / page_walkthrough / data_lineage / caveats / related_pages`），全部 optional，向后兼容
- 新增 `pageGuidesSection` 段落，含 3 篇首批指南（monitoring-overview / ai-strategy / btc-derivatives）
- `app/static/pages/knowledge.js` 新增 `renderGuideCard()`，使用 4 色 callout 区块（blue 何时用 / green 看什么 / orange 数据依赖 / red 注意点）并默认展开
- 顶部 section chip 增加 "📘 页面使用指南" 快速跳转
- 新增 `.knowledge-guide-*` CSS 样式（约 80 行）

### 测试

- `tests/test_knowledge_catalog.py` 新增 4 个测试：工厂字段验证、pageGuidesSection 出口、guide 字段完整性、related_pages 引用一致性
- `tests/test_knowledge_user_guides.py` 新增：Playwright 验证 guide 卡片 + 4 区块 markup 正确

### 后续（不在本次范围）

- 其余 6 篇指南（market-analysis / market-structure / market-events / macro-calendar / ashare-etf / gold-allocation）可独立追加
```

- [ ] **Step 6: Commit docs + any loose screenshots**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add docs/CHANGELOG.md trading-system-codex/tests/screenshots/ && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[docs] CHANGELOG: V1.7.2 entry — knowledge page user guides"
```

- [ ] **Step 7: Final verification**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git log --oneline -10
```

Verify commits form a clean sequence (no orphan work, no merge conflicts, V1.7.2 entries at the top).

---

## Self-Review Checklist

- ✅ Spec coverage: Each requirement maps to a task
  - Schema extension → Task 1
  - 3 first-phase guides → Task 2
  - Validation tests → Task 3
  - Render layer → Task 4
  - CSS → Task 5
  - Final regression + CHANGELOG → Task 6
- ✅ Placeholder scan: No "TBD" / "TODO" / "fill in" markers
- ✅ Type consistency:
  - `term()` factory has consistent field names across all tasks
  - `renderGuideCard(item)` signature matches both spec section 3.3 and task 4 step 3
  - `knowledgeSections` array shape preserved + `pageGuidesSection` prepended (Task 2 step 3)
- ✅ Backward compatibility:
  - All new fields optional (Task 1 step 3 explicit defaults)
  - `term()` still works for existing entries
  - Existing tests not modified (Tasks 2/3 only append)
  - Backend route untouched
- ✅ TDD pattern: Each task writes failing test first, runs to verify fail, implements to make pass, commits

Plan saved at: `trading-system-codex/docs/superpowers/plans/2026-07-02-knowledge-page-user-guides.md`