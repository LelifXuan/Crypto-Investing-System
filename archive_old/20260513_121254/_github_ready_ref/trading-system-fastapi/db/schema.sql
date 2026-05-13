
create extension if not exists "pgcrypto";

create table if not exists tenants (
    tenant_id           text primary key,
    name                text not null,
    created_at          timestamptz not null default now()
);

create table if not exists accounts (
    account_id          text primary key,
    tenant_id           text not null references tenants(tenant_id),
    venue               text not null,
    base_currency       text not null,
    status              text not null default 'ACTIVE',
    created_at          timestamptz not null default now()
);
create index if not exists idx_accounts_tenant on accounts(tenant_id);

create table if not exists strategies (
    strategy_id         text primary key,
    tenant_id           text not null references tenants(tenant_id),
    name                text not null,
    tags                jsonb not null default '[]'::jsonb,
    status              text not null default 'ACTIVE',
    created_at          timestamptz not null default now()
);
create index if not exists idx_strategies_tenant on strategies(tenant_id);

create table if not exists users (
    user_id             text primary key,
    tenant_id           text not null references tenants(tenant_id),
    username            text not null unique,
    email               text unique,
    password_hash       text not null,
    is_active           boolean not null default true,
    created_at          timestamptz not null default now()
);
create index if not exists idx_users_tenant on users(tenant_id);

create table if not exists user_roles (
    user_id             text not null references users(user_id) on delete cascade,
    role_name           text not null,
    created_at          timestamptz not null default now(),
    primary key (user_id, role_name)
);

create table if not exists instruments (
    instrument_id       text primary key,
    venue               text not null,
    symbol              text not null,
    asset_class         text not null,
    base_ccy            text not null,
    quote_ccy           text not null,
    settle_ccy          text not null,
    tick_size           numeric(38, 18) not null,
    lot_size            numeric(38, 18) not null,
    contract_multiplier numeric(38, 18) not null default 1,
    margin_model        text not null default 'NONE',
    metadata            jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now(),
    unique(venue, symbol)
);

create table if not exists event_store (
    event_id            text primary key,
    event_type          text not null,
    schema_version      integer not null,
    source              text not null,
    partition_key       text not null,
    idempotency_key     text,
    ts_event            timestamptz not null,
    ts_ingest           timestamptz not null,
    trace_id            text,
    span_id             text,
    payload             jsonb not null,
    created_at          timestamptz not null default now()
);
create unique index if not exists ux_event_store_idempotency
    on event_store (source, idempotency_key)
    where idempotency_key is not null;
create index if not exists idx_event_store_partition_ts
    on event_store (partition_key, ts_event, event_id);

create table if not exists event_outbox (
    outbox_id           bigserial primary key,
    event_id            text not null unique references event_store(event_id) on delete cascade,
    event_type          text not null,
    status              text not null default 'PENDING',
    attempts            integer not null default 0,
    available_at        timestamptz not null default now(),
    processed_at        timestamptz,
    last_error          text,
    created_at          timestamptz not null default now()
);
create index if not exists idx_event_outbox_status_available
    on event_outbox (status, available_at, outbox_id);

create table if not exists idempotency_keys (
    key_id              bigserial primary key,
    idempotency_key     text not null,
    request_path        text not null,
    request_hash        text not null,
    state               text not null default 'PROCESSING',
    response_status     integer,
    response_body       text,
    content_type        text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique(idempotency_key, request_path)
);

create table if not exists orders (
    order_id            text primary key,
    account_id          text not null references accounts(account_id),
    strategy_id         text references strategies(strategy_id),
    instrument_id       text not null references instruments(instrument_id),
    side                text not null,
    order_type          text not null,
    price               numeric(38, 18),
    qty                 numeric(38, 18) not null,
    status              text not null,
    ts_event            timestamptz not null,
    created_at          timestamptz not null default now()
);

create table if not exists fills (
    fill_pk             bigserial primary key,
    fill_id             text not null,
    source              text not null,
    order_id            text references orders(order_id),
    account_id          text not null references accounts(account_id),
    strategy_id         text not null default '',
    instrument_id       text not null references instruments(instrument_id),
    side                text not null,
    qty                 numeric(38, 18) not null,
    price               numeric(38, 18) not null,
    fee                 numeric(38, 18) not null default 0,
    fee_currency        text not null,
    liquidity           text not null default 'UNKNOWN',
    ts_event            timestamptz not null,
    ts_ingest           timestamptz not null,
    raw_payload         jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now(),
    unique(source, account_id, fill_id)
);
create index if not exists idx_fills_account_instrument_ts on fills(account_id, instrument_id, ts_event);

create table if not exists cash_movements (
    movement_id         text primary key,
    account_id          text not null references accounts(account_id),
    strategy_id         text,
    movement_type       text not null,
    amount              numeric(38, 18) not null,
    currency            text not null,
    ts_event            timestamptz not null,
    metadata            jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists idx_cash_movements_account_ts on cash_movements(account_id, ts_event desc);

create table if not exists funding_events (
    funding_id          text primary key,
    account_id          text not null references accounts(account_id),
    strategy_id         text,
    instrument_id       text not null references instruments(instrument_id),
    rate                numeric(38, 18) not null,
    payment             numeric(38, 18) not null,
    currency            text not null,
    ts_event            timestamptz not null,
    metadata            jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists idx_funding_events_account_ts on funding_events(account_id, ts_event desc);

create table if not exists fx_rates (
    fx_id               bigserial primary key,
    base_currency       text not null,
    quote_currency      text not null,
    rate                numeric(38, 18) not null,
    source              text not null,
    ts_event            timestamptz not null,
    created_at          timestamptz not null default now(),
    unique(base_currency, quote_currency, source, ts_event)
);
create index if not exists idx_fx_rates_pair_ts on fx_rates(base_currency, quote_currency, ts_event desc);

create table if not exists mark_prices (
    mark_id             bigserial primary key,
    instrument_id       text not null references instruments(instrument_id),
    mark_price          numeric(38, 18) not null,
    source              text not null,
    ts_event            timestamptz not null,
    created_at          timestamptz not null default now()
);
create index if not exists idx_mark_prices_inst_ts on mark_prices(instrument_id, ts_event desc);

create table if not exists position_views (
    account_id          text not null references accounts(account_id),
    strategy_id         text not null default '',
    instrument_id       text not null references instruments(instrument_id),
    cost_method         text not null,
    net_qty             numeric(38, 18) not null,
    avg_cost_price      numeric(38, 18) not null default 0,
    gross_notional      numeric(38, 18) not null default 0,
    realized_pnl_json   jsonb not null default '{}'::jsonb,
    unrealized_pnl_json jsonb not null default '{}'::jsonb,
    margin_used         numeric(38, 18) not null default 0,
    leverage            numeric(38, 18) not null default 0,
    updated_at          timestamptz not null default now(),
    primary key (account_id, strategy_id, instrument_id, cost_method)
);

create table if not exists position_snapshots (
    snapshot_id         text primary key,
    account_id          text not null references accounts(account_id),
    strategy_id         text,
    as_of_ts            timestamptz not null,
    payload             jsonb not null,
    created_at          timestamptz not null default now()
);

create table if not exists pnl_snapshots (
    snapshot_id         text primary key,
    account_id          text not null references accounts(account_id),
    strategy_id         text,
    as_of_ts            timestamptz not null,
    base_currency       text not null,
    equity              numeric(38, 18) not null,
    cash_balance        numeric(38, 18) not null default 0,
    realized_pnl        numeric(38, 18) not null default 0,
    unrealized_pnl      numeric(38, 18) not null default 0,
    fees                numeric(38, 18) not null default 0,
    funding             numeric(38, 18) not null default 0,
    slippage_cost       numeric(38, 18) not null default 0,
    exposure_notional   numeric(38, 18) not null default 0,
    formula_version     text not null,
    payload             jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists idx_pnl_snapshots_account_ts on pnl_snapshots(account_id, as_of_ts desc);

create table if not exists market_candles (
    candle_id           bigserial primary key,
    instrument_id       text not null references instruments(instrument_id),
    timeframe           text not null,
    ts_open             timestamptz not null,
    open                numeric(38, 18) not null,
    high                numeric(38, 18) not null,
    low                 numeric(38, 18) not null,
    close               numeric(38, 18) not null,
    volume              numeric(38, 18) not null default 0,
    source              text not null,
    created_at          timestamptz not null default now(),
    unique(instrument_id, timeframe, ts_open, source)
);
create index if not exists idx_market_candles_inst_tf_ts on market_candles(instrument_id, timeframe, ts_open);

create table if not exists indicator_values (
    indicator_value_id  bigserial primary key,
    instrument_id       text not null references instruments(instrument_id),
    timeframe           text not null,
    indicator_name      text not null,
    params_hash         text not null,
    ts_value            timestamptz not null,
    value_json          jsonb not null,
    created_at          timestamptz not null default now(),
    unique(instrument_id, timeframe, indicator_name, params_hash, ts_value)
);

create table if not exists indicator_refresh_policies (
    policy_id           bigserial primary key,
    instrument_id       text not null references instruments(instrument_id),
    timeframe           text not null,
    price_kind          text not null default 'last',
    source_preference   text not null default 'gateio',
    is_enabled          boolean not null default true,
    persist_candles     boolean not null default true,
    fetch_limit         integer not null default 300,
    parameters_json     jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique(instrument_id, timeframe, price_kind, source_preference)
);
create index if not exists idx_indicator_refresh_policies_inst_tf
    on indicator_refresh_policies(instrument_id, timeframe, is_enabled);

create table if not exists market_events (
    event_id            text primary key,
    category            text not null,
    title               text not null,
    summary             text,
    source              text not null,
    reliability         text not null,
    ts_event            timestamptz not null,
    ts_ingest           timestamptz not null default now(),
    payload_json        jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists idx_market_events_ts on market_events(ts_event desc);

create table if not exists market_event_instruments (
    event_id            text not null references market_events(event_id) on delete cascade,
    instrument_id       text not null references instruments(instrument_id),
    primary key (event_id, instrument_id)
);

create table if not exists audit_logs (
    audit_id            bigserial primary key,
    tenant_id           text not null,
    actor_user_id       text not null,
    action              text not null,
    resource_type       text not null,
    resource_id         text not null,
    request_id          text,
    trace_id            text,
    result_status       text not null,
    diff_json           jsonb,
    created_at          timestamptz not null default now()
);
