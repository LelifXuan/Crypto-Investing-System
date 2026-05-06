"""computed dataset cache and page snapshot metadata

Revision ID: 0008_computed_dataset_cache
Revises: 0007_page_snapshot_cache
Create Date: 2026-05-05 11:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0008_computed_dataset_cache"
down_revision = "0007_page_snapshot_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table page_snapshot_cache add column cache_state text default 'missing';
        alter table page_snapshot_cache add column data_ts timestamptz;
        alter table page_snapshot_cache add column source_version text default 'v1';
        alter table page_snapshot_cache add column cost_ms integer;
        update page_snapshot_cache
           set cache_state = coalesce(cache_state, status, 'missing'),
               source_version = coalesce(source_version, 'v1');
        create index if not exists idx_page_snapshot_cache_state_v2
            on page_snapshot_cache(cache_state);
        create index if not exists idx_page_snapshot_cache_data_ts
            on page_snapshot_cache(data_ts);
        create index if not exists idx_page_snapshot_cache_source_version
            on page_snapshot_cache(source_version);

        create table if not exists computed_dataset_cache (
            dataset_cache_id integer primary key autoincrement,
            cache_key text not null,
            dataset_type text not null,
            instrument_id text,
            timeframe text,
            source_data_ts timestamptz,
            source_hash text,
            payload_json json not null default '{}',
            cache_state text not null default 'missing',
            source_version text not null default 'v1',
            calculated_at timestamptz not null default current_timestamp,
            expires_at timestamptz,
            cost_ms integer,
            error_message text,
            meta_json json not null default '{}',
            updated_at timestamptz not null default current_timestamp,
            created_at timestamptz not null default current_timestamp,
            unique(cache_key)
        );
        create index if not exists idx_computed_dataset_cache_key
            on computed_dataset_cache(cache_key);
        create index if not exists idx_computed_dataset_cache_lookup
            on computed_dataset_cache(dataset_type, instrument_id, timeframe, source_data_ts);
        create index if not exists idx_computed_dataset_cache_expires
            on computed_dataset_cache(expires_at);
        create index if not exists idx_computed_dataset_cache_state
            on computed_dataset_cache(cache_state);
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists computed_dataset_cache;")
