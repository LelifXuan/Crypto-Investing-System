from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarkPrice(Base):
    __tablename__ = "mark_prices"

    mark_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"), nullable=False, index=True
    )
    mark_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "timeframe", "ts_open", "source", name="uq_market_candles_unique"
        ),
    )

    candle_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    ts_open: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoldPolicyVersion(Base):
    """Versioned gold allocation policy (tenant+user scoped).

    Maps the existing ``gold_policy_versions`` table (migration 0012,
    applied on 2026-07-28). The workbench read path consumes the latest
    version to derive base-DCA / dip-add decisions.
    """

    __tablename__ = "gold_policy_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "version", name="uq_gold_policy_version"),
    )

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    portfolio_total: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    gold_current_value: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    available_cash: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    target_min: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    target_max: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    base_dca_amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    fixed_dip_add_amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    cooldown_days: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_max_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmations_required: Mapped[int] = mapped_column(Integer, nullable=False)
    drawdown_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    pause_base_when_overweight: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GoldExecutionEvent(Base):
    """Append-only record of executed gold base-DCA / dip-add actions.

    Maps the existing ``gold_execution_events`` table. Used by the
    workbench to derive ``executed_today`` / ``last_dip_add_date`` so
    decisions respect the cooldown and daily-execution idempotency.
    """

    __tablename__ = "gold_execution_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "idempotency_key", name="uq_gold_execution_idempotency"
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IndicatorValue(Base):
    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "indicator_name",
            "params_hash",
            "ts_value",
            name="uq_indicator_values_unique",
        ),
    )

    indicator_value_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    indicator_name: Mapped[str] = mapped_column(String, nullable=False)
    params_hash: Mapped[str] = mapped_column(String, nullable=False)
    ts_value: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndicatorRefreshPolicy(Base):
    __tablename__ = "indicator_refresh_policies"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "price_kind",
            "source_preference",
            name="uq_indicator_refresh_policies_unique",
        ),
    )

    policy_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    price_kind: Mapped[str] = mapped_column(String, nullable=False, default="last")
    source_preference: Mapped[str] = mapped_column(String, nullable=False, default="gateio")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    persist_candles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fetch_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketEvent(Base):
    __tablename__ = "market_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    reliability: Mapped[str] = mapped_column(String, nullable=False)
    ts_event: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ts_ingest: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketEventInstrument(Base):
    __tablename__ = "market_event_instruments"

    event_id: Mapped[str] = mapped_column(
        ForeignKey("market_events.event_id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"), primary_key=True
    )


class TranslationCache(Base):
    __tablename__ = "translation_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider", "target_language", "source_text_hash", name="uq_translation_cache_key"
        ),
    )

    cache_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_language: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_text_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_text: Mapped[str] = mapped_column(String, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranslationTextCache(Base):
    __tablename__ = "translation_text_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "source_language",
            "target_language",
            "normalized_text_hash",
            name="uq_translation_text_cache_key",
        ),
    )

    cache_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_language: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_language: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_text_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_text: Mapped[str] = mapped_column(String, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranslationJob(Base):
    __tablename__ = "translation_jobs"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_translation_jobs_dedupe"),)

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_language: Mapped[str] = mapped_column(String, nullable=False)
    target_language: Mapped[str] = mapped_column(String, nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketEventTranslationMap(Base):
    __tablename__ = "market_event_translation_map"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "field_name",
            "provider",
            "target_language",
            name="uq_market_event_translation_map",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("market_events.event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_language: Mapped[str] = mapped_column(String, nullable=False)
    target_language: Mapped[str] = mapped_column(String, nullable=False)
    normalized_text_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    translated_text: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"

    indicator_key: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    family: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_provider: Mapped[str] = mapped_column(String, nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    calc_engine: Mapped[str] = mapped_column(String, nullable=False)
    calc_params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    supported_assets_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supported_timeframes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    output_fields_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    signal_states_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    default_thresholds_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    use_cases_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndicatorMonitoringPolicy(Base):
    __tablename__ = "indicator_monitoring_policies"
    __table_args__ = (
        UniqueConstraint(
            "indicator_key",
            "scope_type",
            "instrument_id",
            "asset_code",
            "timeframe",
            name="uq_indicator_monitoring_policies_scope",
        ),
    )

    policy_id: Mapped[str] = mapped_column(String, primary_key=True)
    indicator_key: Mapped[str] = mapped_column(
        ForeignKey("indicator_definitions.indicator_key"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asset_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_expr: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    event_key: Mapped[str | None] = mapped_column(String, nullable=True)
    calendar_source: Mapped[str | None] = mapped_column(String, nullable=True)
    release_key: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndicatorObservation(Base):
    __tablename__ = "indicator_observations"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_indicator_observations_dedupe"),)

    observation_id: Mapped[str] = mapped_column(String, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    indicator_key: Mapped[str] = mapped_column(
        ForeignKey("indicator_definitions.indicator_key"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asset_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String, nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    observation_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_start_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_end_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    baseline_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    delta_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    zscore_num: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    percentile_num: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    signal_state: Mapped[str | None] = mapped_column(String, nullable=True)
    signal_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    source_provider: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    source_granularity: Mapped[str | None] = mapped_column(String, nullable=True)
    is_preliminary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=100)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IndicatorAlertRule(Base):
    __tablename__ = "indicator_alert_rules"

    rule_key: Mapped[str] = mapped_column(String, primary_key=True)
    indicator_key: Mapped[str] = mapped_column(
        ForeignKey("indicator_definitions.indicator_key"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    condition_type: Mapped[str] = mapped_column(String, nullable=False)
    comparator: Mapped[str | None] = mapped_column(String, nullable=True)
    threshold_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    lower_threshold_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    upper_threshold_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    state_value: Mapped[str | None] = mapped_column(String, nullable=True)
    percentile_ref_window_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedupe_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    action_channels_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    message_template: Mapped[str] = mapped_column(String, nullable=False)
    extra_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IndicatorAlertEvent(Base):
    __tablename__ = "indicator_alert_events"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_indicator_alert_events_dedupe"),)

    alert_event_id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_key: Mapped[str] = mapped_column(
        ForeignKey("indicator_alert_rules.rule_key"), nullable=False, index=True
    )
    indicator_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    observation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asset_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MacroEventCalendar(Base):
    __tablename__ = "macro_event_calendar"
    __table_args__ = (
        UniqueConstraint(
            "provider_key", "event_key", "scheduled_at", name="uq_macro_event_calendar_unique"
        ),
    )

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String, nullable=False, default="US")
    title: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actual_value_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    consensus_value_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    previous_value_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    surprise_num: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    importance: Mapped[str] = mapped_column(String, nullable=False, default="high")
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PageSnapshotCache(Base):
    __tablename__ = "page_snapshot_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_page_snapshot_cache_key"),)

    cache_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    page_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="missing", index=True)
    cache_state: Mapped[str] = mapped_column(String, nullable=False, default="missing", index=True)
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_version: Mapped[str] = mapped_column(String, nullable=False, default="v1", index=True)
    cost_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComputedDatasetCache(Base):
    __tablename__ = "computed_dataset_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_computed_dataset_cache_key"),)

    dataset_cache_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dataset_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_data_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cache_state: Mapped[str] = mapped_column(String, nullable=False, default="missing", index=True)
    source_version: Mapped[str] = mapped_column(String, nullable=False, default="v1", index=True)
    calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cost_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MacroSourceHealth(Base):
    __tablename__ = "macro_source_health"
    __table_args__ = (
        UniqueConstraint("provider_key", "source_key", name="uq_macro_source_health_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndicatorRun(Base):
    __tablename__ = "indicator_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    indicator_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    trigger_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    stats_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SignalOutcome(Base):
    __tablename__ = "signal_outcome"
    __table_args__ = (
        UniqueConstraint(
            "signal_type", "signal_ref", "timeframe", "signal_ts", name="uq_signal_outcome_signal"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    signal_ref: Mapped[str] = mapped_column(String, nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False, index=True)
    signal_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    entry_ref_price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    bars_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_6: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_12: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_24: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_1: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_3: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_6: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_12: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_24: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mfe: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    take_profit_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyDecision(Base):
    __tablename__ = "strategy_decision"
    __table_args__ = (UniqueConstraint("decision_id", name="uq_strategy_decision_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False, index=True)
    decision_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String, nullable=False, index=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    execution_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    capital_ceiling_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    position_side: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    position_notional: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    config_version: Mapped[str] = mapped_column(String, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    conflict_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    action_plan_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyDecisionOutcome(Base):
    __tablename__ = "strategy_decision_outcome"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    bars_1_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bars_3_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bars_6_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bars_12_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bars_24_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fee_adjusted_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    slippage_adjusted_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mfe: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    take_profit_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    invalidation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    review_label: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyIterationProposal(Base):
    __tablename__ = "strategy_iteration_proposal"
    __table_args__ = (UniqueConstraint("proposal_id", name="uq_strategy_iteration_proposal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instrument_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timeframe: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    proposal_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_module: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    suggested_change_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# AI strategy models
# =============================================================================


class StrategyTemplate(Base):
    """AI strategy template."""

    __tablename__ = "strategy_template"
    __table_args__ = (UniqueConstraint("template_key", name="uq_strategy_template_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)  # long/short/both
    entry_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    exit_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    applicable_instruments_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applicable_timeframes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_indicators_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    strength_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    confidence_ceiling: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="gpt-4")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StrategyRecommendation(Base):
    """AI strategy recommendation."""

    __tablename__ = "strategy_recommendation"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "recommendation_ts",
            name="uq_strategy_recommendation_unique",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    recommendation_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    template_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)  # long/short
    bias_label: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    strength_score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    entry_price_range_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    take_profit_prices_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    current_market_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    entry_conditions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    exit_conditions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    market_conflicts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active/expired/triggered/archived
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="gpt-4")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategySignal(Base):
    """Market strategy signal."""

    __tablename__ = "strategy_signal"
    __table_args__ = (
        UniqueConstraint("signal_key", "timeframe", "signal_ts", name="uq_strategy_signal_unique"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    template_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)  # long/short
    signal_state: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # pending/active/closed/cancelled
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    risk_reward_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    signal_source: Mapped[str] = mapped_column(String(64), nullable=False, default="ai_generated")
    trigger_indicators_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    context_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    market_condition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategySignalOutcome(Base):
    """Market strategy signal outcome."""

    __tablename__ = "strategy_signal_outcome"
    __table_args__ = (
        UniqueConstraint(
            "signal_key", "timeframe", "signal_ts", name="uq_strategy_signal_outcome_unique"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_ref_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    outcome_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    bars_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_6: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_12: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bars_24: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_1: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_3: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_6: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_12: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    return_24: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mfe: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fee_adjusted_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    slippage_adjusted_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    take_profit_hit_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    invalidation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    trailing_stop_activated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    atr_at_entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    atr_at_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    risk_reward_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyEventCalendarNode(Base):
    """A scheduled supply-event node (planned unlock / claim / sellable etc.).

    Read-only for the calendar view: the table is populated by the supply
    event pipeline (whitepaper / exchange / on-chain scrapers), and the
    market-events page renders it as the "未来事件日历".
    """

    __tablename__ = "supply_event_calendar_nodes"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String, nullable=False)
    node_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
