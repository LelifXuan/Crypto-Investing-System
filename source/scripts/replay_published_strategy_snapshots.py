"""Replay a BTC derivatives direction flip against published compact snapshots.

Input must be a compact verification DB, not a copy of the full runtime DB.
Old snapshots without asset ownership are explicitly restamped under today's
resolver contract; the stored historical decision is never modified.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from app.services.cross_page_consistency import (
    apply_check_to_monitoring_summary,
    compare_published_conclusions,
)
from app.services.strategy_unified.direction_resolution import (
    DirectionResolutionEngine,
    ModuleSignal,
)
from app.services.strategy_unified.opportunity_scanner import _extract_scan_item

SYMBOLS = ("btc", "eth", "bnb", "hype", "okb")
SIGNAL_FIELDS = set(ModuleSignal.__dataclass_fields__)
DECISION_FIELDS = (
    "strategic_direction",
    "tactical_direction",
    "execution_direction",
    "permission",
    "position_cap",
    "trade_plan_inputs",
)


def _row(db: sqlite3.Connection, key: str) -> tuple[dict, str]:
    row = db.execute(
        "SELECT payload_json, snapshot_at FROM page_snapshot_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        raise AssertionError(f"Published row missing: {key}")
    return json.loads(row[0]), row[1]


def _signal(raw: dict, target: str) -> ModuleSignal:
    signal = ModuleSignal(**{key: value for key, value in raw.items() if key in SIGNAL_FIELDS})
    if signal.module == "derivatives":
        # The historical rows predate explicit asset_scope. Reapply the
        # production ownership policy rather than trusting the old omission.
        signal = replace(
            signal,
            instrument_id="btc-usdt-perp",
            asset_scope="exact" if target == "btc-usdt-perp" else "proxy",
        )
    elif signal.module == "macro":
        signal = replace(signal, instrument_id="", asset_scope="global")
    else:
        signal = replace(signal, instrument_id=target, asset_scope="exact")
    return signal


def replay(db_path: Path) -> dict:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    report: dict = {"database": str(db_path), "assets": {}}
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
        btc, _ = _row(db, "strategy_unified:btc-usdt-perp:v3")
        derivatives = [
            item for item in btc["signal_coverage"] if item.get("module") == "derivatives"
        ]
        if not any(item.get("direction") == "LONG" for item in derivatives):
            raise AssertionError("Real BTC snapshot has no bullish derivatives signal to flip")
        for symbol in SYMBOLS:
            target = f"{symbol}-usdt-perp"
            unified, unified_at = _row(db, f"strategy_unified:{target}:v3")
            ordinary = [
                _signal(item, target)
                for item in unified["signal_coverage"]
                if item.get("module") != "derivatives"
                and all(key in item for key in ("module", "signal_role", "action_effect"))
            ]
            original_derivatives = [_signal(item, target) for item in derivatives]
            flipped_derivatives = [
                replace(item, direction="SHORT", score=100 - item.score)
                if item.direction == "LONG"
                else item
                for item in original_derivatives
            ]
            resolver = DirectionResolutionEngine()
            bullish = resolver.resolve(
                signals=[*ordinary, *original_derivatives], target_instrument_id=target
            ).as_dict()
            bearish = resolver.resolve(
                signals=[*ordinary, *flipped_derivatives], target_instrument_id=target
            ).as_dict()
            if symbol != "btc":
                for field in DECISION_FIELDS:
                    assert bullish[field] == bearish[field], (target, field)
            else:
                assert any(item.direction == "SHORT" for item in flipped_derivatives)

            # Matrix cells must identify the same published unified payload
            # opened by detail. Monitoring's read-time canonical projection
            # must carry that identity too, even if its own cache is older.
            matrix = {
                tf: _extract_scan_item(unified, target, symbol.upper(), tf)
                for tf in ("1w", "1d", "4h")
            }
            assert all(
                item.source_snapshot_key == unified["snapshot_key"] for item in matrix.values()
            )
            monitor, monitor_at = _row(db, f"monitoring_dashboard:{target}:1d:v3")
            summary = monitor["terminal_summary"]
            check = compare_published_conclusions(
                summary,
                unified,
                instrument_id=target,
                timeframe="1d",
                monitoring_snapshot_at=monitor_at,
                strategy_snapshot_at=unified_at,
                monitoring_cache_state="fresh",
                strategy_cache_state="fresh",
            )
            projected = apply_check_to_monitoring_summary(summary, check, unified)
            canonical_id = projected["decision_brief"]["source_alignment"][
                "canonical_strategy_snapshot_id"
            ]
            assert canonical_id == unified["snapshot_key"]
            report["assets"][symbol] = {
                "published_snapshot_key": unified["snapshot_key"],
                "matrix_snapshot_keys": {
                    tf: item.source_snapshot_key for tf, item in matrix.items()
                },
                "monitoring_canonical_snapshot_key": canonical_id,
                "monitoring_cross_check": check["status"],
                "derivatives_card_before": next(
                    card["direction"]
                    for card in bullish["operation_cards"]
                    if card["key"] == "derivatives"
                ),
                "derivatives_card_after": next(
                    card["direction"]
                    for card in bearish["operation_cards"]
                    if card["key"] == "derivatives"
                ),
                "decision_invariant": all(
                    bullish[field] == bearish[field] for field in DECISION_FIELDS
                ),
            }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
