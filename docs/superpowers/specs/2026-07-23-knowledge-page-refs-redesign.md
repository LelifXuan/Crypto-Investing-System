# Knowledge Page "出现在 X 个页面" Badge Redesign

**Status:** Approved for implementation
**Date:** 2026-07-23
**Scope:** Frontend-only — knowledge page (`app/static/pages/knowledge.js`) and shared CSS (`app/static/styles.css`)

## 1. Problem

Each term card on the knowledge page currently renders a row of three to four grey `status-chip chip-neutral` bubbles in its `knowledge-card-actions` slot:

```
出现在 3 个页面：[市场分析] [形态结构] [告警中心]
```

The badge is informationally useful but visually heavy. The chips compete with the term title and summary for attention, dominate the right side of every term card, and cumulatively turn the knowledge grid into a "chip field" instead of a glossary. Since `term()` entries commonly reference 2-4 pages, almost every card in `technical` / `structure` / `alert` / `macro` sections shows this cluster.

The user described it as occupying too much space and looking ugly.

## 2. Goals and non-goals

**Goals**
- Reduce default visual weight of the page-refs area by ~75 %.
- Preserve all the information — page names and counts must remain accessible.
- Keep the badge a **non-interactive, non-linking** element (V1.5.x hard constraint; see §6).
- Add a one-line purpose description per page in a hover popover, raising information density.
- Zero regression risk to existing tests and to SPA router behaviour.

**Non-goals**
- Do not turn the page-refs into navigable links to other SPA pages.
- Do not change the `term()` schema, the catalog data, or any backend code.
- Do not introduce a new page module or rewrite `knowledge.js`.
- Do not change the top navigation tabs or the per-card "展开详情" button (out of scope of this request).
- Do not require JS controller changes.

## 3. Visual before / after

**Before** (current):
```
出现在 3 个页面：[市场分析][形态结构][告警中心]
```
Three grey rounded chips plus a label, occupying the full width of the actions row.

**After**:
```
[i] 3 页可用 ▾
```
One compact line — a circular info glyph, the count, and a caret — anchored top-right of the card. On `:hover` or `:focus-within`, a popover fades in below the trigger (right-aligned) listing every page with a short purpose string:

```
┌─────────────────────────────────────┐
│ 该术语被引用：                       │
│                                     │
│ • 市场分析 — 技术指标页              │
│ • 形态结构 — 摆动 / 突破 / 回踩     │
│ • 告警中心 — 信号 / 风险 / 决策     │
└─────────────────────────────────────┘
```

## 4. HTML structure

The `renderPageRefsBadge(item)` function in `app/static/pages/knowledge.js` produces this DOM:

```html
<div class="knowledge-page-refs" data-test="page-refs">
  <button type="button"
          class="knowledge-page-refs-trigger"
          aria-haspopup="dialog"
          aria-expanded="false"
          data-page-refs-popover>
    <span class="knowledge-page-refs-icon" aria-hidden="true">i</span>
    <span class="knowledge-page-refs-text">${count} 页可用</span>
    <span class="knowledge-page-refs-caret" aria-hidden="true">▾</span>
  </button>
  <div class="knowledge-page-refs-popover" role="dialog" aria-label="术语被引用的页面">
    <p class="knowledge-page-refs-popover-title">该术语被引用：</p>
    <ul class="knowledge-page-refs-popover-list">
      ${pageRefs.map((key) => `
        <li>
          <strong>${escapeHtml(KNOWLEDGE_PAGE_LABEL[key])}</strong>
          <span>— ${escapeHtml(KNOWLEDGE_PAGE_NOTE[key])}</span>
        </li>
      `).join("")}
    </ul>
  </div>
</div>
```

**Hard constraints honoured**
- No `<a href>`, no `data-page-link`, no router references — the badge is **never** a navigation target.
- `data-test="page-refs"` is preserved on the outer wrapper so existing tests that locate the badge still resolve.
- The popover is rendered into the DOM eagerly (so it works with CSS-only hover); it is hidden via `visibility: hidden` + `opacity: 0`, never removed.

## 5. Interaction model

**Primary mechanism: pure CSS `:hover` and `:focus-within`.**
- The trigger is a `<button>` so it is keyboard-focusable.
- `:focus-within` on the wrapper exposes the popover to keyboard users (Tab → focus trigger → popover visible).
- The popover uses `pointer-events: none` so it never blocks clicks on neighbouring controls.

**Why no JS state:**
- Knowledge page is desktop-first (other parts of the UI, like the `term` hover popovers, also rely on hover).
- Avoids touching `renderKnowledge()` or the controller shape (`mount`/`unmount`/`pause`/`resume`).
- Zero regression risk to existing SPA / boot behaviour.

**Touch / mobile fallback:**
- Hover-only is a known limitation, inherited from the prior design (which was `<span>`-only, also hover-blind). Out of scope to fix in this change.

## 6. Why this preserves the V1.5.x "knowledge-page replaces its parent" contract

The `test_knowledge_page_remounts_when_spa_dom_belongs_to_previous_page` test in `tests/test_knowledge_catalog.py` enforces that **no other SPA page's URL may appear in the knowledge-page DOM**. The badge must therefore be purely informational.

The redesign uses a `<button type="button">` with no `href`, no `data-page-link`, no form submission. It does not push history, does not trigger the SPA click handler in `app/static/main.js`, and does not appear in `PAGE_TITLES` / `pageModules`. The popover text is informational only.

A new test assertion (§9) explicitly verifies that no anchor element rendered by `renderPageRefsBadge` carries `href` or `data-page-link`, locking the constraint.

## 7. CSS specification

Add to `app/static/styles.css` in the existing `.knowledge-*` block (currently around line 5278). All values are tokens already in the design system; no new colors are introduced.

```css
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

Notes:
- `var(--surface-elevated)` is defined in `app/static/styles.css` (existing design-system token, fallback to `#fff`).
- `var(--neutral)`, `var(--neutral-soft)`, `var(--accent-strong)`, `var(--text-strong)`, `var(--hover-tint)` are existing tokens used by `.status-chip` and `.chip-neutral`.
- The popover is `right: 0` so it expands leftward and stays inside the card; the card has no `overflow: hidden` ancestor.

## 8. Data extension — one-line purpose strings

Add a `KNOWLEDGE_PAGE_NOTE` map next to `KNOWLEDGE_PAGE_LABEL` in `app/static/pages/knowledge.js`. Every key already in `KNOWLEDGE_PAGE_LABEL` gets a short purpose string:

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

If `KNOWLEDGE_PAGE_NOTE[key]` is missing for some reason (defensive — every label has a matching note today), fall back to the empty string so the popover still renders the page name with a `— ` separator.

## 9. Testing

### 9.1 Existing tests — must keep passing

- `tests/test_knowledge_catalog.py::test_knowledge_page_remounts_when_spa_dom_belongs_to_previous_page`
  → Verifies no SPA route URL leaks into the knowledge DOM. Still passes because the trigger is a `<button>` with no `href` and no `data-page-link`, and the popover text contains no path-like strings.
- Any test that locates `[data-test="page-refs"]` still resolves because the outer wrapper keeps that attribute.
- `tests/test_knowledge_frontend_static.py` (and any DOM-contract tests) — the trigger class is `.knowledge-page-refs-trigger`, the wrapper class is `.knowledge-page-refs` (unchanged). No new assertions required; a repo-wide grep for `page-refs` confirms only `app/static/pages/knowledge.js` references the badge today, so no test currently asserts the chip-bubble shape.

### 9.2 New static tests to add to `tests/test_knowledge_catalog.py`

```python
def test_knowledge_page_refs_render_compact_trigger() -> None:
    """Badge must be a non-link button with a hidden popover, no chip bubbles."""

def test_knowledge_page_refs_popover_does_not_link_to_spa_routes() -> None:
    """No anchor under .knowledge-page-refs may carry href or data-page-link."""

def test_knowledge_page_refs_popover_lists_pages_with_purpose_notes() -> None:
    """Each known page_ref must appear in the popover with a non-empty note."""
```

Each test renders the page module, inspects the DOM, and asserts the new structure.

### 9.3 Manual verification gate (AGENTS.md §6.1, §6.2, §6.4)

1. `node --check app/static/pages/knowledge.js` (no syntax regressions).
2. `python -m ruff check .` and `python -m pytest -q tests/test_knowledge_catalog.py` pass.
3. **Full** `python tests/verify_pages.py` (not just `--pages knowledge-base`) — required because `app/static/pages/knowledge.js` is changed and the AGENTS.md §6.4 rule applies even though only one page renders the change.
4. Visual screenshot review: `tests/screenshots/knowledge-base.png` should show the new compact badge across the term cards.

## 10. Risks and follow-ups

**Risks**
- *Token fallbacks*: if `var(--surface-elevated)` is not defined, the fallback `#fff` is used, which may not match the dark theme on pages that opt into a dark surface. Mitigated by `--surface-elevated` being present in the design-system block (confirmed during implementation phase).
- *Existing DOM-contract test*: any test that asserts "the badge contains a list of chips" would now fail. Implementation phase must grep `tests/` for `knowledge-page-refs` and `page-refs` to catch this before running pytest.
- *Card overflow*: if a future term card wraps in a parent that has `overflow: hidden`, the popover would be clipped. Today no such ancestor exists in the rendered DOM. Add a note in implementation that the wrapper must not be inside a `overflow:hidden` ancestor.

**Follow-ups (out of scope)**
- Touch / mobile tap-to-open support (would require adding JS-driven `aria-expanded` toggle).
- Internationalising the trigger text "页可用" and the popover labels (currently hard-coded Chinese, consistent with the rest of the page).

## 11. Implementation files

| File | Change |
|---|---|
| `app/static/pages/knowledge.js` | Rewrite `renderPageRefsBadge(item)` to emit the new HTML; add `KNOWLEDGE_PAGE_NOTE` map. |
| `app/static/styles.css` | Add `.knowledge-page-refs*` block in the existing knowledge section. |
| `tests/test_knowledge_catalog.py` | Add 3 new tests; update any "chip" assertion that breaks. |

No other files change. Backend, routes, schema, config, and other pages are untouched.