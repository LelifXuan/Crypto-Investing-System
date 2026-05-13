from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Trading System API", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/trading_system",
        alias="DATABASE_URL",
    )
    default_reporting_currency: str = Field(default="USD", alias="DEFAULT_REPORTING_CURRENCY")
    default_cost_method: str = Field(default="AVG_COST", alias="DEFAULT_COST_METHOD")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8000", "http://localhost:8000"],
        alias="CORS_ORIGINS",
    )

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
    jwt_access_token_expire_minutes: int = Field(default=120, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")

    bootstrap_admin_username: str = Field(default="admin", alias="BOOTSTRAP_ADMIN_USERNAME")
    bootstrap_admin_password: str = Field(default="admin123", alias="BOOTSTRAP_ADMIN_PASSWORD")

    event_bus_enabled: bool = Field(default=True, alias="EVENT_BUS_ENABLED")
    event_bus_poll_interval_ms: int = Field(default=1500, alias="EVENT_BUS_POLL_INTERVAL_MS")
    event_bus_batch_size: int = Field(default=25, alias="EVENT_BUS_BATCH_SIZE")
    event_bus_max_retries: int = Field(default=5, alias="EVENT_BUS_MAX_RETRIES")
    event_bus_retry_delay_seconds: int = Field(default=10, alias="EVENT_BUS_RETRY_DELAY_SECONDS")

    require_idempotency_for_fill_writes: bool = Field(default=True, alias="REQUIRE_IDEMPOTENCY_FOR_FILL_WRITES")

    market_data_provider: str = Field(default="gateio", alias="MARKET_DATA_PROVIDER")
    market_data_prefer_live: bool = Field(default=True, alias="MARKET_DATA_PREFER_LIVE")
    gateio_base_url: str = Field(default="https://api.gateio.ws/api/v4", alias="GATEIO_BASE_URL")
    gateio_timeout_seconds: int = Field(default=10, alias="GATEIO_TIMEOUT_SECONDS")
    gateio_default_settle: str = Field(default="usdt", alias="GATEIO_DEFAULT_SETTLE")

    market_stream_enabled: bool = Field(default=True, alias="MARKET_STREAM_ENABLED")
    market_stream_prefer_ws_cache: bool = Field(default=True, alias="MARKET_STREAM_PREFER_WS_CACHE")
    market_stream_persist_marks: bool = Field(default=True, alias="MARKET_STREAM_PERSIST_MARKS")
    market_stream_persist_candles: bool = Field(default=True, alias="MARKET_STREAM_PERSIST_CANDLES")
    market_stream_timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m"], alias="MARKET_STREAM_TIMEFRAMES")
    market_stream_ping_interval_seconds: int = Field(default=20, alias="MARKET_STREAM_PING_INTERVAL_SECONDS")
    market_stream_reconnect_delay_seconds: int = Field(default=5, alias="MARKET_STREAM_RECONNECT_DELAY_SECONDS")
    market_stream_mark_persist_min_interval_seconds: int = Field(
        default=3,
        alias="MARKET_STREAM_MARK_PERSIST_MIN_INTERVAL_SECONDS",
    )
    gateio_spot_ws_url: str = Field(default="wss://api.gateio.ws/ws/v4/", alias="GATEIO_SPOT_WS_URL")
    gateio_futures_ws_url_template: str = Field(
        default="wss://fx-ws.gateio.ws/v4/ws/{settle}",
        alias="GATEIO_FUTURES_WS_URL_TEMPLATE",
    )

    market_events_enabled: bool = Field(default=True, alias="MARKET_EVENTS_ENABLED")
    market_events_poll_interval_seconds: int = Field(default=300, alias="MARKET_EVENTS_POLL_INTERVAL_SECONDS")
    market_events_default_limit: int = Field(default=50, alias="MARKET_EVENTS_DEFAULT_LIMIT")
    market_events_gate_announcements_enabled: bool = Field(
        default=True,
        alias="MARKET_EVENTS_GATE_ANNOUNCEMENTS_ENABLED",
    )
    market_events_gate_announcements_urls: list[str] = Field(
        default_factory=lambda: ["https://www.gate.com/announcements/39741"],
        alias="MARKET_EVENTS_GATE_ANNOUNCEMENTS_URLS",
    )
    market_events_rss_urls: list[str] = Field(default_factory=list, alias="MARKET_EVENTS_RSS_URLS")

    local_secrets_dir: str = Field(default=".local_secrets", alias="LOCAL_SECRETS_DIR")
    local_secret_key_filename: str = Field(default="master.key", alias="LOCAL_SECRET_KEY_FILENAME")
    local_secret_store_filename: str = Field(default="secrets.enc", alias="LOCAL_SECRET_STORE_FILENAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
