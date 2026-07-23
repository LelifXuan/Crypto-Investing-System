from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.schema_compat import ensure_schema_compatibility


@pytest.mark.asyncio
async def test_schema_compatibility_repairs_old_page_snapshot_cache(tmp_path) -> None:
    db_path = tmp_path / "old.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE page_snapshot_cache (
                        cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key VARCHAR NOT NULL,
                        page_type VARCHAR NOT NULL,
                        instrument_id VARCHAR,
                        timeframe VARCHAR,
                        payload_json JSON NOT NULL DEFAULT '{}',
                        status VARCHAR NOT NULL DEFAULT 'stale',
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
            await conn.execute(
                text(
                    """
                    INSERT INTO page_snapshot_cache
                        (cache_key, page_type, payload_json, status, meta_json)
                    VALUES
                        ('analysis:btc:1h', 'analysis', '{}', 'stale', '{}')
                    """
                )
            )

        await ensure_schema_compatibility(engine)
        await ensure_schema_compatibility(engine)

        async with engine.connect() as conn:
            rows = await conn.execute(text("PRAGMA table_info(page_snapshot_cache)"))
            columns = {row[1] for row in rows.fetchall()}
            assert {"cache_state", "data_ts", "source_version", "cost_ms"} <= columns

            row = (
                await conn.execute(
                    text(
                        "SELECT cache_state, source_version FROM page_snapshot_cache "
                        "WHERE cache_key='analysis:btc:1h'"
                    )
                )
            ).one()
            assert row.cache_state == "stale"
            assert row.source_version == "v1"

            computed_rows = await conn.execute(text("PRAGMA table_info(computed_dataset_cache)"))
            computed_columns = {row[1] for row in computed_rows.fetchall()}
            assert {"cache_key", "dataset_type", "payload_json", "cache_state"} <= computed_columns
    finally:
        await engine.dispose()
