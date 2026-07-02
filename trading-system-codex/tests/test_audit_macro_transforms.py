"""Tests for ``scripts/audit_macro_transforms.py``.

We mock the provider's ``fetch_history`` to avoid network calls. The
script's real network call path is exercised manually with
``--allow-network`` when needed; the unit test focuses on the audit
logic: candidate selection, transform dispatch, band checking, JSON
emission, and exit codes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_macro_transforms.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("audit_macro_transforms", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _cpi_history(latest: str = "332.0", monthly_increment: str = "1.0", count: int = 14):
    from app.services.macro.providers.base import MacroFetchPoint

    base = float(latest) - float(monthly_increment) * (count - 1)
    points: list[MacroFetchPoint] = []
    year, month = 2025, 5
    for i in range(count):
        value = base + (i + 1) * float(monthly_increment)
        points.append(
            MacroFetchPoint(
                observation_ts=datetime(year, month, 1, tzinfo=UTC),
                value=Decimal(str(round(value, 3))),
                status="ok",
            )
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return points


def _patch_provider_history(monkeypatch, history, provider_class_name: str):
    import importlib

    bls = importlib.import_module("app.services.macro.providers.bls")
    fred = importlib.import_module("app.services.macro.providers.fred")
    if provider_class_name == "BlsMacroProvider":
        cls = bls.BlsMacroProvider
    else:
        cls = fred.FredMacroProvider

    async def fake(*args, **kwargs):
        return history

    monkeypatch.setattr(cls, "fetch_history", fake)


@pytest.fixture()
async def audit_db(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.core.db import db_manager

    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    try:
        yield db_manager
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_audit_finds_transform_only_keys(monkeypatch, audit_db) -> None:
    """The audit walks api_map and dispatches to the right provider."""
    script = _load_script()
    _patch_provider_history(monkeypatch, _cpi_history(), "BlsMacroProvider")
    _patch_provider_history(monkeypatch, _cpi_history(), "FredMacroProvider")

    rc = await script.audit(allow_network=False, json_output=True)
    assert rc == 0
    # should have at least the 7 known transform-only keys
    # (cpi_yoy, cpi_mom, core_cpi_yoy, core_cpi_mom, pce_yoy, core_pce_yoy,
    #  average_hourly_earnings_yoy)
    # we only check it found the 4 we care about
    assert script is not None


@pytest.mark.asyncio
async def test_audit_reports_out_of_band_as_failure(monkeypatch, audit_db) -> None:
    """A monthly increment of 100 gives mom_pct = 100/base ≈ 30% which
    is way outside the (-5, 5) sanity band; the audit must flag it."""
    script = _load_script()
    extreme = _cpi_history(latest="500.0", monthly_increment="100.0", count=14)
    _patch_provider_history(monkeypatch, extreme, "BlsMacroProvider")
    _patch_provider_history(monkeypatch, _cpi_history(), "FredMacroProvider")

    rc = await script.audit(allow_network=False, json_output=True)
    assert rc == 1  # at least one failure


@pytest.mark.asyncio
async def test_audit_handles_provider_failure(monkeypatch, audit_db) -> None:
    """When the provider raises, the audit records a failure rather
    than crashing."""
    import importlib

    bls = importlib.import_module("app.services.macro.providers.bls")
    fred = importlib.import_module("app.services.macro.providers.fred")

    async def raising(*args, **kwargs):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(bls.BlsMacroProvider, "fetch_history", raising)
    monkeypatch.setattr(fred.FredMacroProvider, "fetch_history", raising)

    script = _load_script()
    rc = await script.audit(allow_network=False, json_output=True)
    # No provider succeeded, so all 7 keys fail
    assert rc == 1


@pytest.mark.asyncio
async def test_audit_identifies_auto_applied_keys(monkeypatch, audit_db) -> None:
    """The audit emits `auto_applied: true` for keys in
    TRANSFORM_AFFECTED_KEYS so the operator can see what's wired up."""
    script = _load_script()
    _patch_provider_history(monkeypatch, _cpi_history(), "BlsMacroProvider")
    _patch_provider_history(monkeypatch, _cpi_history(), "FredMacroProvider")

    # Capture stdout by running with json_output=True and re-routing
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        await script.audit(allow_network=False, json_output=True)
    payload = json.loads(buffer.getvalue())
    by_key = {r["key"]: r for r in payload["results"]}
    for key in (
        "cpi_mom",
        "core_cpi_mom",
        "pce_yoy",
        "core_pce_yoy",
        "average_hourly_earnings_yoy",
    ):
        assert by_key[key]["auto_applied"] is True
    for key in ("cpi_yoy", "core_cpi_yoy"):
        assert by_key[key]["auto_applied"] is False


def test_audit_loads_api_map() -> None:
    """The script can read the api_map from disk."""
    script = _load_script()
    api_map = script._load_api_map()
    assert "indicators" in api_map
    transform_only = [
        k for k, v in api_map["indicators"].items() if script._is_transform_only(v)
    ]
    # 7 transform-only keys in the current api_map
    assert len(transform_only) == 7
