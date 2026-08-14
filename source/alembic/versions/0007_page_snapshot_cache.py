"""page snapshot cache

Revision ID: 0007_page_snapshot_cache
Revises: 0006_signal_outcome
Create Date: 2026-05-04 10:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0007_page_snapshot_cache"
down_revision = "0006_signal_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists page_snapshot_cache (
            cache_id integer primary key autoincrement,
            cache_key text not null,
            page_type text not null,
            instrument_id text,
            timeframe text,
            payload_json json not null default '{}',
            status text not null default 'missing',
            snapshot_at timestamptz,
            expires_at timestamptz,
            source_updated_at timestamptz,
            last_error text,
            meta_json json not null default '{}',
            updated_at timestamptz not null default current_timestamp,
            created_at timestamptz not null default current_timestamp,
            unique(cache_key)
        );
        create index if not exists idx_page_snapshot_cache_key
            on page_snapshot_cache(cache_key);
        create index if not exists idx_page_snapshot_cache_page
            on page_snapshot_cache(page_type, instrument_id, timeframe);
        create index if not exists idx_page_snapshot_cache_expires
            on page_snapshot_cache(expires_at);
        create index if not exists idx_page_snapshot_cache_status
            on page_snapshot_cache(status);
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists page_snapshot_cache;")
