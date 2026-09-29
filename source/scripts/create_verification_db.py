"""Build a compact, disposable SQLite database for UI verification.

The verification server must not write into the developer's active database.
Copying the entire database also is not acceptable: large history tables such
as ``indicator_runs`` are irrelevant to a cache-backed strategy matrix check.
This helper creates the current schema and copies only the published snapshots
needed by the AI strategy page.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine

from app.core.db import Base

STRATEGY_PAGE_TYPES = (
    "analysis",
    "strategy_scan",
    "strategy_unified",
    "strategy",
    "monitoring",
    "macro",
    "market_context",
)


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({_quoted(table)})")]


def _copy_rows(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    *,
    table: str,
    where_sql: str = "",
    parameters: Iterable[object] = (),
) -> int:
    source_columns = set(_columns(source, table))
    destination_columns = _columns(destination, table)
    common_columns = [column for column in destination_columns if column in source_columns]
    if not common_columns:
        raise RuntimeError(f"No compatible columns found for table {table!r}")

    column_sql = ", ".join(_quoted(column) for column in common_columns)
    select_sql = f"SELECT {column_sql} FROM {_quoted(table)}"
    if where_sql:
        select_sql += f" WHERE {where_sql}"
    insert_sql = (
        f"INSERT INTO {_quoted(table)} ({column_sql}) "
        f"VALUES ({', '.join('?' for _ in common_columns)})"
    )

    copied = 0
    cursor = source.execute(select_sql, tuple(parameters))
    while batch := cursor.fetchmany(200):
        destination.executemany(insert_sql, batch)
        copied += len(batch)
    return copied


def create_verification_database(source_path: Path, output_path: Path) -> dict[str, int]:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    if source_path == output_path:
        raise ValueError("Verification database must not overwrite the source database")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing verification database: {output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{output_path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    copied: dict[str, int] = {}
    try:
        with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(
            sqlite3.connect(output_path)
        ) as destination:
            destination.execute("PRAGMA foreign_keys=OFF")
            copied["instruments"] = _copy_rows(
                source,
                destination,
                table="instruments",
            )
            placeholders = ", ".join("?" for _ in STRATEGY_PAGE_TYPES)
            copied["page_snapshot_cache"] = _copy_rows(
                source,
                destination,
                table="page_snapshot_cache",
                where_sql=f"page_type IN ({placeholders})",
                parameters=STRATEGY_PAGE_TYPES,
            )
            destination.commit()
            destination.execute("VACUUM")
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return copied


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a compact AI-strategy verification database."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    copied = create_verification_database(args.source, args.output)
    size_mb = args.output.stat().st_size / (1024 * 1024)
    print(f"Created {args.output.resolve()} ({size_mb:.2f} MiB)")
    for table, count in copied.items():
        print(f"  {table}: {count} rows")
    print("Launch with WORKER_PROFILE=none and LOCAL_BOOTSTRAP_WARMUP_ENABLED=false.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
