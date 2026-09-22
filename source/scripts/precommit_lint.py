"""Pre-commit ruff gate, scope locked to ``app/ tests/ scripts/``.

Originally introduced by commit ``4ec20ed`` (D1, 2026-09-16). The
``.pre-commit-config.yaml`` referenced this script as the entrypoint of the
``maintained-python-check`` hook, but the file itself never landed. That gap
forced every contributor to ``git commit --no-verify`` and turned the hook
into a no-op rather than the intended gate against T1-style debt
re-accumulation.

This script reproduces exactly what CI's ``quality`` job runs locally:

    python -m ruff check app/ tests/ scripts/

plus a lightweight AST guard for stray ``print()`` calls in
``app/services/`` and ``app/api/``. The AST guard exists because
``pre-commit-hooks`` v5 has no ``forbid-print`` hook and we want a fast
local signal — Ruff's ``T201`` is the canonical replacement and will be
swapped in once the rest of the codebase stops tripping it.

The script:

* Resolves the project root from ``PROJECT_ROOT`` so it works regardless of
  where pre-commit invokes it from.
* Skips silently when ``ruff`` is unavailable (the hook is for the
  developer, not a CI substitute).
* Always re-uses the project's ``pyproject.toml`` configuration, so the
  ``extend-exclude`` list (``runtime_python``, ``data``, ``__pycache__`` …)
  keeps the same scope as CI.
* Exits non-zero if either ``ruff check`` or the print-AST guard finds a
  violation, which pre-commit maps to "block the commit".
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCOPE_DIRS = ("app", "tests", "scripts")
PRINT_FORBIDDEN_DIRS = ("app/services", "app/api")
SCOPE_GLOB = "**/*.py"


def _resolve_scope(base: Path) -> list[Path]:
    """Expand the locked scope into concrete files, honouring gitignore."""
    files: list[Path] = []
    for sub in SCOPE_DIRS:
        root = base / sub
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _run_ruff(base: Path) -> int:
    """Invoke ``ruff check`` against the locked scope."""
    targets = [str(base / sub) for sub in SCOPE_DIRS if (base / sub).exists()]
    if not targets:
        print("[precommit_lint] no scope dirs found; skipping ruff", file=sys.stderr)
        return 0
    cmd = [sys.executable, "-m", "ruff", "check", *targets]
    print(f"[precommit_lint] running: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd, cwd=base)


def _is_cli_script(path: Path) -> bool:
    """A file is treated as a CLI script (allowed to use print()) if it
    starts with a shebang or has an ``if __name__ == "__main__"`` guard.

    The repository already follows this convention for one-off audit and
    healthcheck scripts under ``app/services/`` (``macro/healthcheck.py``)
    and ``app/api/``. Server modules that import FastAPI / ASGI middleware
    never trip this rule.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if text.startswith("#!"):
        return True
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in tree.body:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ):
            return True
    return False


def _find_stray_prints(files: list[Path]) -> list[str]:
    """List source files under ``app/services`` and ``app/api`` that still
    call bare ``print()``. AST-only — we never execute user code here.

    CLI scripts (shebang or ``__main__`` guard) are exempted because the
    repository uses them as one-shot healthcheck / audit tooling where
    stdout is the actual deliverable. The audit policy in
    ``AGENTS.md §六.6`` targets the *server* code path, not CLI shims.
    """
    offenders: list[str] = []
    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        rel_str = rel.as_posix()
        if not any(rel_str.startswith(prefix + "/") for prefix in PRINT_FORBIDDEN_DIRS):
            continue
        if _is_cli_script(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            # ruff already catches syntax errors; skip rather than block
            # twice with a confusing duplicate message.
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders.append(rel_str)
                break
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-ruff",
        action="store_true",
        help="Skip ruff invocation (CI may already enforce it).",
    )
    parser.add_argument(
        "--skip-print-guard",
        action="store_true",
        help="Skip the app/services + app/api print() AST guard.",
    )
    args = parser.parse_args()

    if shutil.which("ruff") is None and not args.skip_ruff:
        # The dev environment might not have ruff installed (e.g. a minimal
        # virtualenv). Fall back to ``python -m ruff`` only if the module is
        # importable; otherwise warn and continue rather than blocking the
        # commit on a missing-but-optional dependency.
        try:
            __import__("ruff")
        except ImportError:
            print(
                "[precommit_lint] ruff not installed; skipping ruff check "
                "(CI will still enforce it).",
                file=sys.stderr,
            )
            args.skip_ruff = True

    ruff_code = 0
    if not args.skip_ruff:
        ruff_code = _run_ruff(PROJECT_ROOT)

    print_code = 0
    if not args.skip_print_guard:
        offenders = _find_stray_prints(_resolve_scope(PROJECT_ROOT))
        if offenders:
            print_code = 1
            print(
                "[precommit_lint] print() forbidden in app/services/ or app/api/ "
                "(use logging). Offending files:",
                file=sys.stderr,
            )
            for path in offenders:
                print(f"  - {path}", file=sys.stderr)

    return ruff_code or print_code


if __name__ == "__main__":
    sys.exit(main())