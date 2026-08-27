"""Safely reset externally fetched and reproducible market data.

The command deliberately preserves trading facts, accounting state, strategy
audit records, research registries, users, and the append-only event store.
It is intended for cold-start connectivity audits, not routine maintenance.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

REPRODUCIBLE_TABLES = (
    "indicator_alert_events",
    "market_event_translation_map",
    "market_event_instruments",
    "market_events",
    "indicator_observations",
    "indicator_runs",
    "indicator_values",
    "macro_event_calendar",
    "macro_source_health",
    "mark_prices",
    "market_candles",
    "gold_oi_daily_snapshots",
    "decision_input_snapshots",
    "domain_snapshot_records",
    "structure_active_item",
    "structure_alert",
    "structure_event",
    "structure_geometry",
    "structure_snapshot",
    "structure_system_judgement",
    "structure_system_scores",
    "supply_event_calendar_nodes",
    "supply_event_snapshots",
    "translation_cache",
    "translation_jobs",
    "translation_text_cache",
    "page_snapshot_cache",
    "computed_dataset_cache",
)

PROTECTED_TABLES = frozenset(
    {
        "fills",
        "orders",
        "positions",
        "position_lots",
        "position_ledger_entries",
        "fill_lot_allocations",
        "funding_events",
        "account_equity_snapshots",
        "fx_valuation_snapshots",
        "gold_execution_events",
        "event_store",
        "event_outbox",
        "strategy_decision",
        "strategy_decision_outcome",
        "strategy_signal",
        "strategy_signal_outcome",
        "signal_outcome",
    }
)


def _assert_child(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    if resolved == root.resolve():
        raise ValueError(f"refusing to clear root directory: {resolved}")
    return resolved


def _clear_directory(path: Path, root: Path) -> tuple[int, int]:
    target = _assert_child(path, root)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return 0, 0
    files = [item for item in target.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    for item in sorted(target.iterdir(), key=lambda candidate: candidate.name):
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    return len(files), total_bytes


def reset_external_data(
    database: Path,
    runtime_root: Path,
    resource_root: Path,
    *,
    include_shipped_cftc: bool = False,
) -> dict[str, object]:
    database = database.resolve()
    runtime_root = runtime_root.resolve()
    resource_root = resource_root.resolve()
    expected_database = _assert_child(runtime_root / "data" / database.name, runtime_root)
    if database != expected_database or not database.is_file():
        raise ValueError(f"unexpected database path: {database}")
    if PROTECTED_TABLES.intersection(REPRODUCIBLE_TABLES):
        raise RuntimeError("reset allowlist overlaps protected trading facts")

    deleted_rows: dict[str, int] = {}
    with sqlite3.connect(database, timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table in REPRODUCIBLE_TABLES:
                if table not in existing:
                    continue
                before = connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                connection.execute(f'DELETE FROM "{table}"')
                deleted_rows[table] = int(before)
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            connection.rollback()
            raise

    cleared_paths: dict[str, dict[str, int]] = {}
    for path in (
        runtime_root / "cache",
        runtime_root / "data" / "derivatives_archive",
        runtime_root / "data" / "research",
    ):
        files, total_bytes = _clear_directory(path, runtime_root)
        cleared_paths[str(path)] = {"files": files, "bytes": total_bytes}

    for path in (
        runtime_root / "data" / "xaut_oi_cache.json",
        runtime_root / "data" / "refresh_jobs.sqlite3",
    ):
        target = _assert_child(path, runtime_root)
        if target.exists():
            size = target.stat().st_size
            target.unlink()
            cleared_paths[str(target)] = {"files": 1, "bytes": size}

    if include_shipped_cftc:
        cftc_root = _assert_child(resource_root / "data" / "cftc", resource_root)
        files, total_bytes = _clear_directory(cftc_root, resource_root)
        cleared_paths[str(cftc_root)] = {"files": files, "bytes": total_bytes}

    return {
        "database": str(database),
        "deleted_rows": deleted_rows,
        "cleared_paths": cleared_paths,
        "protected_tables": sorted(PROTECTED_TABLES),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--resource-root", type=Path, required=True)
    parser.add_argument("--include-shipped-cftc", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "tables": REPRODUCIBLE_TABLES,
                    "protected_tables": sorted(PROTECTED_TABLES),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    result = reset_external_data(
        args.database,
        args.runtime_root,
        args.resource_root,
        include_shipped_cftc=args.include_shipped_cftc,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
