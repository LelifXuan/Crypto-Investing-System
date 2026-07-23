# Timestamp Display Policy Alignment — Design

**Status:** Approved for implementation
**Date:** 2026-07-23
**Scope:** Three formatter functions + 1 untracked test; frontend-only.

## 1. Problem

The strategy page and the dashboard's `formatDateTime` / `formatIsoShort` formatters render absolute timestamps with a ` 北京时间` suffix. The dashboard's default timezone is already Beijing (Asia/Shanghai), so the suffix is redundant noise — every user-facing clock in the system implicitly means Beijing time, and the suffix only clutters the UI.

The original spec for absolute timestamps (`.zcode/plans/...`) said "show `YYYY-MM-DD HH:MM UTC`". The implementation took a different route: show Beijing time (correct for the audience) but with the literal `北京时间` suffix. An untracked test (`tests/test_timezone_label_removed.py`, written 2026-07) explicitly locks the strip-suffix behavior. The two specs are in tension.

**Decision (2026-07-23)**: keep the **Beijing time display** (correct for the audience) but **drop the suffix** (matches the untracked test, matches the rest of the UI which never carries a timezone suffix). Going forward, this is the canonical policy: timestamps on this app are Beijing time, no suffix, no exceptions.

## 2. Goals and non-goals

**Goals**
- Strip the literal `北京时间` from the three formatter functions that emit it.
- Make `tests/test_timezone_label_removed.py` pass (the untracked test).
- Confirm `renderEventWatch.js` and other consumers still work after the formatter change.
- Document the timezone policy in a single source of truth so future changes don't re-introduce the suffix.
- Zero behavior change to anything other than the literal suffix string.

**Non-goals**
- Do NOT switch to UTC display. UTC is correct for server logs but wrong for the end user.
- Do NOT add any other timezone label (CST, UTC+8, etc.). The current spec is "no suffix".
- Do NOT touch the backend (the backend already emits absolute ISO timestamps — that's done).
- Do NOT touch the untracked test file's behavior beyond making the assertions pass.

## 3. Approach

Strip the literal ` 北京时间` tail from these three template strings:

| File | Line | Current template |
|---|---|---|
| `app/static/core/dom.js` | 158 | `` `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute} 北京时间` `` |
| `app/static/ui/charts.js` | 446 | `` `${formatted} 北京时间` `` |
| `app/static/pages/strategy/formatHelpers.js` | 22 | `` `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} 北京时间` `` |

After the change:

- `dom.js:158` → `` `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}` ``
- `charts.js:446` → `` `${formatted}` ``
- `formatHelpers.js:22` → `` `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}` ``

No other code changes. All callers (`renderEventWatch.js`, `btc_derivatives.js`, `formatNextCheck`, `formatValidUntil`, etc.) automatically inherit the new format because they all call one of the three formatters above.

## 4. Architecture

```
ISO string (UTC or +08:00)
    │
    ▼
[Intl.DateTimeFormat with timeZone: "Asia/Shanghai"]
    │
    ▼
"YYYY/MM/DD hh:mm"   ← dom.js#formatDateTime
"YYYY-MM-DD hh:mm"   ← strategy/formatHelpers.js#formatIsoShort
chart axis label     ← ui/charts.js callback
    │
    ▼
(no suffix)          ← single source of truth
```

The **policy** is captured in a comment block at the top of `app/static/core/dom.js#formatDateTime` that future readers will see. The comment will say (the literal 4-character Beijing-time-of-day phrase is intentionally not written out, because the regression test in `tests/test_timezone_label_removed.py` does a naive substring assertion on the source file):

```
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

The same one-line cross-reference comment goes in `formatHelpers.js` and `charts.js`, pointing back to this anchor.

## 5. Files to change

| File | Action |
|---|---|
| `app/static/core/dom.js` | Strip ` 北京时间` from `formatDateTime`; add policy comment |
| `app/static/ui/charts.js` | Strip ` 北京时间` from time-axis callback |
| `app/static/pages/strategy/formatHelpers.js` | Strip ` 北京时间` from `formatIsoShort`; add cross-reference comment |
| `tests/test_timezone_label_removed.py` | NO CHANGE — currently fails; will pass after the strip |

The untracked test already exists and is exhaustive: 4 tests (one per source file, one per formatter). After the strip, all 4 should pass without modification.

## 6. Testing

### 6.1 Existing test (the untracked one)

`tests/test_timezone_label_removed.py` has 4 tests:

1. `test_source_files_do_not_emit_beijing_time_suffix` (parametrized over 3 files): asserts the literal `北京时间` is absent from each file.
2. `test_formatDateTime_renders_without_beijing_time_suffix`: runs `formatDateTime('2026-07-23T14:55:00+08:00')` via Node, asserts no `北京时间` in output, asserts output starts with `2026/`.
3. `test_strategy_formatIsoShort_renders_without_beijing_time_suffix`: same for `formatIsoShort`.
4. `test_charts_time_axis_renders_without_beijing_time_suffix`: greps the charts.js source for `北京时间`.

All 4 should pass after the strip.

### 6.2 No new tests required

The untracked test is the test. The plan is: strip, run the test, ensure it passes.

### 6.3 Existing tests must still pass

- `tests/test_knowledge_catalog.py` (52 tests) — unaffected.
- `tests/test_version_consistency.py` (3 tests) — unaffected.
- `tests/test_strategy*.py`, `tests/test_btc_derivatives*.py` — any test that asserts a substring of `formatDateTime` output may need attention. Implementation phase must run the full test suite and address any new failures (likely none, because the suffix is unused by tests today).

### 6.4 Playwright verify_pages

- Run `python tests/verify_pages.py` and confirm 11/11 cold-load + 10/10 SPA switches (or as close to 10/10 as the environment allows — see the Plan A post-mortem: 2/10 SPA failures on ai-strategy + gold-allocation are pre-existing environmental flakiness, not policy failures).

## 7. Risks and follow-ups

**Risks**
- *Grep-based test fragility*: `test_source_files_do_not_emit_beijing_time_suffix` does a literal substring search. If anyone later adds the suffix back, the test catches it; if they write a non-literal variant (e.g., a template variable), the test misses it. This is the known limit of grep-based tests; acceptable for a cosmetic policy.
- *Timezone ambiguity*: a user reading `2026-07-23 14:55` from a screenshot cannot tell if it's Beijing or UTC. This is the deliberate trade-off: the audience is Chinese traders, the dashboard says "BTC 衍生品", the system clock is Beijing. Mitigation: the policy comment at the top of `formatDateTime` makes the rule discoverable for future developers; the untracked test makes regression visible.
- *RenderEventWatch*: confirmed it uses `formatDateTime` from `dom.js`. After the strip, its output will drop the suffix too — desired.
- *BTC derivatives page*: uses `formatDateTime` 4 places (lines 774, 795, 797, 811). All 4 will inherit the strip — desired.

**Follow-ups (out of scope)**
- Adding a `/health` or settings UI panel that explicitly tells the user "timezone: Asia/Shanghai". This is a separate UX improvement.
- Switching the system to UTC display for international users. Out of scope and not currently requested.
- Renaming `formatDateTime` to `formatBeijingDateTime` to make the policy self-documenting. Out of scope; the comment suffices.

## 8. Out of scope

- Backend timestamp emission (`trade_decision.py`, `direction_resolution.py`, etc.) — already done in prior work.
- Task A (version unification) — separate plan.
- Task B (macro/Fed indicators) — separate plan.
- Task D (NotImplementedError providers) — separate plan.