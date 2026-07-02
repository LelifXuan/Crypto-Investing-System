from __future__ import annotations

import asyncio
import json

from app.services.btc_derivatives.sources.collector import LiveCollector


async def main() -> None:
    collector = LiveCollector()
    probe = await collector.probe()
    snapshot = await collector.snapshot(force=True)
    print(
        json.dumps(
            {
                "probe": probe.model_dump(mode="json"),
                "snapshot": {
                    "state": snapshot.snapshot_state,
                    "timestamp": snapshot.data_timestamp,
                    "primary_option_provider": snapshot.primary_option_provider,
                    "option_quotes": len(snapshot.options),
                    "perp_snapshots": len(snapshot.perps),
                    "history_points": len(snapshot.price_history),
                    "missing_reasons": snapshot.missing_reasons,
                },
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
