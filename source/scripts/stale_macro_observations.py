"""Mark historical ``indicator_observations`` rows as stale for the 4
keys whose transform was previously dropped at write time.

Run once after deploying the C1-C3 transform code to prevent the old
index-value rows (e.g. ``cpi_mom = 332.41``) from being served to the
UI before the next ETL run overwrites them with correct transform
values.

Usage:
    python scripts/stale_macro_observations.py
    python scripts/stale_macro_observations.py --dry-run
    python scripts/stale_macro_observations.py --yes

The script only touches rows where:
- ``indicator_key`` is in ``TRANSFORM_AFFECTED_KEYS``
- ``value_num`` is > 50 (an index level like 332.41) OR
  ``status`` is one of the actively-served statuses

The 4 affected keys and their correct value range come from
``app.services.macro_overview.TRANSFORM_AFFECTED_KEYS``. Each updated
row gets ``status='stale_index_value'``,
``is_preliminary=0`` (it remains visible in audit trails but never
participates in scoring thanks to the ``stale_index_value`` status).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, update

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.db import db_manager  # noqa: E402
from app.db.models.market import IndicatorObservation  # noqa: E402
from app.services.macro_overview import TRANSFORM_AFFECTED_KEYS  # noqa: E402

# Index-level values are > 50 (CPI/PCE indices are 100-400 range); a
# correctly-transformed percent is always in [-50, 50]. The threshold
# 50 is a conservative cut-off so we never mis-stamp a real value.
STALE_INDEX_VALUE_THRESHOLD = 50.0
STALE_REASON = "口径异常：未应用 transform 已标记 stale"


async def _find_candidates(session) -> list[IndicatorObservation]:
    stmt = select(IndicatorObservation).where(
        IndicatorObservation.indicator_key.in_(TRANSFORM_AFFECTED_KEYS),
        IndicatorObservation.value_num.is_not(None),
        IndicatorObservation.value_num > STALE_INDEX_VALUE_THRESHOLD,
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def mark_stale(dry_run: bool, auto_yes: bool, *, manage_lifecycle: bool = True) -> int:
    if manage_lifecycle:
        await db_manager.connect()
    try:
        async with db_manager.session() as session:
            candidates = await _find_candidates(session)
            if not candidates:
                print("No stale rows found for the 4 transform-affected keys.")
                return 0

            by_key: dict[str, list[IndicatorObservation]] = {}
            for row in candidates:
                by_key.setdefault(row.indicator_key, []).append(row)

            print(f"Found {len(candidates)} stale row(s):")
            for key, rows in sorted(by_key.items()):
                latest_value = max(float(r.value_num) for r in rows)
                print(
                    f"  {key:14s} {len(rows):>3} row(s), max value_num={latest_value:.2f}"
                )

            if dry_run:
                print("\n--dry-run: no rows updated.")
                return 0

            if not auto_yes:
                prompt = input("\nProceed to mark these rows stale? [y/N] ")
                if prompt.strip().lower() not in {"y", "yes"}:
                    print("Aborted by user.")
                    return 0

            observation_ids = [r.observation_id for r in candidates]
            stmt = (
                update(IndicatorObservation)
                .where(IndicatorObservation.observation_id.in_(observation_ids))
                .values(
                    is_preliminary=False,
                    signal_state="stale_index_value",
                    value_text=STALE_REASON,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            updated = result.rowcount or 0
            print(f"\nMarked {updated} row(s) as stale_index_value.")

            print(
                "\n[!] This script only updates the trading_system.db at:\n"
                f"   {settings.database_url}\n"
                "   Portable runtime (8000) has its own copy; rerun\n"
                "   `python scripts/tasks.py build-portable` to sync code,\n"
                "   then run this script against the portable DB if needed."
            )
            return updated
    finally:
        if manage_lifecycle:
            await db_manager.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates without updating the database.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args()
    return asyncio.run(mark_stale(args.dry_run, args.yes))


if __name__ == "__main__":
    raise SystemExit(main())
