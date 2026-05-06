"""structure recognition snapshot storage

Revision ID: 0004_structure_recognition
Revises: 0003_indicator_monitoring
Create Date: 2026-04-14 19:20:00
"""

from __future__ import annotations

from alembic import op

revision = "0004_structure_recognition"
down_revision = "0003_indicator_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists structure_snapshot (
            id integer primary key autoincrement,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            detector_version text not null,
            is_latest boolean not null default true,
            overall_bias text not null,
            score numeric(10, 4) not null default 0,
            confidence numeric(10, 4) not null default 0,
            primary_drivers_json json not null default '[]',
            opposing_factors_json json not null default '[]',
            active_structure_ids_json json not null default '[]',
            diagnostics_json json not null default '{}',
            generated_at timestamptz not null,
            created_at timestamptz not null default now(),
            unique(instrument_id, timeframe, snapshot_version)
        );
        create index if not exists idx_structure_snapshot_lookup
            on structure_snapshot(instrument_id, timeframe, is_latest, generated_at desc);

        create table if not exists structure_system_judgement (
            id integer primary key autoincrement,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            system text not null,
            bias text not null,
            score numeric(10, 4) not null default 0,
            confidence numeric(10, 4) not null default 0,
            status text not null default 'confirmed',
            drivers_json json not null default '[]',
            opposing_factors_json json not null default '[]',
            active_structures_json json not null default '[]',
            generated_at timestamptz not null
        );
        create index if not exists idx_structure_system_judgement_lookup
            on structure_system_judgement(instrument_id, timeframe, snapshot_version, system);

        create table if not exists structure_active_item (
            id integer primary key autoincrement,
            structure_id text not null unique,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            system text not null,
            structure_type text not null,
            display_name text not null,
            lifecycle_status text not null,
            directional_bias text not null,
            confidence numeric(10, 4) not null default 0,
            event_ts timestamptz not null,
            confirmation_ts timestamptz,
            invalidation_ts timestamptz,
            summary text,
            reasoning_json json not null default '[]',
            key_levels_json json not null default '{}',
            payload_json json not null default '{}',
            is_active boolean not null default true
        );
        create index if not exists idx_structure_active_item_lookup
            on structure_active_item(instrument_id, timeframe, snapshot_version, system, lifecycle_status);

        create table if not exists structure_geometry (
            id integer primary key autoincrement,
            geometry_id text not null unique,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            system text not null,
            kind text not null,
            status text not null,
            visible boolean not null default true,
            points_json json not null default '[]',
            labels_json json,
            meta_json json,
            created_at timestamptz not null
        );
        create index if not exists idx_structure_geometry_lookup
            on structure_geometry(instrument_id, timeframe, snapshot_version, system);

        create table if not exists structure_event (
            id integer primary key autoincrement,
            event_id text not null unique,
            instrument_id text not null,
            timeframe text not null,
            system text not null,
            event_name text not null,
            structure_id text,
            bias text not null,
            status text not null,
            confidence numeric(10, 4) not null default 0,
            anchor_bar_ts timestamptz,
            confirmation_bar_ts timestamptz,
            event_ts timestamptz not null,
            detection_ts timestamptz not null,
            dedupe_key text not null unique,
            payload_json json not null default '{}'
        );
        create index if not exists idx_structure_event_lookup
            on structure_event(instrument_id, timeframe, event_ts desc);
        create index if not exists idx_structure_event_name_ts
            on structure_event(event_name, event_ts desc);

        create table if not exists structure_alert (
            id integer primary key autoincrement,
            alert_id text not null unique,
            instrument_id text not null,
            timeframe text not null,
            snapshot_version text not null,
            event_id text,
            rule_key text not null,
            alert_name text not null,
            severity text not null,
            status text not null default 'open',
            dedupe_key text not null unique,
            title text not null,
            message text not null,
            triggered_at timestamptz not null,
            resolved_at timestamptz,
            event_payload_json json not null default '{}'
        );
        create index if not exists idx_structure_alert_lookup
            on structure_alert(instrument_id, timeframe, triggered_at desc);
        create index if not exists idx_structure_alert_triggered
            on structure_alert(triggered_at desc);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists structure_alert;
        drop table if exists structure_event;
        drop table if exists structure_geometry;
        drop table if exists structure_active_item;
        drop table if exists structure_system_judgement;
        drop table if exists structure_snapshot;
        """
    )
