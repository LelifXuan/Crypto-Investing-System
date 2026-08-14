"""signal outcome tracking

Revision ID: 0006_signal_outcome
Revises: 0005_structure_scoring_engine
Create Date: 2026-04-25 10:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0006_signal_outcome"
down_revision = "0005_structure_scoring_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists signal_outcome (
            id integer primary key autoincrement,
            signal_type text not null,
            signal_ref text not null,
            instrument_id text not null,
            timeframe text not null,
            signal_ts timestamptz not null,
            entry_ref_price numeric(38, 18) not null,
            bars_1 integer,
            bars_3 integer,
            bars_6 integer,
            bars_12 integer,
            bars_24 integer,
            return_1 numeric(18, 8),
            return_3 numeric(18, 8),
            return_6 numeric(18, 8),
            return_12 numeric(18, 8),
            return_24 numeric(18, 8),
            mfe numeric(18, 8),
            mae numeric(18, 8),
            stop_hit_first boolean,
            take_profit_hit_first boolean,
            payload_json json not null default '{}',
            created_at timestamptz not null default current_timestamp,
            unique(signal_type, signal_ref, timeframe, signal_ts)
        );
        create index if not exists idx_signal_outcome_lookup
            on signal_outcome(instrument_id, timeframe, signal_ts desc);
        create index if not exists idx_signal_outcome_signal_ref
            on signal_outcome(signal_type, signal_ref);
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists signal_outcome;")
