# Knowledge Page "出现在 X 个页面" Badge Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heavy `status-chip chip-neutral` cluster on every knowledge-page term card with a single compact "N 页可用 ▾" trigger that reveals a hover/focus popover listing each page and a one-line purpose note — while preserving V1.5.x constraints (no SPA links, `data-test="page-refs"` retained).

**Architecture:** Pure CSS hover/focus popover, no JS state. Frontend-only change touching 3 files (`app/static/pages/knowledge.js`, `app/static/styles.css`, `tests/test_knowledge_catalog.py`). One TDD cycle (failing test → implement → green), then a separate cleanup task, then full verification gate (AGENTS.md §6 / §6.4).

**Tech Stack:** Vanilla ES modules, design-system CSS tokens already present in `app/static/styles.css`, `pytest` + subprocess-driven `node --check` harness in `tests/test_knowledge_catalog.py`.

---

## File map

| File | Responsibility | Action |
|---|---|---|
| `app/static/pages/knowledge.js` | `renderPageRefsBadge(item)` + `KNOWLEDGE_PAGE_NOTE` map | Modify (rewrite `renderPageRefsBadge`, add `KNOWLEDGE_PAGE_NOTE`) |
| `app/static/styles.css` | `.knowledge-page-refs*` CSS block | Modify (append block after `.knowledge-card-actions` at line ~5278) |
| `tests/test_knowledge_catalog.py` | 3 new static tests + node-based DOM assertions | Modify (append 3 tests) |
| `docs/superpowers/specs/2026-07-23-knowledge-page-refs-redesign.md` | Source spec | No change |

---

## Task 1: Add failing test for compact trigger rendering

**Files:**
- Modify: `tests/test_knowledge_catalog.py:212` area (after the existing remount test, before the BTC derivatives tests — add at the end of file is also fine; pick the end-of-file for stability)

- [ ] **Step 1: Append the new test to the end of `tests/test_knowledge_catalog.py`**

Append this exact block (the helper `_node(...)` and `KNOWLEDGE_PAGE_PATH` are already defined at the top of the file, do not re-import them):

```python
def test_knowledge_page_refs_render_compact_trigger() -> None:
    """Each term with page_refs renders a compact button trigger, not chips."""

    payload = _node(
        f"""
globalThis.window = {{ location: {{ hash: '' }}, addEventListener() {{}}, setTimeout() {{}}, clearTimeout() {{}}, requestAnimationFrame(cb) {{ cb(); }} }};
const elements = new Map();
elements.set('knowledge-search', {{ addEventListener() {{}} }});
elements.set('knowledge-page-filter', {{ addEventListener() {{}} }});
elements.set('knowledge-section-filter', {{ addEventListener() {{}} }});
elements.set('knowledge-family-filter', {{ addEventListener() {{}} }});
elements.set('knowledge-level-filter', {{ addEventListener() {{}} }});
let rootInnerHTML = '';
const root = {{
  get innerHTML() {{ return rootInnerHTML; }},
  set innerHTML(value) {{ rootInnerHTML = String(value); }},
}};
globalThis.document = {{
  getElementById(id) {{ return elements.get(id) || null; }},
  querySelector(sel) {{
    if (sel === '.knowledge-metrics') return {{ innerHTML: '', appendChild() {{}} }}; 
    if (sel === '.knowledge-sections') return {{ innerHTML: '' }}; 
    if (sel === '.knowledge-back-top') return {{ addEventListener() {{}} }}; 
    return null;
  }},
  querySelectorAll() {{ return []; }},
}};
globalThis.HTMLElement = function() {{}};
const module = await import('file:///{KNOWLEDGE_PAGE_PATH.as_posix()}?case=compact');
await module.renderKnowledge();
const match = rootInnerHTML.match(/<button[^>]*knowledge-page-refs-trigger[^>]*>([\s\S]*?)<\/button>/);
const popoverMatch = rootInnerHTML.match(/<div[^>]*knowledge-page-refs-popover[^>]*>([\s\S]*?)<\/div>/);
const chipMatch = rootInnerHTML.match(/<span class="status-chip chip-neutral">市场分析<\/span>/);
console.log(JSON.stringify({{
  hasTrigger: Boolean(match),
  triggerText: match ? match[1].replace(/<[^>]+>/g, '').trim() : null,
  hasPopover: Boolean(popoverMatch),
  popoverContainsNote: popoverMatch ? popoverMatch[1].includes('技术指标页') : false,
  stillRendersLegacyChip: Boolean(chipMatch),
}}));
"""
    )

    assert payload["hasTrigger"] is True, "trigger button missing"
    assert "页可用" in (payload["triggerText"] or ""), "trigger text should mention '页可用'"
    assert payload["hasPopover"] is True, "popover div missing"
    assert payload["popoverContainsNote"] is True, "popover must contain a per-page note (e.g. '技术指标页')"
    assert payload["stillRendersLegacyChip"] is False, "legacy chip bubbles must be gone"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_knowledge_catalog.py::test_knowledge_page_refs_render_compact_trigger -v`

Expected: FAIL — `hasTrigger` is `False` and `stillRendersLegacyChip` is `True` because the current code emits `<span class="status-chip chip-neutral">` chips, not the new button trigger.

---

## Task 2: Add failing test for "no SPA link leakage"

**Files:**
- Modify: `tests/test_knowledge_catalog.py` (append)

- [ ] **Step 1: Append the new test to the end of `tests/test_knowledge_catalog.py`**

```python
def test_knowledge_page_refs_popover_does_not_link_to_spa_routes() -> None:
    """No anchor inside .knowledge-page-refs may carry href or data-page-link."""

    payload = _node(
        f"""
globalThis.window = {{ location: {{ hash: '' }}, addEventListener() {{}}, setTimeout() {{}}, clearTimeout() {{}}, requestAnimationFrame(cb) {{ cb(); }} }};
const elements = new Map();
['knowledge-search', 'knowledge-page-filter', 'knowledge-section-filter', 'knowledge-family-filter', 'knowledge-level-filter'].forEach((id) => elements.set(id, {{ addEventListener() {{}} }}));
let rootInnerHTML = '';
const root = {{
  get innerHTML() {{ return rootInnerHTML; }},
  set innerHTML(value) {{ rootInnerHTML = String(value); }},
}};
globalThis.document = {{
  getElementById(id) {{ return elements.get(id) || null; }},
  querySelector(sel) {{
    if (sel === '.knowledge-metrics') return {{ innerHTML: '', appendChild() {{}} }}; 
    if (sel === '.knowledge-sections') return {{ innerHTML: '' }}; 
    if (sel === '.knowledge-back-top') return {{ addEventListener() {{}} }}; 
    return null;
  }},
  querySelectorAll() {{ return []; }},
}};
globalThis.HTMLElement = function() {{}};
const module = await import('file:///{KNOWLEDGE_PAGE_PATH.as_posix()}?case=nolink');
await module.renderKnowledge();
const badge = rootInnerHTML.match(/<div class="knowledge-page-refs"[\s\S]*?<\/div>(?=\s*<\/div>)/);
// Extract only the badge block, then look for href or data-page-link inside it.
const block = badge ? badge[0] : '';
const hrefMatches = (block.match(/href=/g) || []).length;
const dataPageLink = (block.match(/data-page-link=/g) || []).length;
const hasButton = /<button[^>]*type="button"[^>]*knowledge-page-refs-trigger/.test(block);
console.log(JSON.stringify({{
  blockFound: Boolean(badge),
  hrefMatches,
  dataPageLink,
  hasButton,
}}));
"""
    )

    assert payload["blockFound"] is True, "knowledge-page-refs block not found"
    assert payload["hrefMatches"] == 0, "page-refs must not contain href"
    assert payload["dataPageLink"] == 0, "page-refs must not contain data-page-link"
    assert payload["hasButton"] is True, "trigger must be a button[type=button]"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_knowledge_catalog.py::test_knowledge_page_refs_popover_does_not_link_to_spa_routes -v`

Expected: FAIL — `blockFound` is `False` because the current wrapper class is `knowledge-page-refs` but the inner spans are chips without `<button type="button">`, so the regex `<button[^>]*type="button"[^>]*knowledge-page-refs-trigger` does not match. (After Task 4 implementation the test will pass.)

---

## Task 3: Add failing test for per-page purpose notes

**Files:**
- Modify: `tests/test_knowledge_catalog.py` (append)

- [ ] **Step 1: Append the new test to the end of `tests/test_knowledge_catalog.py`**

```python
def test_knowledge_page_refs_popover_lists_pages_with_purpose_notes() -> None:
    """Every known page_ref must appear in the popover with a non-empty note."""

    payload = _node(
        f"""
globalThis.window = {{ location: {{ hash: '' }}, addEventListener() {{}}, setTimeout() {{}}, clearTimeout() {{}}, requestAnimationFrame(cb) {{ cb(); }} }};
const elements = new Map();
['knowledge-search', 'knowledge-page-filter', 'knowledge-section-filter', 'knowledge-family-filter', 'knowledge-level-filter'].forEach((id) => elements.set(id, {{ addEventListener() {{}} }}));
let rootInnerHTML = '';
const root = {{
  get innerHTML() {{ return rootInnerHTML; }},
  set innerHTML(value) {{ rootInnerHTML = String(value); }},
}};
globalThis.document = {{
  getElementById(id) {{ return elements.get(id) || null; }},
  querySelector(sel) {{
    if (sel === '.knowledge-metrics') return {{ innerHTML: '', appendChild() {{}} }}; 
    if (sel === '.knowledge-sections') return {{ innerHTML: '' }}; 
    if (sel === '.knowledge-back-top') return {{ addEventListener() {{}} }}; 
    return null;
  }},
  querySelectorAll() {{ return []; }},
}};
globalThis.HTMLElement = function() {{}};
const module = await import('file:///{KNOWLEDGE_PAGE_PATH.as_posix()}?case=notes');
await module.renderKnowledge();
// Pull every <li>...</li> from inside .knowledge-page-refs-popover
const popover = rootInnerHTML.match(/<div[^>]*knowledge-page-refs-popover[^>]*>([\s\S]*?)<\/div>/);
const listItems = popover ? (popover[1].match(/<li>[\s\S]*?<\/li>/g) || []) : [];
const items = listItems.map((li) => li.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim());
console.log(JSON.stringify({{ itemCount: items.length, samples: items.slice(0, 5) }}));
"""
    )

    assert payload["itemCount"] > 0, "popover should render at least one <li> entry"
    # Every item must contain both a page label and a non-empty note (separated by an em-dash or hyphen)
    for sample in payload["samples"]:
        assert "—" in sample or " - " in sample, f"item missing note separator: {sample!r}"
        assert sample.count("—") >= 1 or sample.count("-") >= 1
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_knowledge_catalog.py::test_knowledge_page_refs_popover_lists_pages_with_purpose_notes -v`

Expected: FAIL — `itemCount == 0` because the current code emits `<span>` chips inside the wrapper, not a popover with `<li>` items.

---

## Task 4: Rewrite `renderPageRefsBadge` and add `KNOWLEDGE_PAGE_NOTE` in `app/static/pages/knowledge.js`

**Files:**
- Modify: `app/static/pages/knowledge.js:205-240` (the `KNOWLEDGE_PAGE_LABEL` map and `renderPageRefsBadge` function)

- [ ] **Step 1: Add the `KNOWLEDGE_PAGE_NOTE` map immediately after `KNOWLEDGE_PAGE_LABEL`**

After the closing `};` of `KNOWLEDGE_PAGE_LABEL` (current end-of-block at line 222), insert:

```js
const KNOWLEDGE_PAGE_NOTE = {
  "market-analysis": "技术指标页",
  "market-structure": "摆动 / 突破 / 回踩",
  "alert-center": "信号 / 风险 / 决策",
  "monitoring-overview": "终端摘要 / 宏观 + 技术汇总",
  "macro-calendar": "宏观日历与观察项",
  "market-events": "新闻 / 事件流",
  "knowledge-base": "知识百科（本页）",
  "risk": "风险 / 仓位 / 失效位",
  "ashare-etf": "A 股 ETF 行情",
  "btc-derivatives": "期货 / 期权 / 资金费率",
};
```

- [ ] **Step 2: Rewrite `renderPageRefsBadge(item)` (current lines 224-240)**

Replace the existing function body with:

```js
function renderPageRefsBadge(item) {
  // Skip self-reference (the term's own knowledge-base page) and unknown
  // page keys (only well-known SPA pages get a label).
  const pageRefs = (item.page_refs || []).filter(
    (key) => key !== "knowledge-base" && KNOWLEDGE_PAGE_LABEL[key],
  );
  if (!pageRefs.length) return "";
  // Popover is rendered eagerly but hidden via CSS until the trigger is
  // hovered or focused. No JS state, no <a> links, no data-page-link —
  // V1.5.x contract: the knowledge page must not surface other SPA routes
  // in its DOM.
  const items = pageRefs
    .map((key) => {
      const label = KNOWLEDGE_PAGE_LABEL[key];
      const note = KNOWLEDGE_PAGE_NOTE[key] || "";
      return `<li><strong>${escapeHtml(label)}</strong><span> — ${escapeHtml(note)}</span></li>`;
    })
    .join("");
  return `
    <div class="knowledge-page-refs" data-test="page-refs">
      <button type="button"
              class="knowledge-page-refs-trigger"
              aria-haspopup="dialog"
              aria-expanded="false"
              data-page-refs-popover>
        <span class="knowledge-page-refs-icon" aria-hidden="true">i</span>
        <span class="knowledge-page-refs-text">${pageRefs.length} 页可用</span>
        <span class="knowledge-page-refs-caret" aria-hidden="true">▾</span>
      </button>
      <div class="knowledge-page-refs-popover" role="dialog" aria-label="术语被引用的页面">
        <p class="knowledge-page-refs-popover-title">该术语被引用：</p>
        <ul class="knowledge-page-refs-popover-list">${items}</ul>
      </div>
    </div>
  `;
}
```

- [ ] **Step 3: Run the three new tests and verify they pass**

Run:
```bash
python -m pytest tests/test_knowledge_catalog.py::test_knowledge_page_refs_render_compact_trigger tests/test_knowledge_catalog.py::test_knowledge_page_refs_popover_does_not_link_to_spa_routes tests/test_knowledge_catalog.py::test_knowledge_page_refs_popover_lists_pages_with_purpose_notes -v
```

Expected: all three PASS. If `test_knowledge_page_refs_popover_does_not_link_to_spa_routes` fails on `blockFound`, double-check that the wrapper class is exactly `knowledge-page-refs` (not e.g. `knowledge-page-refs-block`). If `test_knowledge_page_refs_popover_lists_pages_with_purpose_notes` fails on `itemCount == 0`, confirm the `<ul class="knowledge-page-refs-popover-list">` opens immediately after the title `<p>`.

- [ ] **Step 4: Run the full knowledge test file to confirm no regressions**

Run: `python -m pytest tests/test_knowledge_catalog.py -q`

Expected: all existing tests still pass (including `test_knowledge_page_remounts_when_spa_dom_belongs_to_previous_page` and `test_tooltip_is_concise_and_links_to_knowledge`).

---

## Task 5: Add the `.knowledge-page-refs*` CSS block

**Files:**
- Modify: `app/static/styles.css` (append after the existing `.knowledge-card-actions` block at line ~5278)

- [ ] **Step 1: Verify the design tokens are defined**

Run:
```bash
grep -nE "^\.(surface-elevated|hover-tint|text-strong|neutral|accent-strong|neutral-soft)\b" app/static/styles.css | head -20
```

Expected output: at least one match per token, confirming `var(--surface-elevated)`, `var(--hover-tint)`, `var(--text-strong)`, `var(--neutral)`, `var(--accent-strong)`, `var(--neutral-soft)` are defined. If any are missing, add them as `:root` variables before proceeding (mirror values from existing `.status-chip` / `.chip-neutral` selectors at line ~2304).

- [ ] **Step 2: Insert the CSS block immediately after `.knowledge-card-actions { ... }` (the block ending around line 5283)**

Open `app/static/styles.css`, locate:
```css
.knowledge-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
```

Insert directly after its closing `}`:

```css
/* 2026-07-23: compact page-refs trigger + hover/focus popover.
   Replaces the legacy chip cluster to lower the visual weight of the
   term-card actions row. */
.knowledge-page-refs {
  position: relative;
  display: inline-block;
}

.knowledge-page-refs-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: none;
  background: transparent;
  font-size: 11px;
  font-weight: 500;
  color: var(--neutral);
  opacity: 0.75;
  cursor: help;
  border-radius: 6px;
  transition: opacity 120ms ease, background 120ms ease;
}

.knowledge-page-refs-trigger:hover,
.knowledge-page-refs:focus-within .knowledge-page-refs-trigger {
  opacity: 1;
  background: var(--hover-tint);
}

.knowledge-page-refs-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: var(--neutral-soft);
  color: var(--neutral);
  font-size: 9px;
  font-weight: 700;
  font-style: italic;
}

.knowledge-page-refs-caret {
  font-size: 8px;
  opacity: 0.7;
  margin-left: 1px;
}

.knowledge-page-refs-popover {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 12;
  min-width: 220px;
  max-width: 280px;
  padding: 10px 12px;
  background: var(--surface-elevated, #ffffff);
  border: 1px solid rgba(15, 118, 110, 0.15);
  border-radius: 10px;
  box-shadow: 0 6px 24px rgba(15, 23, 42, 0.08);
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-strong);
  pointer-events: none;
  visibility: hidden;
  opacity: 0;
  transition: opacity 120ms ease;
}

.knowledge-page-refs-trigger:hover + .knowledge-page-refs-popover,
.knowledge-page-refs:focus-within .knowledge-page-refs-popover {
  visibility: visible;
  opacity: 1;
}

.knowledge-page-refs-popover-title {
  margin: 0 0 6px;
  font-weight: 600;
  color: var(--text-strong);
}

.knowledge-page-refs-popover-list {
  margin: 0;
  padding-left: 14px;
}

.knowledge-page-refs-popover-list li {
  margin: 2px 0;
}

.knowledge-page-refs-popover-list strong {
  color: var(--accent-strong);
  margin-right: 4px;
}
```

- [ ] **Step 3: Validate JS syntax (no behavior change, but Task 4's edit must still parse)**

Run: `node --check app/static/pages/knowledge.js`

Expected: exits 0 with no output.

- [ ] **Step 4: Run knowledge tests again to ensure CSS-only change didn't regress anything**

Run: `python -m pytest tests/test_knowledge_catalog.py -q`

Expected: still all green (CSS-only changes don't affect the static tests, but this catches any inadvertent JS edit).

---

## Task 6: Full verification gate (AGENTS.md §6.4)

**Files:** none

- [ ] **Step 1: Run the mandatory static checks**

```bash
node --check app/static/pages/knowledge.js
python -m ruff check .
python -m compileall -q app tests
```

Expected: all exit 0.

- [ ] **Step 2: Run the full pytest suite (or at least the impacted modules)**

```bash
python -m pytest tests/test_knowledge_catalog.py tests/test_knowledge_frontend_static.py -q
```

Expected: 0 failed. If broader regression concerns exist, also run `python -m pytest tests/ -q` and confirm 0 failed.

- [ ] **Step 3: Playwright instance check — full suite (not just knowledge page)**

The AGENTS.md §6.4 rule mandates a full `verify_pages.py` run when a shared page module changes. `knowledge.js` is page-local but the rule for "page module changes → full verify_pages" applies.

Start the backend in a separate terminal first:
```bash
uvicorn app.main:app --port 8002
```
Then in this terminal:
```bash
python tests/verify_pages.py
```

Expected: 11/11 cold-load pages pass, 10/10 SPA switches pass, 0 console/page errors. The `tests/screenshots/knowledge-base.png` will be regenerated — visually confirm the badge now shows the compact "N 页可用 ▾" line in the actions row of each term card.

If any page fails, **stop** and investigate before claiming completion (AGENTS.md §6.1: curl-only is forbidden; rely on the Playwright report at `tests/screenshots/verify_pages_report.json`).

- [ ] **Step 4: Optional — manual visual screenshot review**

Read: `tests/screenshots/knowledge-base.png`

Expected: every term card has a small grey "i  N 页可用 ▾" line in its actions row (no longer the multi-chip cluster). Hover the badge in a browser to confirm the popover appears below-right with the per-page notes.

---

## Task 7: Commit

**Files:** all of the above

- [ ] **Step 1: Stage and commit**

```bash
git add app/static/pages/knowledge.js app/static/styles.css tests/test_knowledge_catalog.py docs/superpowers/specs/2026-07-23-knowledge-page-refs-redesign.md docs/superpowers/plans/2026-07-23-knowledge-page-refs-redesign.md
git status
```

Verify the staged set is exactly the 5 expected files (no screenshots, no `.env`, no runtime artefacts).

```bash
git commit -m "[frontend] knowledge: compact page-refs trigger + hover popover"
```

Expected: commit succeeds with one feature commit. The CHANGELOG / version bump is **out of scope** for this change.

---

## Self-review

**1. Spec coverage:**
- §3 visual before/after → Task 4 (rewrite `renderPageRefsBadge`) + Task 5 (CSS block).
- §4 HTML structure → Task 4 exact template.
- §5 CSS-only interaction → Task 5 `:hover` + `:focus-within`.
- §6 V1.5.x contract (no SPA URL leak) → Task 2 (explicit assertion) + Task 4 (`<button type="button">`, no `<a>`).
- §7 CSS tokens → Task 5 Step 1 verification of `--surface-elevated` / `--hover-tint` etc.
- §8 `KNOWLEDGE_PAGE_NOTE` map → Task 4 Step 1.
- §9.1 existing tests preserved → Task 4 Step 4 + Task 5 Step 4.
- §9.2 new tests → Tasks 1, 2, 3.
- §9.3 verification gate → Task 6.

**2. Placeholder scan:** No "TBD", "TODO", "implement later", or "similar to Task N". Every code block is exact and copy-pastable.

**3. Type consistency:**
- Class names used in Task 4 HTML match Task 5 CSS: `.knowledge-page-refs`, `.knowledge-page-refs-trigger`, `.knowledge-page-refs-icon`, `.knowledge-page-refs-text`, `.knowledge-page-refs-caret`, `.knowledge-page-refs-popover`, `.knowledge-page-refs-popover-title`, `.knowledge-page-refs-popover-list`, `.knowledge-page-refs-popover-list li`, `.knowledge-page-refs-popover-list strong`. ✓
- `KNOWLEDGE_PAGE_NOTE` keys match `KNOWLEDGE_PAGE_LABEL` keys exactly. ✓
- `data-test="page-refs"` preserved on the wrapper (existing test selector still works). ✓
- Test selector `<button[^>]*type="button"[^>]*knowledge-page-refs-trigger` matches the exact Task 4 HTML template. ✓

**Execution handoff:** Plan saved. Choose execution mode next.