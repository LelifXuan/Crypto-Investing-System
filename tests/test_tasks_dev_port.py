from __future__ import annotations

import pytest

from scripts import tasks


def test_dev_port_falls_back_when_preferred_is_busy(monkeypatch: pytest.MonkeyPatch):
    def fake_can_bind(port: int) -> bool:
        return port != 8002

    monkeypatch.setattr(tasks, "_can_bind_localhost", fake_can_bind)

    assert tasks._select_dev_port(8002) == 8003


def test_app_port_env_must_be_valid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PORT", "not-a-port")

    with pytest.raises(tasks.TaskError, match="APP_PORT must be an integer"):
        tasks._port_from_env_or_default(8002)
