#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REQUIREMENTS = {
    "1h": 720,
    "4h": 480,
    "1d": 420,
    "1w": 260,
    "30d": 180,
    "1m": 240,
    "5m": 240,
    "15m": 240,
}
LONG_REQUIREMENTS = {
    "1h": 1000,
    "4h": 900,
    "1d": 900,
    "1w": 520,
    "30d": 360,
    "1m": 1000,
    "5m": 1000,
    "15m": 1000,
}
TTL_CACHE_TABLES = ("page_snapshot_cache", "computed_dataset_cache")
LONG_TERM_TABLES = (
    "market_candles",
    "mark_prices",
    "strategy_decision",
    "signal_outcome",
    "translation_text_cache",
    "translation_cache",
)


def parse_env_urls(repo: Path) -> dict[str, str]:
    urls = {}
    for rel in (".env", ".env.example", "runtime/config/portable.env"):
        path = repo / rel
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                urls[rel] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return urls


def find_dbs(repo: Path) -> list[Path]:
    skip = {".venv", "dist", "node_modules", ".git", "__pycache__"}
    dbs = []
    for p in repo.rglob("*.db"):
        if any(s in p.relative_to(repo).parts for s in skip):
            continue
        dbs.append(p)
    return sorted(dbs)


def kline_coverage(conn, tables):
    if "market_candles" not in tables:
        return []
    rows = conn.execute("""
        select instrument_id, timeframe, source, count(*) as cnt, min(ts_open), max(ts_open)
        from market_candles
        group by instrument_id, timeframe, source
        order by instrument_id, timeframe, source
    """).fetchall()
    items = []
    for inst, tf, src, cnt, _min_ts, _max_ts in rows:
        def_need = DEFAULT_REQUIREMENTS.get(str(tf), 240)
        long_need = LONG_REQUIREMENTS.get(str(tf), def_need)
        issues = []
        if int(cnt) < def_need:
            issues.append("insufficient_default")
        if int(cnt) < long_need:
            issues.append("insufficient_long")
        if str(tf) == "30d" and int(cnt) < def_need:
            issues.append("history_limited")
        items.append(
            {
                "instrument_id": inst,
                "timeframe": tf,
                "source": src,
                "count": int(cnt),
                "default_required": def_need,
                "default_gap": max(0, def_need - int(cnt)),
                "coverage_pct": round(min(int(cnt) / max(def_need, 1), 1.0) * 100, 2),
                "issues": issues,
            }
        )
    return items


def summarize_db(repo, db_path, active_urls):
    item = {
        "path": str(db_path),
        "rel": str(db_path.relative_to(repo)) if db_path.is_relative_to(repo) else str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "referenced_by": [],
        "error": None,
    }
    resolved = str(db_path.resolve())
    for env_file, url in active_urls.items():
        parsed = None
        if url.startswith("sqlite+aiosqlite:///"):
            raw = url[len("sqlite+aiosqlite:///") :]
            p = Path(raw)
            parsed = str((repo / p).resolve()) if not p.is_absolute() else raw
        if parsed and parsed == resolved:
            item["referenced_by"].append(env_file)
    if not db_path.exists():
        return item
    try:
        c = sqlite3.connect(db_path)
        names = {row[0] for row in c.execute("select name from sqlite_master where type='table'")}
        item["tables"] = {
            t: int(c.execute(f"select count(*) from {t}").fetchone()[0])
            for t in sorted(names)
            if t in names
        }
        item["kline_coverage"] = kline_coverage(c, names)
        item["deficits"] = [r for r in item["kline_coverage"] if r["issues"]]
        now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        expired = 0
        for t in TTL_CACHE_TABLES:
            if t in names:
                try:
                    expired += int(
                        c.execute(
                            (
                                f"select count(*) from {t} "
                                "where expires_at is not null and expires_at < ?"
                            ),
                            (now,),
                        ).fetchone()[0]
                    )
                except Exception:
                    pass
        item["expired_cache_rows"] = expired
        item["recommendation"] = (
            "Run clean_workspace.py --clear-data to clear expired cache" if expired > 0 else None
        )
        c.close()
    except sqlite3.Error as e:
        item["error"] = str(e)
    return item


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=".")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--write-runtime-log", action="store_true")
    args = p.parse_args()
    repo = Path(args.repo).resolve()
    urls = parse_env_urls(repo)
    dbs = find_dbs(repo)
    for u in urls.values():
        if u.startswith("sqlite+aiosqlite:///"):
            raw = u[len("sqlite+aiosqlite:///") :]
            tp = Path(raw)
            if not tp.is_absolute():
                tp = (repo / tp).resolve()
            if tp not in dbs:
                dbs.append(tp)
    dbs = sorted(set(dbs))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "database_urls": urls,
        "databases": [summarize_db(repo, p, urls) for p in dbs],
    }
    if args.write_runtime_log:
        ld = repo / "runtime/logs"
        ld.mkdir(parents=True, exist_ok=True)
        (ld / "local_storage_audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== Database URLs ===")
        for k, v in urls.items():
            print(f"  {k}: {v}")
        print(f"\n=== Databases ({len(dbs)} found) ===")
        for db in report["databases"]:
            ref = ",".join(db.get("referenced_by", [])) or "none"
            print(f"\n{db['rel']} ({db['size_bytes']} bytes, referenced by: {ref})")
            if db.get("error"):
                print(f"  ERROR: {db['error']}")
                continue
            t = db.get("tables", {})
            print(
                "  market_candles="
                f"{t.get('market_candles', 0)} "
                f"cache_snapshot={t.get('page_snapshot_cache', 0)} "
                f"computed={t.get('computed_dataset_cache', 0)}"
            )
            deficits = db.get("deficits", [])
            print(
                f"  sample_deficits={len(deficits)} expired_cache={db.get('expired_cache_rows', 0)}"
            )
            for d in deficits[:20]:
                print(
                    f"    {d['instrument_id']}:{d['timeframe']} "
                    f"count={d['count']} gap={d['default_gap']} "
                    f"coverage={d['coverage_pct']}% issues={','.join(d['issues'])}"
                )
            if len(deficits) > 20:
                print(f"    ... {len(deficits) - 20} more")
            if db.get("recommendation"):
                print(f"  REC: {db['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
