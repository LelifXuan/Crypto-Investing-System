from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.reset_external_market_data import PROTECTED_TABLES, reset_external_data


def test_reset_deletes_reproducible_data_and_preserves_facts(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    data = runtime / "data"
    cache = runtime / "cache"
    resource = tmp_path / "resource"
    database = data / "trading_system.db"
    data.mkdir(parents=True)
    cache.mkdir(parents=True)
    resource.mkdir()
    (cache / "provider.json").write_text("{}", encoding="utf-8")
    (data / "derivatives_archive").mkdir()
    (data / "derivatives_archive" / "raw.json").write_text("{}", encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE market_candles (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE page_snapshot_cache (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE fills (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE event_store (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO market_candles VALUES (1)")
        connection.execute("INSERT INTO page_snapshot_cache VALUES (1)")
        connection.execute("INSERT INTO fills VALUES (1)")
        connection.execute("INSERT INTO event_store VALUES (1)")

    result = reset_external_data(database, runtime, resource)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM market_candles").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM page_snapshot_cache").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM event_store").fetchone()[0] == 1
    assert result["deleted_rows"] == {"market_candles": 1, "page_snapshot_cache": 1}
    assert list(cache.iterdir()) == []
    assert PROTECTED_TABLES.isdisjoint(result["deleted_rows"])


def test_reset_rejects_database_outside_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    database = tmp_path / "outside.db"
    database.touch()

    try:
        reset_external_data(database, runtime, tmp_path / "resource")
    except ValueError as exc:
        assert "unexpected database path" in str(exc)
    else:
        raise AssertionError("outside database must be rejected")
