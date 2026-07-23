"""indicator monitoring framework

Revision ID: 0003_indicator_monitoring
Revises: 0002_auth_evented_pnl
Create Date: 2026-04-05 04:30:00
"""

from __future__ import annotations

from alembic import op

revision = "0003_indicator_monitoring"
down_revision = "0002_auth_evented_pnl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists indicator_definitions (
            indicator_key text primary key,
            display_name text not null,
            category text not null,
            family text not null,
            source_provider text not null,
            source_kind text not null,
            calc_engine text not null,
            calc_params_json json not null default '{}',
            supported_assets_json json not null default '[]',
            supported_timeframes_json json not null default '[]',
            output_fields_json json not null default '[]',
            signal_states_json json not null default '[]',
            default_thresholds_json json not null default '{}',
            use_cases_json json not null default '[]',
            is_enabled boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );
        create index if not exists idx_indicator_definitions_category on indicator_definitions(category);
        create index if not exists idx_indicator_definitions_family on indicator_definitions(family);

        create table if not exists indicator_monitoring_policies (
            policy_id text primary key,
            indicator_key text not null references indicator_definitions(indicator_key),
            scope_type text not null,
            instrument_id text,
            asset_code text,
            timeframe text,
            mode text not null,
            interval_seconds integer,
            cron_expr text,
            timezone text,
            event_key text,
            calendar_source text,
            release_key text,
            fallback_interval_seconds integer,
            priority integer not null default 5,
            is_enabled boolean not null default true,
            last_run_at timestamptz,
            next_run_at timestamptz,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            unique(indicator_key, scope_type, instrument_id, asset_code, timeframe)
        );
        create index if not exists idx_indicator_monitoring_policies_next_run
            on indicator_monitoring_policies(is_enabled, next_run_at);

        create table if not exists indicator_observations (
            observation_id text primary key,
            dedupe_key text not null unique,
            indicator_key text not null references indicator_definitions(indicator_key),
            category text not null,
            instrument_id text,
            asset_code text,
            country_code text,
            timeframe text,
            observation_ts timestamptz not null,
            effective_start_ts timestamptz,
            effective_end_ts timestamptz,
            value_num numeric(30, 10),
            value_text text,
            value_json json not null default '{}',
            baseline_num numeric(30, 10),
            delta_num numeric(30, 10),
            zscore_num numeric(20, 8),
            percentile_num numeric(10, 4),
            signal_state text,
            signal_score numeric(10, 4),
            source_provider text not null,
            source_ref text,
            source_granularity text,
            is_preliminary boolean not null default false,
            quality_score numeric(5, 2) not null default 100,
            run_id text,
            inserted_at timestamptz not null default now()
        );
        create index if not exists idx_indicator_observations_lookup
            on indicator_observations(indicator_key, instrument_id, asset_code, timeframe, observation_ts desc);
        create index if not exists idx_indicator_observations_category_ts
            on indicator_observations(category, observation_ts desc);

        create table if not exists indicator_alert_rules (
            rule_key text primary key,
            indicator_key text not null references indicator_definitions(indicator_key),
            enabled boolean not null default true,
            severity text not null,
            category text not null,
            scope_type text not null,
            condition_type text not null,
            comparator text,
            threshold_num numeric(30, 10),
            lower_threshold_num numeric(30, 10),
            upper_threshold_num numeric(30, 10),
            state_value text,
            percentile_ref_window_points integer,
            consecutive_points integer,
            dedupe_window_seconds integer not null default 300,
            cooldown_seconds integer not null default 300,
            action_channels_json json not null default '[]',
            message_template text not null,
            extra_config_json json not null default '{}',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );

        create table if not exists indicator_alert_events (
            alert_event_id text primary key,
            rule_key text not null references indicator_alert_rules(rule_key),
            indicator_key text not null,
            observation_id text,
            severity text not null,
            status text not null default 'open',
            instrument_id text,
            asset_code text,
            timeframe text,
            triggered_at timestamptz not null,
            resolved_at timestamptz,
            dedupe_key text not null unique,
            title text not null,
            message text not null,
            event_payload_json json not null default '{}',
            created_at timestamptz not null default now()
        );
        create index if not exists idx_indicator_alert_events_status on indicator_alert_events(status, triggered_at desc);

        create table if not exists macro_event_calendar (
            event_id text primary key,
            provider_key text not null,
            event_key text not null,
            country_code text not null default 'US',
            title text not null,
            scheduled_at timestamptz not null,
            actual_value_num numeric(30, 10),
            consensus_value_num numeric(30, 10),
            previous_value_num numeric(30, 10),
            surprise_num numeric(30, 10),
            importance text not null default 'high',
            status text not null default 'scheduled',
            source_ref text,
            payload_json json not null default '{}',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            unique(provider_key, event_key, scheduled_at)
        );
        create index if not exists idx_macro_event_calendar_sched on macro_event_calendar(scheduled_at desc);

        create table if not exists indicator_runs (
            run_id text primary key,
            indicator_key text not null,
            scope_type text not null,
            scope_ref text,
            status text not null,
            trigger_type text not null,
            trigger_ref text,
            started_at timestamptz not null,
            finished_at timestamptz,
            rows_written integer not null default 0,
            error_code text,
            error_message text,
            stats_json json not null default '{}'
        );
        create index if not exists idx_indicator_runs_key_started
            on indicator_runs(indicator_key, started_at desc);

        create table if not exists review_indicator_snapshots (
            snapshot_id text primary key,
            trade_review_id text not null,
            snapshot_phase text not null,
            observed_at timestamptz not null,
            instrument_id text,
            asset_code text,
            timeframe text,
            indicators_json json not null default '{}',
            created_at timestamptz not null default now()
        );
        create index if not exists idx_review_indicator_snapshots_trade
            on review_indicator_snapshots(trade_review_id, observed_at desc);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists review_indicator_snapshots;
        drop table if exists indicator_runs;
        drop table if exists macro_event_calendar;
        drop table if exists indicator_alert_events;
        drop table if exists indicator_alert_rules;
        drop table if exists indicator_observations;
        drop table if exists indicator_monitoring_policies;
        drop table if exists indicator_definitions;
        """
    )
