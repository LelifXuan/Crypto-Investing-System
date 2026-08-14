"""Import a bundled 6-ETF daily-price CSV into the fund_history cache.

The CSV (e.g. ``HALO_6ETF_daily_prices_20210104_20260805.csv``) carries
per-symbol ``{code}_close`` and ``{code}_volume`` columns plus an ``all_ok``
flag. Each HALO ETF lists at a different date, so symbols are imported
independently: a row where a symbol's close is empty is simply skipped for
that symbol.

Merge semantics (identical to ``EtfHistoryService._merge_points``):
- Bars are keyed by ``trade_date``; importing the same CSV twice is
  idempotent (no duplicate points).
- A date that already exists in the cache keeps its cached bar — the CSV
  only carries close+volume, so it must NOT downgrade an existing bar's
  open/high/low. New dates get ``open/high/low = null``.
- ``coverage_start`` / ``coverage_end`` / ``last_updated`` are recomputed.

The raw CSV is archived to ``runtime/cache/fund_history/source/`` so the
import is reproducible without re-downloading the source file.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / "cache" / "fund_history"
SOURCE_DIR = CACHE_DIR / "source"

# The strategy universe is FIXED at 6 ETFs (spec 表1).
HALO_CODES: tuple[str, ...] = ("561560", "159930", "512400", "516950", "512660", "563010")

UTC = timezone.utc


def _read_csv(path: Path) -> dict[str, list[tuple[date, float, float | None]]]:
    """Parse the CSV into per-code (date, close, volume) rows.

    Returns ``{code: [(date, close, volume|None), ...]}`` sorted by date.
    Rows where the code's close is empty are skipped for that code.
    """
    per_code: dict[str, list[tuple[date, float, float | None]]] = {c: [] for c in HALO_CODES}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            day_raw = (row.get("date") or "").strip()
            if not day_raw:
                continue
            d = date.fromisoformat(day_raw[:10])
            for code in HALO_CODES:
                close_raw = (row.get(f"{code}_close") or "").strip()
                if not close_raw:
                    continue  # symbol not yet listed / data gap
                close = float(close_raw)
                vol_raw = (row.get(f"{code}_volume") or "").strip()
                volume = float(vol_raw) if vol_raw else None
                per_code[code].append((d, close, volume))
    for code in HALO_CODES:
        per_code[code].sort(key=lambda x: x[0])
    return per_code


def _import_code(code: str, rows: list[tuple[date, float, float | None]]) -> tuple[int, int]:
    """Merge ``rows`` into ``{code}.json``; returns (added, total)."""
    path = CACHE_DIR / f"{code}.json"
    existing: dict[str, object] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))

    by_date: dict[str, dict] = {p["date"]: p for p in existing.get("points", [])}
    added = 0
    for d, close, volume in rows:
        iso = d.isoformat()
        if iso in by_date:
            continue  # keep the cached bar (it has OHLC; CSV is close-only)
        by_date[iso] = {
            "date": iso,
            "open": None,
            "close": close,
            "high": None,
            "low": None,
            "volume": volume,
            "amount": None,
            "amplitude_pct": None,
        }
        added += 1

    points = sorted(by_date.values(), key=lambda p: p["date"])
    if not points:
        return 0, 0

    payload = {
        "code": code,
        "market": existing.get("market", "SH" if code.startswith(("5", "6")) else "SZ"),
        "secid": existing.get("secid", f"1.{code}" if code.startswith(("5", "6")) else f"0.{code}"),
        "name": existing.get("name"),
        "source": existing.get("source", "csv_import"),
        "coverage_start": points[0]["date"],
        "coverage_end": points[-1]["date"],
        "last_updated": datetime.now(tz=UTC).isoformat(),
        "points": points,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return added, len(points)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a bundled 6-ETF daily-price CSV into the fund_history cache."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the source CSV (date, {code}_close, {code}_volume, ...).",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}")
        return 2

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    archive = SOURCE_DIR / args.csv.name
    shutil.copy2(args.csv, archive)

    per_code = _read_csv(args.csv)
    total_added = 0
    for code in HALO_CODES:
        added, total = _import_code(code, per_code[code])
        total_added += added
        print(f"{code}: +{added} bars (cache total {total})")
    print(f"archive: {archive}")
    print(f"imported {total_added} new bar(s) across {len(HALO_CODES)} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
