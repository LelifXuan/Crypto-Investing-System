# Timestamp Display Policy Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop the literal `北京时间` suffix from the three user-facing timestamp formatters, and document the timezone policy in code so it doesn't drift back.

**Architecture:** Pure substring edits in 3 source files + 2 comment blocks. The untracked test `tests/test_timezone_label_removed.py` is the regression guard; it already exists and currently fails. No new tests; no backend changes.

**Tech Stack:** Plain JavaScript (formatters), pytest (regression), Node.js (subprocess in test).

---

## File map

| File | Action |
|---|---|
| `app/static/core/dom.js` | Strip ` 北京时间` from `formatDateTime`; add policy comment block above it |
| `app/static/ui/charts.js` | Strip ` 北京时间` from time-axis callback |
| `app/static/pages/strategy/formatHelpers.js` | Strip ` 北京时间` from `formatIsoShort`; add cross-reference comment |
| `tests/test_timezone_label_removed.py` | NO CHANGE (already exists as untracked; tests will start passing) |

---

## Task 1: Strip suffix from `dom.js#formatDateTime` + add policy comment

**Files:**
- Modify: `app/static/core/dom.js` (around line 158)

- [ ] **Step 1: Read the current `formatDateTime` implementation**

Run:
```bash
sed -n '140,170p' app/static/core/dom.js
```

Expected: a function `formatDateTime(input)` that builds a `parts` object via `Intl.DateTimeFormat(...)` and returns a template string containing `北京时间` on or near line 158.

- [ ] **Step 2: Edit the template string to drop the suffix**

Find the line that currently reads:

```js
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute} 北京时间`;
```

Replace it with:

```js
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
```

- [ ] **Step 3: Add the policy comment block immediately above the `formatDateTime` declaration**

Find the line `export function formatDateTime` (or `function formatDateTime`, depending on how the function is currently declared in this file). Insert the following comment block immediately above it (preserve any existing comment that may already be there; if there is one, REPLACE it with this canonical version):

```js
// User-facing time policy (2026-07-23):
// All user-facing timestamps on this app are Beijing time (Asia/Shanghai).
// Do NOT add a literal Beijing-time-of-day suffix (e.g. the four-Chinese-
// character phrase) or "CST" / "UTC+8" — the dashboard's default zone is
// already Beijing, so any suffix is noise. Server logs and OpenAPI
// responses stay UTC; this rule applies only to human-visible strings.
// See tests/test_timezone_label_removed.py for the regression guard.
// (The naive substring test forbids the literal phrase in source files,
// so this comment deliberately describes the rule without naming it.)
```

**Important**: this canonical text deliberately avoids the literal 4-character phrase, because the regression test in `tests/test_timezone_label_removed.py` does a naive substring assertion (`assert "北京时间" not in content`) on the source file. Writing the literal phrase in this comment would make the test fail.

- [ ] **Step 4: Validate JS syntax**

Run:
```bash
node --check app/static/core/dom.js
```

Expected: exit 0, no output.

- [ ] **Step 5: Verify the untracked test now partially passes (1 of 4 sub-cases)**

Run:
```bash
python -m pytest tests/test_timezone_label_removed.py -k "dom.js" -v
```

Expected: 1 passed (the parametrized source-file grep test for `dom.js`), 1 failed (the runtime formatter test, which we have not yet fixed in `formatHelpers.js` or `charts.js`).

- [ ] **Step 6: Do NOT commit yet — Task 1 is part of a single commit at the end of Task 3**

Note: leave the working tree dirty until all 3 files are stripped. The single commit message will describe the policy alignment across all three.

---

## Task 2: Strip suffix from `formatHelpers.js#formatIsoShort` + cross-reference

**Files:**
- Modify: `app/static/pages/strategy/formatHelpers.js` (around line 22)

- [ ] **Step 1: Read the current `formatIsoShort` implementation**

Run:
```bash
sed -n '1,30p' app/static/pages/strategy/formatHelpers.js
```

Expected: a function `formatIsoShort(iso)` that builds `parts` and returns a template string containing `北京时间` on or near line 22.

- [ ] **Step 2: Edit the template string**

Find the line that currently reads:

```js
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} 北京时间`;
```

Replace it with:

```js
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
```

- [ ] **Step 3: Add a one-line cross-reference comment above the function declaration**

The function declaration is `export function formatIsoShort(iso) {`. Insert this comment immediately above it (replace any existing comment with the canonical version):

```js
// User-facing timestamps on this app are Beijing time without suffix.
// See the policy comment in app/static/core/dom.js#formatDateTime.
```

- [ ] **Step 4: Validate JS syntax**

Run:
```bash
node --check app/static/pages/strategy/formatHelpers.js
```

Expected: exit 0, no output.

---

## Task 3: Strip suffix from `charts.js` time-axis callback

**Files:**
- Modify: `app/static/ui/charts.js` (around line 446)

- [ ] **Step 1: Read the chart-axis callback**

Run:
```bash
sed -n '435,455p' app/static/ui/charts.js
```

Expected: a `return` statement inside a Chart.js `ticks.callback` that includes ` 北京时间` on or near line 446.

- [ ] **Step 2: Edit the return statement**

Find the line that currently reads:

```js
            return `${formatted} 北京时间`;
```

(Indentation may vary; what matters is the suffix ` 北京时间` and the leading backtick.) Replace it with:

```js
            return formatted;
```

If the line is currently `${formatted} 北京时间` and the surrounding code is a `return` followed by other code, the new line is just `return formatted;` without template literals.

- [ ] **Step 3: Add a one-line cross-reference comment above the function/callback that holds the return statement**

Locate the enclosing function or the line that sets up `callback: (value) => { ... }` for the time axis. Add this comment immediately above it (or above the enclosing config object):

```js
// User-facing timestamps on this app are Beijing time without suffix.
// See the policy comment in app/static/core/dom.js#formatDateTime.
```

If a comment is already present, REPLACE it with this version.

- [ ] **Step 4: Validate JS syntax**

Run:
```bash
node --check app/static/ui/charts.js
```

Expected: exit 0, no output.

---

## Task 4: Run the untracked test and confirm all 4 sub-cases pass

- [ ] **Step 1: Run the full untracked test file**

Run:
```bash
python -m pytest tests/test_timezone_label_removed.py -v
```

Expected: ALL 4 tests pass.

The 4 tests are:
1. `test_source_files_do_not_emit_beijing_time_suffix[dom.js]`
2. `test_source_files_do_not_emit_beijing_time_suffix[formatHelpers.js]`
3. `test_source_files_do_not_emit_beijing_time_suffix[charts.js]`
4. `test_formatDateTime_renders_without_beijing_time_suffix` (runtime check)
5. `test_strategy_formatIsoShort_renders_without_beijing_time_suffix` (runtime check)
6. `test_charts_time_axis_renders_without_beijing_time_suffix` (source check)

Note: that's actually 6 test runs (3 parametrized + 3 standalone). All should pass.

If any test fails:
- For the source-file grep tests: re-check that you removed the literal `北京时间` from that file. Use `grep -n "北京时间" app/static/<file>` to confirm.
- For the runtime test: re-check the template string was changed to drop the suffix; ensure the new template literal is syntactically valid (e.g., not `return ` ` or `return ${formatted} `).

---

## Task 5: Confirm no regressions in the rest of the test suite

- [ ] **Step 1: Run all knowledge + version + timezone tests**

```bash
python -m pytest tests/test_knowledge_catalog.py tests/test_version_consistency.py tests/test_timezone_label_removed.py -q
```

Expected: 58 passed, 0 failed (52 knowledge + 3 version + 6 timezone minus the 3 parametrized counted as 3 separate).

- [ ] **Step 2: Run the full pytest suite and look for any NEW failures**

```bash
python -m pytest tests/ -q --ignore=tests/test_chip_structure.py --ignore=tests/test_page_loading_performance_contract.py --ignore=tests/test_btc_derivatives_api.py --ignore=tests/test_classic_pattern_detection.py --ignore=tests/test_macro_api_sources.py --ignore=tests/test_user_facing_text_audit.py 2>&1 | tail -10
```

The 6 ignored tests are **pre-existing failures** (verified in Plan A post-mortem). Expected: 0 new failures. If a new failure appears whose trace mentions `北京时间` or `formatDateTime`, debug and fix; otherwise the failure is unrelated to this change.

---

## Task 6: Playwright smoke test

- [ ] **Step 1: Confirm backend is up**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/health
```

Expected: `200`. If 000, start it: `uvicorn app.main:app --port 8002 &`.

- [ ] **Step 2: Run verify_pages**

```bash
python tests/verify_pages.py
```

Expected: 11/11 cold-load pages OK. SPA switches: 8-10/10 OK (the 2 ai-strategy + gold-allocation timeouts are pre-existing environmental flakiness, verified in Plan A post-mortem; not a regression from this change).

The screenshots for `ai-strategy.png` and any other page that uses `formatDateTime` will be regenerated; the visible diff should be the absence of the `北京时间` suffix on the relevant text labels.

- [ ] **Step 3: Spot-check one strategy-page screenshot**

Open `tests/screenshots/ai-strategy.png` (or whichever page renders the strategy decision panel) and confirm that timestamps in the "下一检查" / "有效期至" labels no longer have the ` 北京时间` suffix. The text should look like `下一检查：2026-07-23 14:55` (or similar) without trailing `北京时间`.

---

## Task 7: Single commit

- [ ] **Step 1: Stage the 3 source files**

```bash
git add app/static/core/dom.js app/static/ui/charts.js app/static/pages/strategy/formatHelpers.js
```

If `tests/test_timezone_label_removed.py` is untracked, decide whether to add it now. The user policy in this plan is to leave it tracked (it formalises a regression guard). If the user prefers to track it later, skip the test from the add.

For this plan, include the test in the commit because it documents the regression:

```bash
git add tests/test_timezone_label_removed.py
git status --short
```

Verify the staged set is exactly the 4 files above (3 source + 1 test). If the working tree has other dirty files (e.g., the strategy page module that was dirty before this work), DO NOT stage them.

- [ ] **Step 2: Commit**

```bash
git commit -m "[frontend] drop 北京时间 suffix from user-facing timestamps"
```

Expected: commit succeeds. If a pre-commit hook (if any) runs the test suite, it should now pass.

---

## Self-review

**1. Spec coverage:**
- §3 strip-suffix approach — Tasks 1, 2, 3 cover all 3 files. ✓
- §4 architecture / §5 file list — Tasks 1, 2, 3 match. ✓
- §6 testing — Task 4 runs the untracked test; Task 5 runs the rest of the suite. ✓
- §7 policy comment — Task 1 Step 3, Task 2 Step 3, Task 3 Step 3 add the comments. ✓

**2. Placeholder scan:** No TBD / TODO / "implement later" / "similar to Task N". All template strings are exact.

**3. Type / name consistency:**
- `formatDateTime` is the same function name across Tasks 1, 4, 5. ✓
- `formatIsoShort` is the same function name across Tasks 2, 4, 5. ✓
- The policy comment block is identical in Tasks 1, 2, 3 (with appropriate cross-reference in 2 and 3). ✓
- The untracked test name `test_timezone_label_removed.py` and the 6 test ids are stable across Tasks 4, 5, 7. ✓

**Execution handoff:** Plan saved to `docs/superpowers/plans/2026-07-23-timestamp-policy-alignment.md`. The work is small and well-specified; proceed with subagent-driven implementation.