"""realtime market extensions and indicator refresh policies

Revision ID: 0003_realtime_market_and_indicator_policies
Revises: 0002_auth_evented_pnl
Create Date: 2026-04-05 00:30:00
"""

from __future__ import annotations

from alembic import op

revision = "0003_realtime_market_and_indicator_policies"
down_revision = "0002_auth_evented_pnl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists indicator_refresh_policies (
            policy_id bigserial primary key,
            instrument_id text not null references instruments(instrument_id),
            timeframe text not null,
            price_kind text not null default 'last',
            source_preference text not null default 'gateio',
            is_enabled boolean not null default true,
            persist_candles boolean not null default true,
            fetch_limit integer not null default 300,
            parameters_json jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            unique(instrument_id, timeframe, price_kind, source_preference)
        );
        create index if not exists idx_indicator_refresh_policies_inst_tf
            on indicator_refresh_policies(instrument_id, timeframe, is_enabled);
        create index if not exists idx_market_events_ts on market_events(ts_event desc);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop index if exists idx_indicator_refresh_policies_inst_tf;
        drop table if exists indicator_refresh_policies cascade;
        """
    )
