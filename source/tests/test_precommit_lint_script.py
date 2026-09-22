"""Static + runtime guards for ``source/scripts/precommit_lint.py``.

Commit ``4ec20ed`` (D1, 2026-09-16) introduced a ``.pre-commit-config.yaml``
hook that referenced this script, but the file itself never landed. Every
contributor since has been forced to ``git commit --no-verify`` to bypass
the broken hook. These guards exist so we never silently regress that
gap again:

* the file exists at the path the hook hardcodes;
* it is importable and exposes the documented entrypoint;
* the CLI exit code is 0 against the current ``app/ tests/ scripts/`` tree;
* the print-guard correctly exempts shebang / ``__main__`` scripts while
  still flagging inline ``print()`` calls inside server modules.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "precommit_lint.py"


def test_script_exists_at_hooked_path() -> None:
    assert SCRIPT.is_file(), (
        "pre-commit hook 'maintained-python-check' references "
        f"{SCRIPT.relative_to(ROOT.parent)} — the file must exist for the "
        "hook to do anything other than block every commit."
    )


def test_script_has_main_entrypoint() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "if __name__ == \"__main__\":" in text
    assert "def main" in text
    assert "sys.exit(main" in text


def test_script_targets_documented_scope() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "SCOPE_DIRS = (\"app\", \"tests\", \"scripts\")" in text
    # The ruff invocation must mirror CI exactly.
    assert "ruff" in text
    assert "\"check\"" in text
    for sub in ("app", "tests", "scripts"):
        assert sub in text


def test_script_exits_zero_against_current_tree() -> None:
    if shutil.which("ruff") is None:
        # Fall back to ``python -m ruff`` so the test still runs in a venv
        # where the binary is not on PATH.
        try:
            __import__("ruff")
        except ImportError:
            import pytest

            pytest.skip("ruff not installed; skipping live lint smoke")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-print-guard"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "precommit_lint.py failed against the current source tree; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_print_guard_exempts_cli_scripts() -> None:
    from scripts.precommit_lint import _find_stray_prints

    offenders = _find_stray_prints(
        list((ROOT / "app").rglob("*.py"))
    )
    # healthcheck.py and friends are CLI scripts (shebang / __main__) and
    # must NOT show up as offenders even though they call print().
    assert all(
        "healthcheck" not in path
        and "audit_" not in path
        and "verify_" not in path
        for path in offenders
    ), f"CLI scripts leaked into print offenders: {offenders}"


def test_print_guard_flags_server_module_prints(tmp_path) -> None:
    """The guard must still catch inline print() in real server files. We
    build a synthetic module under a project-shaped root to assert the AST
    path without having to wait for someone to re-introduce a real print()
    in app/services."""
    import importlib

    pl = importlib.import_module("scripts.precommit_lint")
    original_root = pl.PROJECT_ROOT
    try:
        # Mirror the real layout: tmp_path/app/services/x.py
        (tmp_path / "app" / "services").mkdir(parents=True)
        fake_file = tmp_path / "app" / "services" / "x.py"
        fake_file.write_text(
            "def handler(request):\n    print('hello')\n",
            encoding="utf-8",
        )
        pl.PROJECT_ROOT = tmp_path  # so the relative_to() check passes
        offenders = pl._find_stray_prints([fake_file])
        assert any(str(o).endswith("x.py") for o in offenders), (
            "Synthetic server print() must be flagged"
        )
    finally:
        pl.PROJECT_ROOT = original_root