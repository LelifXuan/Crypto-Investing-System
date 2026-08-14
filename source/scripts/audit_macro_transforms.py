"""Audit script for transform-only macro keys.

Walks ``app/monitoring/configs/macro_indicator_api_map.v1.json`` and,
for every key whose ``transform`` field is ``mom_pct`` or ``yoy_pct``,
asks the matching provider for a 14-point history and runs the
transform. The result is checked against a sanity band:

- ``yoy_pct``: (-20, 50)
- ``mom_pct``: (-5, 5)

Exit codes:
- 0: all transform-only keys pass the sanity check
- 1: at least one key produced a value outside the band, or the
     provider could not return enough history

Usage:
    python scripts/audit_macro_transforms.py
    python scripts/audit_macro_transforms.py --allow-network  # real fetch
    python scripts/audit_macro_transforms.py --json           # machine-readable

By default the script does NOT hit the network — it relies on the
caches that ``IndicatorMonitoringService`` and the providers maintain
locally. With ``--allow-network`` the script will issue live HTTP
calls when the cache is cold.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.db import db_manager  # noqa: E402
from app.services.macro import transforms  # noqa: E402
from app.services.macro.provider_registry import MacroProviderRegistry  # noqa: E402
from app.services.macro_overview import TRANSFORM_AFFECTED_KEYS  # noqa: E402

API_MAP_PATH = (
    ROOT / "app" / "monitoring" / "configs" / "macro_indicator_api_map.v1.json"
)
SANITY_BANDS = {
    "yoy_pct": (-20.0, 50.0),
    "mom_pct": (-5.0, 5.0),
}


def _load_api_map() -> dict[str, Any]:
    with API_MAP_PATH.open(encoding="utf-8") as fp:
        return json.load(fp)


def _is_transform_only(item: dict[str, Any]) -> bool:
    return item.get("transform") in {"mom_pct", "yoy_pct"}


def _resolve_primary_source(item: dict[str, Any]) -> tuple[str, str] | None:
    sources = item.get("sources") or []
    if not sources:
        return None
    primary = sources[0]
    return primary.get("source"), primary.get("symbol") or primary.get("series")


async def _audit_one(
    key: str, item: dict[str, Any], registry: MacroProviderRegistry
) -> dict[str, Any]:
    transform = item.get("transform")
    primary = _resolve_primary_source(item)
    if not primary:
        return {"key": key, "ok": False, "reason": "no primary source configured"}
    source_provider, series_symbol = primary
    provider = registry.resolve(
        source_provider=source_provider, source_kind="raw_series"
    )
    if provider is None:
        return {
            "key": key,
            "ok": False,
            "reason": f"provider '{source_provider}' not registered",
        }
    if not hasattr(provider, "fetch_history"):
        return {
            "key": key,
            "ok": False,
            "reason": f"provider '{source_provider}' does not implement fetch_history",
        }
    try:
        history = await provider.fetch_history(series_symbol, lookback_points=14)
    except Exception as exc:
        return {
            "key": key,
            "ok": False,
            "reason": f"fetch_history raised: {exc!r}",
        }
    points = [
        (p.observation_ts, p.value) for p in history if p.observation_ts is not None
    ]
    if transform == "yoy_pct":
        result = transforms.compute_yoy_pct(points)
    else:
        result = transforms.compute_mom_pct(points)
    if result is None:
        return {
            "key": key,
            "ok": False,
            "reason": f"transform {transform} returned None (history len={len(points)})",
        }
    value, _ = result
    low, high = SANITY_BANDS[transform]
    in_band = low < float(value) < high
    return {
        "key": key,
        "ok": in_band,
        "transform": transform,
        "value": float(value),
        "source": source_provider,
        "series": series_symbol,
        "history_len": len(points),
        "band": [low, high],
        "in_band": in_band,
        "auto_applied": key in TRANSFORM_AFFECTED_KEYS,
    }


async def audit(allow_network: bool, json_output: bool) -> int:
    api_map = _load_api_map()
    indicators = api_map.get("indicators", {})
    candidates = {
        key: item for key, item in indicators.items() if _is_transform_only(item)
    }
    if not json_output:
        print(f"Auditing {len(candidates)} transform-only macro key(s)...")
    registry = MacroProviderRegistry()
    await db_manager.connect()
    try:
        results: list[dict[str, Any]] = []
        for key, item in candidates.items():
            results.append(await _audit_one(key, item, registry))
    finally:
        await db_manager.disconnect()

    failed = [r for r in results if not r["ok"]]
    if json_output:
        payload = {
            "summary": {
                "total": len(results),
                "passed": len(results) - len(failed),
                "failed": len(failed),
            },
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "OK " if r["ok"] else "FAIL"
            if r.get("value") is not None:
                line = (
                    f"  {mark} {r['key']:14s} {r['transform']:7s} "
                    f"value={r['value']:+.2f} "
                    f"band={r['band']} "
                    f"history={r['history_len']:>2} "
                    f"src={r['source']}/{r['series']}"
                )
            else:
                line = f"  {mark} {r['key']:14s} reason: {r['reason']}"
            print(line)
        print(
            f"\n{len(results) - len(failed)} passed, {len(failed)} failed."
        )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Issue live HTTP calls when the provider cache is cold.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    args = parser.parse_args()
    return asyncio.run(audit(args.allow_network, args.json))


if __name__ == "__main__":
    raise SystemExit(main())
