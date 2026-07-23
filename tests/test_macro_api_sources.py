from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.macro.healthcheck import _check_provider
from app.services.macro.secret_loader import SecretLoader


class FakeProvider:
    async def healthcheck(self):
        return "auth_missing", RuntimeError("https://example.test?api_key=secret-value")


def test_api_source_configs_are_present() -> None:
    # 2026-07-23: api_sources.v1.json was retired alongside the portable
    # build and replaced by macro_data_sources.v2.json (added the data
    # sources previously split across the api_sources and api_map files).
    data_sources = Path("app/monitoring/configs/macro_data_sources.v2.json")
    indicator_map = Path("app/monitoring/configs/macro_indicator_api_map.v1.json")

    assert data_sources.exists()
    assert indicator_map.exists()
    assert json.loads(data_sources.read_text(encoding="utf-8"))["version"] == "macro_data_sources_v2"
    assert (
        json.loads(indicator_map.read_text(encoding="utf-8"))["version"]
        == "macro_indicator_api_map_v1"
    )


@pytest.mark.asyncio
async def test_macro_healthcheck_does_not_leak_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "secret-value")
    result = await _check_provider(FakeProvider(), "fred", SecretLoader(), ["FRED_API_KEY"])
    rendered = json.dumps(result, ensure_ascii=False)

    assert result["auth_present"] is True
    assert result["error_type"] == "RuntimeError"
    assert "secret-value" not in rendered
    assert "api_key=" not in rendered
