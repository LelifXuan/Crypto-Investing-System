-- Market event source registry and normalized event store
-- PostgreSQL 15+

create extension if not exists pgcrypto;

create table if not exists market_event_sources (
    source_id text primary key,
    provider_name text not null,
    official_priority text not null check (official_priority in ('official','semi_official','domestic_aggregator','media','onchain_vendor')),
    access_confidence text not null check (access_confidence in ('high','medium','low')),
    category text not null,
    access_mode text not null,
    auth_required boolean not null default false,
    poll_interval_sec integer not null,
    base_url text not null,
    entry_url text not null,
    enabled boolean not null default true,
    last_success_at timestamptz,
    last_error_at timestamptz,
    last_error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists market_event_fetch_runs (
    fetch_run_id uuid primary key default gen_random_uuid(),
    source_id text not null references market_event_sources(source_id),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null check (status in ('running','success','failed','partial')),
    http_status integer,
    bytes_fetched integer,
    items_seen integer,
    items_inserted integer,
    items_updated integer,
    error_message text,
    latency_ms integer
);

create table if not exists market_event_raw_items (
    raw_item_id uuid primary key default gen_random_uuid(),
    source_id text not null references market_event_sources(source_id),
    source_item_id text,
    original_url text,
    title text,
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    payload_hash text not null,
    raw_payload jsonb not null,
    unique(source_id, payload_hash)
);

create table if not exists market_events (
    event_id uuid primary key default gen_random_uuid(),
    source_id text not null references market_event_sources(source_id),
    source_item_id text,
    canonical_hash text not null,
    event_type text not null,
    event_subtype text,
    title text not null,
    summary text,
    scheduled_at timestamptz,
    published_at timestamptz,
    detected_at timestamptz not null default now(),
    effective_at timestamptz,
    ended_at timestamptz,
    timezone text not null default 'Asia/Shanghai',
    region text,
    country text,
    exchange text,
    market_scope text[] not null default '{}',
    asset_symbol text,
    base_asset text,
    quote_asset text,
    entity_name text,
    entity_type text,
    importance text not null check (importance in ('critical','high','medium','low')),
    severity smallint not null check (severity between 0 and 100),
    status text not null default 'active' check (status in ('scheduled','active','resolved','cancelled','expired')),
    is_confirmed boolean not null default false,
    original_url text,
    raw_item_ids uuid[] not null default '{}',
    tags text[] not null default '{}',
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(canonical_hash)
);

create index if not exists idx_market_events_event_type on market_events(event_type);
create index if not exists idx_market_events_scheduled_at on market_events(scheduled_at desc);
create index if not exists idx_market_events_published_at on market_events(published_at desc);
create index if not exists idx_market_events_asset_symbol on market_events(asset_symbol);
create index if not exists idx_market_events_exchange on market_events(exchange);
create index if not exists idx_market_events_importance on market_events(importance);
create index if not exists idx_market_events_raw_payload on market_events using gin(raw_payload);

create table if not exists market_event_alert_rules (
    rule_id uuid primary key default gen_random_uuid(),
    rule_name text not null unique,
    enabled boolean not null default true,
    source_id text references market_event_sources(source_id),
    event_type text,
    event_subtype text,
    asset_symbol text,
    min_importance text check (min_importance in ('critical','high','medium','low')),
    lead_time_sec integer default 0,
    condition_json jsonb not null default '{}'::jsonb,
    throttle_sec integer not null default 600,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists market_event_alerts (
    alert_id uuid primary key default gen_random_uuid(),
    rule_id uuid not null references market_event_alert_rules(rule_id),
    event_id uuid not null references market_events(event_id),
    triggered_at timestamptz not null default now(),
    status text not null default 'firing' check (status in ('firing','acked','resolved')),
    payload jsonb not null default '{}'::jsonb,
    unique(rule_id, event_id)
);
