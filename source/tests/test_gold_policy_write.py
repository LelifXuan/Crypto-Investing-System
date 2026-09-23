"""Tests for POST /api/v1/gold/policy (gold strategy write path).

Before this endpoint, ``gold_policy_versions`` had no write path outside
test fixtures: losing the row meant the workbench degraded to
``setup_required`` with no in-product recovery. These tests pin:

- validation rejects inverted ranges / oversized gold value (422, no row)
- happy path appends version 1, then version 2; history rows are kept
- amounts go through Decimal end-to-end (no float residue in the row)
- version sequences are scoped per tenant+user (repository level)
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _payload(**overrides):
    base = dict(
        base_currency="USD",
        portfolio_total=200_000,
        gold_current_value=10_000,
        available_cash=25_000,
        target_min=0.05,
        target_max=0.15,
        base_dca_amount=500,
        fixed_dip_add_amount=1000,
        cooldown_days=14,
        quote_max_age_seconds=300,
        confirmations_required=3,
        drawdown_threshold=0.08,
        pause_base_when_overweight=False,
    )
    base.update(overrides)
    return base


@pytest.fixture()
async def gold_client(tmp_path, monkeypatch):
    """Isolated file DB with the real schema, via the app's own manager.

    Reuses the ``audit_db`` pattern (settings.database_url + connect):
    the writer session commits on clean exit, so consecutive POSTs
    observe each other's rows; tmp_path keeps the developer DB untouched.
    """
    from app.core.config import settings
    from app.core.db import db_manager

    db_path = tmp_path / "gold-policy.db"
    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    monkeypatch.setattr(settings, "local_auto_bootstrap_enabled", False)
    monkeypatch.setattr(settings, "precompute_enabled", False)
    monkeypatch.setattr(settings, "worker_profile", "none")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        with TestClient(create_app(enable_lifespan=False)) as client:
            yield client
    finally:
        await db_manager.disconnect()


async def _versions() -> list[int]:
    from sqlalchemy import select

    from app.core.db import db_manager
    from app.db.models.market import GoldPolicyVersion

    async with db_manager.session() as session:
        result = await session.execute(
            select(GoldPolicyVersion).order_by(GoldPolicyVersion.version)
        )
        return [row.version for row in result.scalars()]


@pytest.mark.asyncio
async def test_save_policy_appends_version_1(gold_client):
    resp = gold_client.post("/api/v1/gold/policy", json=_payload())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["version"] == 1
    assert data["base_currency"] == "USD"
    assert float(data["base_dca_amount"]) == 500
    assert data["policy_id"].startswith("gold-policy-")


@pytest.mark.asyncio
async def test_save_policy_appends_version_2_and_keeps_history(gold_client):
    assert gold_client.post("/api/v1/gold/policy", json=_payload()).status_code == 200
    resp = gold_client.post("/api/v1/gold/policy", json=_payload(base_dca_amount=600))
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 2
    assert float(resp.json()["base_dca_amount"]) == 600
    assert await _versions() == [1, 2]


@pytest.mark.asyncio
async def test_save_policy_rejects_inverted_range(gold_client):
    resp = gold_client.post(
        "/api/v1/gold/policy", json=_payload(target_min=0.2, target_max=0.1)
    )
    assert resp.status_code == 422
    assert await _versions() == []


@pytest.mark.asyncio
async def test_save_policy_rejects_gold_above_total(gold_client):
    resp = gold_client.post(
        "/api/v1/gold/policy",
        json=_payload(portfolio_total=1000, gold_current_value=2000),
    )
    assert resp.status_code == 422
    assert await _versions() == []


@pytest.mark.asyncio
async def test_save_policy_round_trips_through_workbench(gold_client):
    """POST then GET /workbench: the page leaves setup_required without
    a restart or a fixture."""
    assert gold_client.post("/api/v1/gold/policy", json=_payload()).status_code == 200
    workbench = gold_client.get("/api/v1/gold/workbench").json()
    assert workbench["refresh_state"] == "ok"
    assert workbench["snapshot"]["status"] == "ok"
    assert workbench["base_dca"]["status"] != "NO_POLICY"


@pytest.mark.asyncio
async def test_save_policy_stores_decimal_amounts(gold_client):
    from sqlalchemy import select

    from app.core.db import db_manager
    from app.db.models.market import GoldPolicyVersion

    assert gold_client.post("/api/v1/gold/policy", json=_payload()).status_code == 200
    async with db_manager.session() as session:
        result = await session.execute(select(GoldPolicyVersion).limit(1))
        row = result.scalar_one()
        assert row.base_dca_amount == Decimal("500")
        assert row.target_min == Decimal("0.05")


def test_policy_write_request_validates_ranges_without_db():
    from pydantic import ValidationError

    from app.schemas.gold_policy import GoldPolicyWriteRequest

    with pytest.raises(ValidationError):
        GoldPolicyWriteRequest(
            portfolio_total=1000,
            gold_current_value=100,
            target_min=0.2,
            target_max=0.1,
            base_dca_amount=10,
            fixed_dip_add_amount=10,
        )
    with pytest.raises(ValidationError):
        GoldPolicyWriteRequest(
            portfolio_total=0,
            gold_current_value=0,
            target_min=0.05,
            target_max=0.15,
            base_dca_amount=10,
            fixed_dip_add_amount=10,
        )


def test_gold_policy_model_has_no_float_columns():
    """Amounts must survive as Numeric — a float column would silently
    reintroduce binary rounding the service layer just removed."""
    from sqlalchemy import Numeric

    from app.db.models.market import GoldPolicyVersion

    float_like = [
        column.name
        for column in GoldPolicyVersion.__table__.columns
        if str(column.type).upper().startswith(("FLOAT", "REAL", "DOUBLE"))
    ]
    assert float_like == []
    assert isinstance(
        GoldPolicyVersion.__table__.columns["portfolio_total"].type, Numeric
    )


@pytest.mark.asyncio
async def test_repository_versions_are_scoped_per_user(tmp_path, monkeypatch):
    """Two users never share a version sequence (repository level)."""
    from app.core.config import settings
    from app.core.db import db_manager
    from app.schemas.gold_policy import GoldPolicyWriteRequest
    from app.services.gold_workbench import GoldPolicyRepository

    db_path = tmp_path / "gold-policy-scope.db"
    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    monkeypatch.setattr(settings, "local_auto_bootstrap_enabled", False)
    monkeypatch.setattr(settings, "worker_profile", "none")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        req = GoldPolicyWriteRequest(
            portfolio_total=200000,
            gold_current_value=10000,
            target_min=0.05,
            target_max=0.15,
            base_dca_amount=500,
            fixed_dip_add_amount=1000,
        )
        async with db_manager.writer_session() as session:
            repo = GoldPolicyRepository(session)
            first = await repo.save_policy("t", "u1", req)
            second = await repo.save_policy("t", "u1", req)
            other = await repo.save_policy("t", "u2", req)
        assert (first.version, second.version, other.version) == (1, 2, 1)
        assert len({first.policy_id, second.policy_id, other.policy_id}) == 3
        async with db_manager.session() as session:
            repo = GoldPolicyRepository(session)
            latest = await repo.latest("t", "u1")
            assert latest is not None and latest.version == 2
    finally:
        await db_manager.disconnect()
