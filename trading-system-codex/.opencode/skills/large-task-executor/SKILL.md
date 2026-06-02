---
name: large-task-executor
description: Use when executing multi-phase tasks (3+ distinct items) or task lists with priority levels (P0/P1/P2). Applies to: macro data pipelines, API integration, provider contracts, config bulk updates, portable sync, and any batch file creation/modification. Enforces continuous execution without mid-task pauses, auto-retry on common failures, and structured progress tracking.
---

# Large Task Executor

## Core Principles

1. **Execute to Completion**: Once a task list is confirmed, execute ALL phases without stopping mid-way to ask "continue?" The user provided the full list — they want it all done.

2. **Auto-Retry on Failure**: Common transient errors must be retried automatically with appropriate strategies. Do not report failure and stop — recover and continue.

3. **Structured Progress**: Use `todowrite` for every task. Mark completion only after actual work is done AND verified.

## When to Use

Trigger this skill when the task description contains any of:
- Multiple numbered items (3+) in a single request
- Priority levels: P0, P1, P2
- Phase markers: Phase 1, Phase 2, Batch 1, Batch 2
- Reference files containing a `tasks` array or numbered checklist
- User says "execute all tasks" or "complete everything"

## Execution Rules

### Rule 1: Never ask "continue?" between sub-tasks

Wrong:
```
P0 tasks done. Continue with P1?
```

Correct:
```
P0 tasks done. Starting P1 now...
```

Only stop for:
- Genuine ambiguity (two valid approaches, unclear preference)
- Hard dependency (P2 behavior depends on P1 result in an unpredictable way)
- User explicitly requests a checkpoint

### Rule 2: Plan first, then batch-execute

Before making any file changes:
1. Read all reference files to understand scope
2. Create the full `todowrite` list
3. Identify independent operations that can run in parallel
4. Group edits to the same file into a single batch

### Rule 3: Parallelize aggressively

When tasks are independent (edit different files, run independent commands), execute them in parallel using multiple tool calls in one message.

### Rule 4: Progressive verification + complete logic chain

After each single file edit, verify at least **2 layers downstream** before marking the task complete:

```
例：修改后端 Python 返回值
  → 验证: Schema 字段名是否匹配前端 JS 读取的 key
  → 验证: 前端渲染函数是否真的消费了新字段
  → 完成后才标记 done
```

Verification checklist per edit:
- Python backend change → check import still works (`python -c "import <module>"`)
- Schema field added → check frontend JS reads the same key name (case-sensitive)
- Frontend JS change → check brace/backtick balance + function exists in file
- API response change → use `httpx` to verify the new field appears in HTTP response

After each logical batch:
- Run `python scripts/cross_check_and_retry.py` after data pipeline changes
- Run `python tools/audit_user_facing_text.py` after text changes

Final verification after ALL tasks:
- Cross-check
- Text audit
- Relevant tests

### Rule 5: Incremental todowrite

Update `todowrite` after EACH completed-and-verified task, not batched at the end. This ensures the progress bar reflects actual state.

```
BAD:   edit A, edit B, edit C, edit D → todowrite(all complete)
GOOD:  edit A → verify → todowrite(A complete) → edit B → verify → todowrite(B complete) → ...
```

### Rule 6: 3-Attempt Principle

When a tool call fails, try at least **3 alternative approaches** before reporting the failure:

| Failure | Attempt 1 | Attempt 2 | Attempt 3 |
|---|---|---|---|
| `edit` tool: "oldString not found" | Copy exact text from file via `read` | Use smaller unique surrounding context | Use Python script to delete/insert by line number |
| `bash` timeout | Double timeout + retry | Write to temp `.py` script file | Check for partial results, skip completed steps |
| ModuleNotFoundError | pip install | Check if installed elsewhere, add to sys.path | Downgrade to stub/mock |
| "无法打开浏览器" | Check `$env:LOCALAPPDATA\ms-playwright\` | Use headless Chromium via subprocess | Use `httpx` to simulate page load + check static JS |

Do not report "not possible" until 3 distinct approaches have been tried. Exhaust a strategy before ruling it out.

### Rule 7: Context Recycling

After completing a major Phase (all P0 tasks, or ~5+ edits), write a state summary to `reports/session_state.md`:

```markdown
## Phase X Complete - YYYY-MM-DD HH:MM

### Completed
- file1: change description
- file2: change description

### Current State
- Server: running on port X
- Tests: N/N passing
- Cross-check: N/N

### Remaining
- task A (priority)
- task B
```

Then keep only the current Phase's todos in `todowrite`. This frees context for deeper reasoning on remaining tasks.

## Auto-Retry Strategies

### Strategy A: PowerShell String Escaping Failure
**Symptoms**: `SyntaxError: unterminated string literal`, escape character issues

**Action**:
1. Write the Python code to a temporary `.py` file in `C:\Users\h2278\AppData\Local\Temp\opencode\`
2. Execute `python C:\Users\h2278\AppData\Local\Temp\opencode\<name>.py`
3. Clean up the temp file

### Strategy B: Command Timeout
**Symptoms**: Tool terminated after exceeding timeout

**Action**:
1. Retry with timeout doubled (max 600s)
2. Check if partial results exist (e.g., `dist/portable_bundle` was created despite timeout)
3. If partial results, skip the completed step and continue

### Strategy C: Subprocess Encoding Error
**Symptoms**: `UnicodeDecodeError: 'gbk' codec can't decode byte`

**Action**:
1. Add `encoding='utf-8', errors='replace'` to subprocess call
2. Retry once

### Strategy D: Python String Escaping in PowerShell
**Symptoms**: `SyntaxError` from inline Python with nested quotes

**Action**:
1. Immediately switch to writing a temp `.py` file instead
2. Execute the file, read results
3. Delete temp file

### Strategy E: File Access / Lock Error
**Symptoms**: `PermissionError`, `OSError`, file in use

**Action**:
1. Wait 2 seconds
2. Retry once

### Strategy F: API Connectivity Timeout
**Symptoms**: `ConnectTimeout`, `ReadTimeout` from httpx/requests

**Action**:
1. Retry once with 2x timeout
2. If still failing, mark source as `source_error` and continue with other sources
3. Report all failed sources at the end

## Timeout Budgeting

For portable builds and pip installs:
- Use 600s (10 min) timeout for full `sync_portable_local.ps1`
- Use 300s (5 min) timeout for `build_portable_bundle.py` alone
- If timeout occurs: check `dist/portable_bundle` exists → skip build, fix deps manually, sync with `-SkipBuild`

## Task State Machine

```
pending → in_progress → completed
                    ↘ failed
                       → retry (auto, max 2) → completed
                       → skip (recoverable, mark as cancelled) → continue
                       → report (unrecoverable, at END of all tasks)
```

- Only ONE task in_progress at a time
- Mark completed only after verification
- Report unrecoverable failures at the end, not mid-batch

## Output Format for Completion

After all tasks:
```
All X tasks completed. Results:

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | ... | completed | ... |
| 2 | ... | completed (retried 1x timeout) | ... |
| 3 | ... | skipped (known issue: ...) | ... |

Verification:
- Cross-check: X/Y
- Tests: X/Y
- Audit: X violations
```
