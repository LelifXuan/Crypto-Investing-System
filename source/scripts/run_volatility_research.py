from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import db_manager  # noqa: E402
from app.repositories.market_repository import MarketRepository  # noqa: E402
from app.services.volatility_research import VolatilityResearchService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one append-only BTC volatility research shadow snapshot."
    )
    parser.add_argument("--instrument", default="btc-usdt-perp")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--candle-limit", type=int, default=1200)
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    await db_manager.connect()
    try:
        await db_manager.ensure_schema_compatibility()
        async with db_manager.writer_session() as session:
            repository = MarketRepository(session)
            snapshot = await VolatilityResearchService(repository).build_shadow_snapshot(
                args.instrument,
                args.timeframe,
                candle_limit=args.candle_limit,
            )
            observations = await repository.list_volatility_feature_observations(
                snapshot.snapshot_id
            )
        print(
            json.dumps(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "formula_version": snapshot.formula_version,
                    "integration_status": snapshot.integration_status,
                    "timestamp_contract": snapshot.timestamp_contract_json,
                    "quality": snapshot.quality_json,
                    "features": {
                        item.feature_key: (
                            format(item.value_num, "f") if item.value_num is not None else None
                        )
                        for item in observations
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
