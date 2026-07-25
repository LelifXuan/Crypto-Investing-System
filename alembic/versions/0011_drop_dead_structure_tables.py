"""drop dead structure_snapshot tables

Revision ID: 0011_drop_dead_structure_tables
Revises: 0010_strategy_signal_tables
Create Date: 2026-07-25

The 7 structure_* SQL tables are never written by current code.

StructureSnapshotService persists to page_snapshot_cache (page_type='structure')
instead. The repository methods that wrote to the SQL tables
(replace_structure_snapshot_bundle, get_latest_structure_snapshot, etc.)
have zero callers in app/ or tests/. The corresponding ORM models and
helpers (writers.py, readers.py) are also dead.

This migration idempotently drops the 7 tables for installations where
they exist (existing dev databases that ran migration 0004 /
0005). New installations never create them in the first place.

No downgrade: the original tables contained no production data after
2026-05-04 (when 0007_page_snapshot_cache.py introduced the cache
backbone). The dead path wrote nothing observable. downgrade() is
intentionally a no-op.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_drop_dead_structure_tables"
down_revision = "0010_strategy_signal_tables"
branch_labels = None
depends_on = None


_STRUCTURE_TABLES = (
    "structure_alerts",
    "structure_events",
    "structure_geometry",
    "structure_active_item",
    "structure_system_scores",
    "structure_system_judgement",
    "structure_snapshot",
)


def upgrade() -> None:
    """Drop the 7 dead structure_* tables if they exist (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table in _STRUCTURE_TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    """No-op: original tables held no production data. Re-running this
    migration after alembic downgrade -1 cannot recreate the deleted
    ORM models because they no longer exist in app/db/models/market.py.

    To bring the dead path back, restore the model classes,
    repository methods, writers.py / readers.py, then issue the
    inverse DROP here (manual recovery).
    """
    # Intentionally empty.
    pass
