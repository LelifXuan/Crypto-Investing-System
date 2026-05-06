"""structure scoring engine persistence

Revision ID: 0005_structure_scoring_engine
Revises: 0004_structure_recognition
Create Date: 2026-04-14 22:10:00
"""

from __future__ import annotations

from alembic import op

revision = "0005_structure_scoring_engine"
down_revision = "0004_structure_recognition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table structure_snapshot add column regime text not null default 'transition';
        alter table structure_snapshot add column weight_template text not null default 'transition';
        alter table structure_snapshot add column weight_swing numeric(10, 4) not null default 0;
        alter table structure_snapshot add column weight_classic numeric(10, 4) not null default 0;
        alter table structure_snapshot add column weight_profile numeric(10, 4) not null default 0;
        alter table structure_snapshot add column swing_effective_score numeric(10, 4);
        alter table structure_snapshot add column classic_effective_score numeric(10, 4);
        alter table structure_snapshot add column profile_effective_score numeric(10, 4);
        alter table structure_snapshot add column overall_score numeric(10, 4) not null default 0;
        alter table structure_snapshot add column overall_confidence numeric(10, 4) not null default 0;
        alter table structure_snapshot add column conflict_state boolean not null default false;
        alter table structure_snapshot add column top_reasons_json json not null default '[]';
        alter table structure_snapshot add column contribution_json json not null default '{}';

        create table if not exists structure_system_scores (
            id integer primary key autoincrement,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            system text not null,
            as_of_ts timestamptz not null,
            direction text not null default 'uncertain',
            direction_score numeric(10, 4) not null default 0,
            confidence numeric(10, 4) not null default 0,
            quality numeric(10, 4) not null default 0,
            freshness numeric(10, 4) not null default 0,
            evidence_count integer not null default 0,
            effective_score numeric(10, 4) not null default 0,
            weight numeric(10, 4) not null default 0,
            weighted_contribution numeric(10, 4) not null default 0,
            top_reasons_json json not null default '[]',
            conflict_flags_json json not null default '[]',
            metadata_json json not null default '{}',
            generated_at timestamptz not null,
            unique(instrument_id, timeframe, snapshot_version, system)
        );
        create index if not exists idx_structure_system_scores_lookup
            on structure_system_scores(instrument_id, timeframe, snapshot_version, system);
        create index if not exists idx_structure_system_scores_asof
            on structure_system_scores(instrument_id, timeframe, as_of_ts desc);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists structure_system_scores;
        """
    )
