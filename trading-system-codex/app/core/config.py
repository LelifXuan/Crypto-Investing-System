from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import app_paths, bootstrap_runtime_environment

bootstrap_runtime_environment()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(app_paths.portable_env_path), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Trading System API", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_distribution_mode: str = Field(
        default=app_paths.distribution_mode, alias="APP_DISTRIBUTION_MODE"
    )
    app_host: str = Field(
        default="127.0.0.1" if app_paths.distribution_mode == "portable" else "0.0.0.0",
        alias="APP_HOST",
    )
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_debug: bool = Field(default=app_paths.distribution_mode != "portable", alias="APP_DEBUG")
    worker_profile: str = Field(default="desktop_light", alias="WORKER_PROFILE")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default=app_paths.default_database_url,
        alias="DATABASE_URL",
    )
    default_reporting_currency: str = Field(default="USD", alias="DEFAULT_REPORTING_CURRENCY")
    default_cost_method: str = Field(default="AVG_COST", alias="DEFAULT_COST_METHOD")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")
    single_user_mode: bool = Field(default=True, alias="SINGLE_USER_MODE")
    local_only_enforced: bool = Field(default=True, alias="LOCAL_ONLY_ENFORCED")
    local_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "::1", "localhost", "testclient"],
        alias="LOCAL_ALLOWED_HOSTS",
    )
    local_tenant_id: str = Field(default="local_tenant", alias="LOCAL_TENANT_ID")
    local_user_id: str = Field(default="local_user", alias="LOCAL_USER_ID")
    local_username: str = Field(default="local", alias="LOCAL_USERNAME")
    local_user_roles: list[str] = Field(
        default_factory=lambda: ["admin", "trader", "analyst", "viewer"],
        alias="LOCAL_USER_ROLES",
    )

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=120, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    bootstrap_admin_username: str = Field(default="admin", alias="BOOTSTRAP_ADMIN_USERNAME")
    bootstrap_admin_password: str = Field(default="admin123", alias="BOOTSTRAP_ADMIN_PASSWORD")
    auto_create_schema: bool = Field(default=True, alias="AUTO_CREATE_SCHEMA")
    local_auto_bootstrap_enabled: bool = Field(default=True, alias="LOCAL_AUTO_BOOTSTRAP_ENABLED")
    local_bootstrap_warmup_enabled: bool = Field(
        default=True,
        alias="LOCAL_BOOTSTRAP_WARMUP_ENABLED",
    )
    local_bootstrap_warmup_all_instruments: bool = Field(
        default=app_paths.distribution_mode != "portable",
        alias="LOCAL_BOOTSTRAP_WARMUP_ALL_INSTRUMENTS",
    )
    local_bootstrap_candle_limit: int = Field(default=240, alias="LOCAL_BOOTSTRAP_CANDLE_LIMIT")
    local_bootstrap_candle_limits_by_timeframe: str = Field(
        default='{"1h":1000,"4h":1000,"1d":1000,"1w":520,"30d":360}',
        alias="LOCAL_BOOTSTRAP_CANDLE_LIMITS_BY_TIMEFRAME",
    )
    local_bootstrap_warmup_timeframes: list[str] = Field(
        default_factory=lambda: ["1h", "4h", "1d", "1w", "30d"],
        alias="LOCAL_BOOTSTRAP_WARMUP_TIMEFRAMES",
    )
    local_bootstrap_structure_timeframes: list[str] = Field(
        default_factory=lambda: ["1h", "4h", "1d", "1w"],
        alias="LOCAL_BOOTSTRAP_STRUCTURE_TIMEFRAMES",
    )

    event_bus_enabled: bool = Field(default=True, alias="EVENT_BUS_ENABLED")
    event_bus_poll_interval_ms: int = Field(default=1500, alias="EVENT_BUS_POLL_INTERVAL_MS")
    event_bus_batch_size: int = Field(default=25, alias="EVENT_BUS_BATCH_SIZE")
    event_bus_max_retries: int = Field(default=5, alias="EVENT_BUS_MAX_RETRIES")
    event_bus_retry_delay_seconds: int = Field(default=10, alias="EVENT_BUS_RETRY_DELAY_SECONDS")

    require_idempotency_for_fill_writes: bool = Field(
        default=True, alias="REQUIRE_IDEMPOTENCY_FOR_FILL_WRITES"
    )

    market_data_provider: str = Field(default="gateio", alias="MARKET_DATA_PROVIDER")
    market_data_prefer_live: bool = Field(default=False, alias="MARKET_DATA_PREFER_LIVE")
    gateio_base_url: str = Field(default="https://api.gateio.ws/api/v4", alias="GATEIO_BASE_URL")
    gateio_timeout_seconds: int = Field(default=10, alias="GATEIO_TIMEOUT_SECONDS")
    gateio_default_settle: str = Field(default="usdt", alias="GATEIO_DEFAULT_SETTLE")
    market_stream_enabled: bool = Field(default=True, alias="MARKET_STREAM_ENABLED")
    market_stream_prefer_ws_cache: bool = Field(default=True, alias="MARKET_STREAM_PREFER_WS_CACHE")
    market_stream_persist_marks: bool = Field(default=True, alias="MARKET_STREAM_PERSIST_MARKS")
    market_stream_persist_candles: bool = Field(default=True, alias="MARKET_STREAM_PERSIST_CANDLES")
    market_stream_timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "5m"], alias="MARKET_STREAM_TIMEFRAMES"
    )
    market_stream_ping_interval_seconds: int = Field(
        default=20, alias="MARKET_STREAM_PING_INTERVAL_SECONDS"
    )
    market_stream_reconnect_delay_seconds: int = Field(
        default=5, alias="MARKET_STREAM_RECONNECT_DELAY_SECONDS"
    )
    market_stream_mark_persist_min_interval_seconds: int = Field(
        default=3,
        alias="MARKET_STREAM_MARK_PERSIST_MIN_INTERVAL_SECONDS",
    )
    shared_query_cache_seconds: int = Field(
        default=20,
        alias="SHARED_QUERY_CACHE_SECONDS",
    )
    macro_calendar_cache_seconds: int = Field(
        default=60,
        alias="MACRO_CALENDAR_CACHE_SECONDS",
    )
    indicator_refresh_interval_seconds: int = Field(
        default=600,
        alias="INDICATOR_REFRESH_INTERVAL_SECONDS",
    )
    indicator_read_auto_refresh: bool = Field(
        default=False,
        alias="INDICATOR_READ_AUTO_REFRESH",
    )
    gateio_spot_ws_url: str = Field(
        default="wss://api.gateio.ws/ws/v4/", alias="GATEIO_SPOT_WS_URL"
    )
    gateio_futures_ws_url_template: str = Field(
        default="wss://fx-ws.gateio.ws/v4/ws/{settle}",
        alias="GATEIO_FUTURES_WS_URL_TEMPLATE",
    )
    market_events_feed_enabled: bool = Field(default=True, alias="MARKET_EVENTS_FEED_ENABLED")
    market_events_poll_seconds: int = Field(default=1800, alias="MARKET_EVENTS_POLL_SECONDS")
    market_events_translate_enabled: bool = Field(
        default=False, alias="MARKET_EVENTS_TRANSLATE_ENABLED"
    )
    market_events_translation_provider: str = Field(
        default="mymemory",
        alias="MARKET_EVENTS_TRANSLATION_PROVIDER",
    )
    market_events_translation_base_url: str = Field(
        default="https://api.mymemory.translated.net/get",
        alias="MARKET_EVENTS_TRANSLATION_BASE_URL",
    )
    market_events_translation_target_lang: str = Field(
        default="zh-CN",
        alias="MARKET_EVENTS_TRANSLATION_TARGET_LANG",
    )
    market_events_translation_timeout_seconds: int = Field(
        default=10,
        alias="MARKET_EVENTS_TRANSLATION_TIMEOUT_SECONDS",
    )
    market_events_translation_worker_enabled: bool = Field(
        default=True,
        alias="MARKET_EVENTS_TRANSLATION_WORKER_ENABLED",
    )
    market_events_translation_poll_seconds: int = Field(
        default=10,
        alias="MARKET_EVENTS_TRANSLATION_POLL_SECONDS",
    )
    market_events_translation_batch_size: int = Field(
        default=6,
        alias="MARKET_EVENTS_TRANSLATION_BATCH_SIZE",
    )
    market_events_translation_concurrency: int = Field(
        default=2,
        alias="MARKET_EVENTS_TRANSLATION_CONCURRENCY",
    )
    market_events_translation_retry_delay_seconds: int = Field(
        default=600,
        alias="MARKET_EVENTS_TRANSLATION_RETRY_DELAY_SECONDS",
    )
    market_events_translation_cache_enabled: bool = Field(
        default=True,
        alias="MARKET_EVENTS_TRANSLATION_CACHE_ENABLED",
    )
    market_event_feed_urls: list[str] = Field(
        default_factory=lambda: [
            "https://cointelegraph.com/rss/tag/markets",
            "https://www.theblock.co/rss.xml",
            "https://decrypt.co/feed",
        ],
        alias="MARKET_EVENT_FEED_URLS",
    )
    monitoring_scheduler_enabled: bool = Field(default=True, alias="MONITORING_SCHEDULER_ENABLED")
    monitoring_scheduler_poll_seconds: int = Field(
        default=15, alias="MONITORING_SCHEDULER_POLL_SECONDS"
    )
    monitoring_stale_refresh_check_seconds: int = Field(
        default=3600,
        alias="MONITORING_STALE_REFRESH_CHECK_SECONDS",
    )
    monitoring_default_quality_score: int = Field(
        default=95, alias="MONITORING_DEFAULT_QUALITY_SCORE"
    )
    monitoring_demo_quality_score: int = Field(default=60, alias="MONITORING_DEMO_QUALITY_SCORE")
    ashare_etf_provider_order: list[str] = Field(
        default_factory=lambda: ["eastmoney_direct"],
        alias="ASHARE_ETF_PROVIDER_ORDER",
    )
    ashare_etf_quote_ttl_seconds: int = Field(default=15, alias="ASHARE_ETF_QUOTE_TTL_SECONDS")
    ashare_etf_stale_cache_seconds: int = Field(
        default=1800,
        alias="ASHARE_ETF_STALE_CACHE_SECONDS",
    )
    ashare_etf_timeout_seconds: int = Field(default=6, alias="ASHARE_ETF_TIMEOUT_SECONDS")
    ashare_etf_eastmoney_base_url: str = Field(
        default="https://push2.eastmoney.com",
        alias="ASHARE_ETF_EASTMONEY_BASE_URL",
    )
    fred_public_csv_url: str = Field(
        default="https://fred.stlouisfed.org/graph/fredgraph.csv",
        alias="FRED_PUBLIC_CSV_URL",
    )
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    bls_api_key: str = Field(default="", alias="BLS_API_KEY")
    bea_api_key: str = Field(default="", alias="BEA_API_KEY")
    glassnode_api_key: str = Field(default="", alias="GLASSNODE_API_KEY")
    history_mark_prices_keep_per_series: int = Field(
        default=720,
        alias="HISTORY_MARK_PRICES_KEEP_PER_SERIES",
    )
    enable_docs: bool = Field(
        default=app_paths.distribution_mode != "portable", alias="ENABLE_DOCS"
    )
    enable_openapi: bool = Field(
        default=app_paths.distribution_mode != "portable", alias="ENABLE_OPENAPI"
    )
    portable_remote_translation_enabled: bool = Field(
        default=False, alias="PORTABLE_REMOTE_TRANSLATION_ENABLED"
    )
    precompute_enabled: bool = Field(default=True, alias="PRECOMPUTE_ENABLED")
    precompute_max_queue_size: int = Field(default=200, alias="PRECOMPUTE_MAX_QUEUE_SIZE")
    precompute_worker_interval_seconds: int = Field(
        default=3, alias="PRECOMPUTE_WORKER_INTERVAL_SECONDS"
    )
    precompute_max_concurrency: int = Field(default=1, alias="PRECOMPUTE_MAX_CONCURRENCY")
    precompute_cpu_idle_threshold: float = Field(
        default=0.72, alias="PRECOMPUTE_CPU_IDLE_THRESHOLD"
    )
    precompute_min_seconds_between_same_key: int = Field(
        default=120, alias="PRECOMPUTE_MIN_SECONDS_BETWEEN_SAME_KEY"
    )
    page_snapshot_analysis_ttl_seconds: int = Field(
        default=180, alias="PAGE_SNAPSHOT_ANALYSIS_TTL_SECONDS"
    )
    page_snapshot_structure_ttl_seconds: int = Field(
        default=180, alias="PAGE_SNAPSHOT_STRUCTURE_TTL_SECONDS"
    )
    page_snapshot_alerts_ttl_seconds: int = Field(
        default=180, alias="PAGE_SNAPSHOT_ALERTS_TTL_SECONDS"
    )
    page_snapshot_monitoring_ttl_seconds: int = Field(
        default=180, alias="PAGE_SNAPSHOT_MONITORING_TTL_SECONDS"
    )
    page_snapshot_macro_ttl_seconds: int = Field(
        default=300, alias="PAGE_SNAPSHOT_MACRO_TTL_SECONDS"
    )
    page_snapshot_events_ttl_seconds: int = Field(
        default=300, alias="PAGE_SNAPSHOT_EVENTS_TTL_SECONDS"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
