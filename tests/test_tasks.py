from __future__ import annotations

import pytest

from scripts import tasks


def test_supported_python_check_rejects_wrong_version(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "active_python_version", lambda: (3, 12))

    with pytest.raises(tasks.TaskError):
        tasks.ensure_supported_python("check")


def test_supported_python_check_allows_clean(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "active_python_version", lambda: (3, 14))

    tasks.ensure_supported_python("clean")


def test_supported_python_check_allows_314(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "active_python_version", lambda: (3, 14))

    tasks.ensure_supported_python("check")


def test_virtualenv_check_rejects_global_python(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "in_virtualenv", lambda: False)

    with pytest.raises(tasks.TaskError):
        tasks.ensure_virtualenv("test")


def test_build_check_steps_runs_lint_then_test_then_smoke() -> None:
    steps = tasks.build_check_steps()

    assert steps[0][-2:] == ["check", "."]
    assert steps[1][-1] == "-q"
    assert steps[2][2] == "compileall"
    assert steps[3][1] == "-c"
