from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from app.core.db import Base
from scripts.create_verification_db import create_verification_database


def _build_source(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO instruments (
                instrument_id, venue, symbol, asset_class, base_ccy, quote_ccy,
                settle_ccy, tick_size, lot_size, contract_multiplier,
                margin_model, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "btc-usdt-perp",
                "gateio",
                "BTC_USDT",
                "crypto",
                "BTC",
                "USDT",
                "USDT",
                "0.1",
                "0.001",
                "1",
                "linear",
                "{}",
            ),
        )
        for cache_key, page_type in (
            ("strategy_scan:test", "strategy_scan"),
            ("strategy_unified:test", "strategy_unified"),
            ("events:test", "events"),
        ):
            connection.execute(
                """
                INSERT INTO page_snapshot_cache (
                    cache_key, page_type, payload_json, status, cache_state,
                    source_version, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cache_key, page_type, "{}", "ready", "fresh", "test", "{}"),
            )
        connection.commit()


def test_strategy_verification_database_copies_only_compact_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    output = tmp_path / "verification.db"
    _build_source(source)

    copied = create_verification_database(source, output)

    assert copied == {"instruments": 1, "page_snapshot_cache": 2}
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT count(*) FROM instruments").fetchone()[0] == 1
        page_types = {
            row[0]
            for row in connection.execute(
                "SELECT page_type FROM page_snapshot_cache ORDER BY page_type"
            )
        }
        assert page_types == {"strategy_scan", "strategy_unified"}
        assert connection.execute("SELECT count(*) FROM indicator_runs").fetchone()[0] == 0


def test_strategy_verification_database_refuses_to_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    output = tmp_path / "verification.db"
    _build_source(source)
    output.touch()

    try:
        create_verification_database(source, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing verification database must not be overwritten")
