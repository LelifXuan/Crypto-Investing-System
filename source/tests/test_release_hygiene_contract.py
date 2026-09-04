"""Exercise previously unvisited test entrypoints and acceptance failure paths."""

import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import conftest
import pytest

ENTRYPOINTS = (
    "test_chart_theme_token_readback.py",
    "test_component_chip_button_smoke.py",
    "test_dropdown_a11y.py",
    "test_sticky_thead_present.py",
    "test_strategy_market_operation_card.py",
    "test_undeclared_token_visual_regression.py",
)


@pytest.mark.parametrize("filename", ENTRYPOINTS)
@pytest.mark.parametrize("exit_code", [0, 1])
def test_static_script_entrypoint_propagates_pytest_exit(monkeypatch, filename, exit_code):
    path = Path(__file__).with_name(filename)
    runner = Mock(return_value=exit_code)
    monkeypatch.setattr(pytest, "main", runner)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(path), run_name="__main__")
    assert stopped.value.code == exit_code
    runner.assert_called_once_with([str(path), "-v"])


def test_acceptance_missing_backend_fails_without_exposing_url(monkeypatch):
    connection = Mock(side_effect=ConnectionRefusedError("private diagnostic"))
    monkeypatch.setattr(conftest.socket, "create_connection", connection)
    with pytest.raises(pytest.UsageError, match="Acceptance backend unavailable") as error:
        conftest.require_acceptance_backend("http://127.0.0.1:8123/?key=not-for-output")
    assert "not-for-output" not in str(error.value)
    assert "private diagnostic" not in str(error.value)


def test_acceptance_uses_configured_backend(monkeypatch):
    connection = Mock(return_value=nullcontext())
    monkeypatch.setattr(conftest.socket, "create_connection", connection)
    conftest.require_acceptance_backend("http://localhost:8123")
    connection.assert_called_once_with(("localhost", 8123), timeout=2)


@pytest.mark.parametrize("acceptance", [False, True])
@pytest.mark.parametrize("reason", ["backend not running on :8002", "TA-Lib unavailable"])
def test_acceptance_rejects_only_missing_backend_skips(acceptance, reason):
    report = SimpleNamespace(skipped=True, outcome="skipped", longrepr=reason)
    item = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: acceptance))
    hook = conftest.pytest_runtest_makereport(item, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))
    assert report.outcome == ("failed" if acceptance and "backend" in reason else "skipped")
