"""auth, idempotency, evented pnl extensions

Revision ID: 0002_auth_evented_pnl
Revises: 0001_initial_schema
Create Date: 2026-04-04 08:30:00
"""

from __future__ import annotations

from alembic import op

revision = "0002_auth_evented_pnl"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists users (
            user_id text primary key,
            tenant_id text not null references tenants(tenant_id),
            username text not null unique,
            email text unique,
            password_hash text not null,
            is_active boolean not null default true,
            created_at timestamptz not null default now()
        );
        create index if not exists idx_users_tenant on users(tenant_id);

        create table if not exists user_roles (
            user_id text not null references users(user_id) on delete cascade,
            role_name text not null,
            created_at timestamptz not null default now(),
            primary key (user_id, role_name)
        );

        create table if not exists event_outbox (
            outbox_id bigserial primary key,
            event_id text not null unique references event_store(event_id) on delete cascade,
            event_type text not null,
            status text not null default 'PENDING',
            attempts integer not null default 0,
            available_at timestamptz not null default now(),
            processed_at timestamptz,
            last_error text,
            created_at timestamptz not null default now()
        );
        create index if not exists idx_event_outbox_status_available
            on event_outbox (status, available_at, outbox_id);

        create table if not exists idempotency_keys (
            key_id bigserial primary key,
            idempotency_key text not null,
            request_path text not null,
            request_hash text not null,
            state text not null default 'PROCESSING',
            response_status integer,
            response_body text,
            content_type text,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            unique(idempotency_key, request_path)
        );

        alter table cash_movements add column if not exists strategy_id text;
        alter table funding_events add column if not exists strategy_id text;
        alter table funding_events add column if not exists metadata jsonb not null default '{}'::jsonb;
        alter table cash_movements add column if not exists metadata jsonb not null default '{}'::jsonb;
        alter table fills alter column strategy_id set default '';
        update fills set strategy_id = '' where strategy_id is null;
        alter table fills alter column strategy_id set not null;
        alter table pnl_snapshots add column if not exists cash_balance numeric(38, 18) not null default 0;

        alter table fx_rates drop constraint if exists uq_fx_rates_unique;
        alter table fx_rates add constraint uq_fx_rates_unique unique(base_currency, quote_currency, source, ts_event);
        create index if not exists idx_cash_movements_account_ts on cash_movements(account_id, ts_event desc);
        create index if not exists idx_funding_events_account_ts on funding_events(account_id, ts_event desc);
        create index if not exists idx_fx_rates_pair_ts on fx_rates(base_currency, quote_currency, ts_event desc);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop index if exists idx_fx_rates_pair_ts;
        drop index if exists idx_funding_events_account_ts;
        drop index if exists idx_cash_movements_account_ts;
        alter table pnl_snapshots drop column if exists cash_balance;
        drop table if exists idempotency_keys cascade;
        drop table if exists event_outbox cascade;
        drop table if exists user_roles cascade;
        drop table if exists users cascade;
        """
    )
