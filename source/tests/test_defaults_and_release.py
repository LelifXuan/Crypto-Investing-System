from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from scripts.release_common import should_skip

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_market_data_prefers_cache_by_default() -> None:
    assert type(settings).model_fields["market_data_prefer_live"].default is False


def test_frontend_market_requests_default_to_cached_sources() -> None:
    source = (PROJECT_ROOT / "app" / "static" / "core" / "api.js").read_text(encoding="utf-8")
    assert 'prefer_live: options.preferLive ? "true" : "false"' in source
    assert "getCandles(instrumentId, timeframe, limit, options = {})" in source
    assert "getLatestMark(instrumentId, options = {})" in source


def test_release_common_excludes_runtime_databases_and_logs() -> None:
    cases = [
        PROJECT_ROOT / "run" / "double-client.err.log",
        PROJECT_ROOT / "runtime" / "cache" / "foo.json",
        PROJECT_ROOT / "dist" / "portable_bundle.zip",
        PROJECT_ROOT / "trading_system.db",
        PROJECT_ROOT / "trading_system.db-wal",
        PROJECT_ROOT / "__pycache__" / "x.pyc",
        PROJECT_ROOT / ".pytest_cache" / "state",
        PROJECT_ROOT / ".ruff_cache" / "data",
        PROJECT_ROOT / ".env",
    ]
    for case in cases:
        assert should_skip(case, root=PROJECT_ROOT) is True
