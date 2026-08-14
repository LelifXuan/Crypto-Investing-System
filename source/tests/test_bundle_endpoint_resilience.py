from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.db import db_manager
from app.main import create_app


def _create_old_page_snapshot_schema(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE page_snapshot_cache (
                        cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key VARCHAR NOT NULL,
                        page_type VARCHAR NOT NULL,
                        instrument_id VARCHAR,
                        timeframe VARCHAR,
                        payload_json JSON NOT NULL DEFAULT '{}',
                        status VARCHAR NOT NULL DEFAULT 'missing',
                        snapshot_at DATETIME,
                        expires_at DATETIME,
                        source_updated_at DATETIME,
                        last_error VARCHAR,
                        meta_json JSON NOT NULL DEFAULT '{}',
                        updated_at DATETIME,
                        created_at DATETIME
                    )
                    """
                )
            )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_bundle_endpoints_do_not_500_on_old_snapshot_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bundle-old.db"
    _create_old_page_snapshot_schema(db_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "local_auto_bootstrap_enabled", False)
    monkeypatch.setattr(settings, "precompute_enabled", True)
    monkeypatch.setattr(settings, "worker_profile", "none")
    await db_manager.disconnect()

    try:
        with TestClient(create_app()) as client:
            endpoints = [
                (
                    "/api/v1/analysis/bundle",
                    {
                        "instrument_id": "btc-usdt-perp",
                        "timeframe": "1h",
                        "view_window": "default",
                    },
                ),
                (
                    "/api/v1/structure/tab/bundle",
                    {
                        "instrument_id": "btc-usdt-perp",
                        "timeframe": "1h",
                        "include_geometry": "true",
                        "include_diagnostics": "true",
                    },
                ),
                (
                    "/api/v1/monitoring/dashboard",
                    {"instrument_id": "btc-usdt-perp", "timeframe": "1h"},
                ),
                (
                    "/api/v1/alerts/bundle",
                    {"instrument_id": "btc-usdt-perp", "timeframe": "1h"},
                ),
            ]
            for path, params in endpoints:
                response = client.get(path, params=params)
                assert response.status_code != 500, (path, response.text)
                assert response.status_code in {200, 404}
                if response.status_code == 200:
                    payload = response.json()
                    assert payload.get("status") in {None, "ready", "stale", "missing", "error"}
    finally:
        await db_manager.disconnect()
