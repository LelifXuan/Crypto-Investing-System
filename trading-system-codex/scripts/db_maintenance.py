#!/usr/bin/env python
"""Database maintenance tasks for Trading System.

Usage:
    python scripts/db_maintenance.py backup
    python scripts/db_maintenance.py vacuum
    python scripts/db_maintenance.py recreate
    python scripts/db_maintenance.py check
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
RUNTIME_ROOT = PROJECT_ROOT.parent / "runtime_dev" / "source_runtime"
DB_PATH = RUNTIME_ROOT / "data" / "trading_system.db"
BACKUP_DIR = RUNTIME_ROOT / "data" / "backups"


def backup() -> int:
    if not DB_PATH.exists():
        print(f"error: database not found at {DB_PATH}")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"trading_system_{ts}.db"

    shutil.copy2(DB_PATH, dest)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"Backed up to {dest} ({size_mb:.1f} MB)")

    existing = sorted(BACKUP_DIR.glob("trading_system_*.db"), reverse=True)
    for old in existing[5:]:
        old.unlink()
        print(f"Cleaned old backup: {old.name}")
    return 0


def vacuum() -> int:
    if not DB_PATH.exists():
        print(f"error: database not found at {DB_PATH}")
        return 1

    import sqlite3
    size_before = DB_PATH.stat().st_size

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("VACUUM")
    conn.close()

    size_after = DB_PATH.stat().st_size
    saved_mb = (size_before - size_after) / (1024 * 1024)
    print(f"VACUUM complete: {size_before/1024/1024:.1f} MB -> {size_after/1024/1024:.1f} MB (saved {saved_mb:.1f} MB)")
    return 0


def recreate() -> int:
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(".db.recreate_backup")
        shutil.copy2(DB_PATH, backup_path)
        print(f"Old DB backed up to {backup_path}")
        DB_PATH.unlink()
        print(f"Deleted {DB_PATH}")

    print("Restart the application to recreate the database from schema.")
    return 0


def check_db() -> int:
    if not DB_PATH.exists():
        print(f"warning: database not found at {DB_PATH}")
        return 1

    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {len(tables)}")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        count = cur.fetchone()[0]
        print(f"  {t}: {count} rows")

    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()[0]
    print(f"Integrity: {result}")
    conn.close()
    return 0 if result == "ok" else 1


COMMANDS = {"backup": backup, "vacuum": vacuum, "recreate": recreate, "check": check_db}


def main() -> int:
    parser = argparse.ArgumentParser(description="Database maintenance")
    parser.add_argument("command", choices=list(COMMANDS))
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    return COMMANDS[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
