from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_app_version_is_1_8_0() -> None:
    """Source of truth: app.__version__ must be 1.8.0."""
    assert __version__ == "1.8.0"


def test_pyproject_version_matches_app_version() -> None:
    """Packaging release authority (pyproject.toml) must equal app.__version__."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None, "pyproject.toml missing [project] version"
    assert match.group(1) == __version__, (
        f"pyproject.toml version={match.group(1)!r} "
        f"!= app.__version__={__version__!r}"
    )


def test_settings_app_version_defaults_to_app_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime surface (Settings.app_version, no env override) must equal
    app.__version__. This is the strongest guard against drift.

    Note: ``_env_file=None`` is passed to skip the developer-local ``.env``
    so the test isolates the field default from any leaked environment
    override (``monkeypatch.delenv`` cannot un-set values that pydantic-
    settings reads directly from the dotenv file).
    """
    monkeypatch.delenv("APP_VERSION", raising=False)
    from app.core.config import Settings
    settings = Settings(_env_file=None)
    assert settings.app_version == __version__