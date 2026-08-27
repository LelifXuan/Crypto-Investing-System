from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.models.market import (
    ComputedDatasetCache,
    VolatilityFeatureObservation,
    VolatilityResearchSnapshot,
)

VOLATILITY_RESEARCH_TABLES = [
    VolatilityResearchSnapshot.__table__,
    VolatilityFeatureObservation.__table__,
]

PAGE_SNAPSHOT_COLUMNS = {
    "cache_state": "VARCHAR NOT NULL DEFAULT 'missing'",
    "data_ts": "DATETIME",
    "source_version": "VARCHAR NOT NULL DEFAULT 'v1'",
    "cost_ms": "INTEGER",
}


async def ensure_schema_compatibility(engine: AsyncEngine) -> None:
    url = str(engine.url)
    if url.startswith("sqlite"):
        await _ensure_sqlite_schema_compatibility(engine)
    else:
        await _ensure_postgres_schema_compatibility(engine)


async def _ensure_sqlite_schema_compatibility(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[ComputedDatasetCache.__table__, *VOLATILITY_RESEARCH_TABLES],
            )
        )
        rows = await conn.execute(text("PRAGMA table_info(page_snapshot_cache)"))
        columns = {row[1] for row in rows.fetchall()}
        for name, ddl in PAGE_SNAPSHOT_COLUMNS.items():
            if name not in columns:
                await conn.execute(text(f"ALTER TABLE page_snapshot_cache ADD COLUMN {name} {ddl}"))

        await conn.execute(
            text(
                """
                UPDATE page_snapshot_cache
                   SET cache_state = COALESCE(NULLIF(status, ''), 'missing')
                 WHERE cache_state IS NULL OR cache_state = '' OR cache_state = 'missing'
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE page_snapshot_cache
                   SET source_version = COALESCE(NULLIF(source_version, ''), 'v1')
                 WHERE source_version IS NULL OR source_version = ''
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_state_v2 "
                "ON page_snapshot_cache(cache_state)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_data_ts "
                "ON page_snapshot_cache(data_ts)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_source_version "
                "ON page_snapshot_cache(source_version)"
            )
        )
        # 2026-08-11: 市场事件冻结标记（仅当表存在时执行）
        rows = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='market_events'")
        )
        if rows.fetchone() is not None:
            rows = await conn.execute(text("PRAGMA table_info(market_events)"))
            columns = {row[1] for row in rows.fetchall()}
            if "is_frozen" not in columns:
                await conn.execute(
                    text(
                        "ALTER TABLE market_events "
                        "ADD COLUMN is_frozen BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_market_events_is_frozen "
                    "ON market_events(is_frozen)"
                )
            )


async def _ensure_postgres_schema_compatibility(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[ComputedDatasetCache.__table__, *VOLATILITY_RESEARCH_TABLES],
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE page_snapshot_cache
                ADD COLUMN IF NOT EXISTS cache_state VARCHAR NOT NULL DEFAULT 'missing',
                ADD COLUMN IF NOT EXISTS data_ts TIMESTAMP WITH TIME ZONE NULL,
                ADD COLUMN IF NOT EXISTS source_version VARCHAR NOT NULL DEFAULT 'v1',
                ADD COLUMN IF NOT EXISTS cost_ms INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE page_snapshot_cache
                   SET cache_state = COALESCE(NULLIF(status, ''), 'missing')
                 WHERE cache_state IS NULL OR cache_state = '' OR cache_state = 'missing'
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE page_snapshot_cache
                   SET source_version = COALESCE(NULLIF(source_version, ''), 'v1')
                 WHERE source_version IS NULL OR source_version = ''
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_state_v2 "
                "ON page_snapshot_cache(cache_state)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_data_ts "
                "ON page_snapshot_cache(data_ts)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_page_snapshot_cache_source_version "
                "ON page_snapshot_cache(source_version)"
            )
        )
        # 2026-08-11: 市场事件冻结标记
        await conn.execute(
            text(
                """
                ALTER TABLE market_events
                ADD COLUMN IF NOT EXISTS is_frozen BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_market_events_is_frozen "
                "ON market_events(is_frozen)"
            )
        )
