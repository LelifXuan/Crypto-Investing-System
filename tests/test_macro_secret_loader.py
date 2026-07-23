from __future__ import annotations

from app.core.config import settings
from app.services.macro.secret_loader import SecretLoader


def test_secret_loader_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "env-key")
    monkeypatch.setattr(settings, "fred_api_key", "settings-key")

    loader = SecretLoader()

    assert loader.get("FRED_API_KEY") == "env-key"
    assert loader.auth_state(["FRED_API_KEY"]) == "present"


def test_secret_loader_falls_back_to_settings(monkeypatch) -> None:
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    monkeypatch.setattr(settings, "bls_api_key", "settings-key")

    loader = SecretLoader()

    assert loader.get("BLS_API_KEY") == "settings-key"
    assert loader.auth_state(["BLS_API_KEY"]) == "present"


def test_secret_loader_reports_missing_without_leaking_values(monkeypatch) -> None:
    monkeypatch.delenv("BEA_API_KEY", raising=False)
    monkeypatch.setattr(settings, "bea_api_key", "")

    loader = SecretLoader()

    assert loader.get("BEA_API_KEY") in {None, ""}
    assert loader.auth_state(["BEA_API_KEY"]) == "missing"
