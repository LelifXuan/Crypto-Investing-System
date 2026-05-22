from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "trading_system.db"
SEED_DIR = ROOT / "app" / "assets" / "seed_cache"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export local macro observations into bundled seed cache."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    parser.add_argument("--out-dir", default=str(SEED_DIR), help="Output seed cache directory.")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = []
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT indicator_key, value_num, value_text, observation_ts, source_provider
                    FROM indicator_observations
                    WHERE category = 'macro'
                       OR source_provider IN ('fred', 'bls', 'bea', 'treasury')
                    ORDER BY observation_ts DESC
                    """
                ).fetchall()
            except sqlite3.Error:
                rows = []
        seen = set()
        for row in rows:
            key = row["indicator_key"]
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "indicator_id": key,
                    "value": row["value_num"],
                    "value_text": row["value_text"],
                    "latest_date": row["observation_ts"],
                    "source": row["source_provider"] or "local_export",
                    "status": "seed_cache",
                }
            )

    payload = {
        "version": "macro_seed_cache_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    (out_dir / "macro_observations_seed.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = {
        "version": "seed_manifest_v1",
        "generated_at": payload["generated_at"],
        "contains_real_observations": bool(items),
        "item_count": len(items),
        "files": ["macro_observations_seed.json", "macro_websearch_seed.json"],
    }
    (out_dir / "seed_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Exported {len(items)} macro seed observation(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
