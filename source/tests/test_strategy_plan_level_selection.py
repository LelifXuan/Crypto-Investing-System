"""Guards for the strategy plan's price/level provenance (2026-09-22).

The AI strategy page could not show an executable setup: every plan came out
with an entry zone ~8% away from the market and was invalidated by the
live-price guard on every read. The audit traced it to two provenance bugs in
`StrategySnapshotBuilder.build`:

1. The price fell back to the *structure* bundle's candle tail when the
   analysis dependency was unavailable. ETH's 4h/1h bundles carried a 13-day-old
   "current price" (2493 against a 2744 market) from that fallback.
2. `support`/`resistance` fall back to the volume-profile value area (VAL/VAH) —
   a range measured over a long window. Used unbounded as the tactical entry, it
   produced ETH's short entry zone at 2531-2542 while the market traded at 2744.

These tests pin the fixes: the price never comes from another bundle's candles,
a structure level only selects the entry when the plan it implies is reachable
and not already dead, and the take-profit side is *not* bounded by that rule
(a distant target is the reward, not a defect).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.services.strategy_signal.snapshot_builder import (
    STOP_ATR_MULTIPLE,
    TP_ATR_MULTIPLE,
    select_entry_levels,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "app/services/strategy_signal/snapshot_builder.py"


def _source() -> str:
    return BUILDER.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry-level acceptance
# ---------------------------------------------------------------------------

# ETH 4h as measured on 2026-09-22: price 2739.32, atr_14 43.767, 4h VAH 2536.89.
ETH_ATR = 43.767
ETH_PRICE = 2739.32
ETH_MAX_DISTANCE = ETH_ATR * 3.0


def _eth_levels(**overrides) -> dict:
    """The level block ETH's 4h structure bundle actually publishes."""
    levels = {"val_price": 2385.15, "vah_price": 2536.89}
    levels.update(overrides)
    return levels


def _select(levels: dict, *, atr: float = ETH_ATR, price: float = ETH_PRICE):
    return select_entry_levels(levels, price=price, atr=atr, max_distance_atr=3.0)


def test_value_area_bounds_are_not_entry_levels_for_eth():
    """Both bounds sat ~8% below the market — the entry zone came from here."""
    support, resistance = _select(_eth_levels())

    assert support is None and resistance is None


def test_near_levels_are_kept():
    support, resistance = _select(_eth_levels(support_price=2700.0, resistance_price=2760.0))

    assert support == Decimal("2700.0")
    assert resistance == Decimal("2760.0")


def test_level_whose_plan_is_already_dead_is_rejected():
    """A stop the live price has already crossed is what the guard invalidates."""
    # SHORT: stop = level + 1.6 ATR = 2660 + 70.0 = 2730 < 2739.32 -> crossed.
    dead_level = 2660.0
    assert dead_level + ETH_ATR * STOP_ATR_MULTIPLE < ETH_PRICE
    _, resistance = _select(_eth_levels(resistance_price=dead_level))

    assert resistance is None


def test_level_whose_plan_survives_is_kept():
    alive_level = 2740.0
    assert alive_level + ETH_ATR * STOP_ATR_MULTIPLE > ETH_PRICE
    _, resistance = _select(_eth_levels(resistance_price=alive_level))

    assert resistance == Decimal("2740.0")


def test_structure_provided_stop_decides_the_dead_check():
    """When the structure names its own stop, that stop is what gets checked."""
    stopped, _ = _select(_eth_levels(support_price=2700.0, structure_invalid_long=2760.0))
    assert stopped is None, "a long whose structure stop is above the price is already dead"

    kept, _ = _select(_eth_levels(support_price=2700.0, structure_invalid_long=2600.0))
    assert kept == Decimal("2700.0")


def test_build_selects_entries_through_the_shared_rule():
    source = _source()
    build = source[
        source.index("    async def build("):source.index("    async def _stored_mark_price")
    ]

    assert "select_entry_levels(" in build


# ---------------------------------------------------------------------------
# Price provenance
# ---------------------------------------------------------------------------


def test_current_price_never_comes_from_the_structure_candle_tail():
    source = _source()
    price_block = source[
        source.index("candles = analysis_payload.get"):source.index("core = analysis_payload.get")
    ]

    assert 'structure_payload.get("candles")' in price_block, (
        "the structure series may still feed the informational candle count"
    )
    # The price fallback must not touch `candles`; it reads the analysis series
    # explicitly and then a stored mark.
    assert "analysis_candles = analysis_payload.get(\"candles\")" in price_block
    assert "_stored_mark_price" in price_block
    assert "_decimal(_field(candles[-1], \"close\"))" not in price_block


def test_price_fallback_uses_a_stored_mark_without_a_provider_call():
    source = _source()
    helper = source[source.index("async def _stored_mark_price"):source.index("def _levels(")]

    assert "prefer_live=False" in helper, (
        "one live fetch per timeframe per refresh cycle would multiply provider calls"
    )


# ---------------------------------------------------------------------------
# Targets stay structural
# ---------------------------------------------------------------------------


def test_take_profit_uses_the_raw_level_not_the_bounded_entry_copy():
    source = _source()

    assert "long_target = float(resistance_level)" in source
    assert "short_target = float(support_level)" in source
    # The tp1 defaults must read the raw target, otherwise the entry bound also
    # deletes the reward and the plan collapses onto the RR fallback.
    assert (
        '"long_tp1": long_target if long_target is not None else long_entry + tp_distance,'
        in source
    )
    assert (
        '"short_tp1": short_target if short_target is not None else short_entry - tp_distance,'
        in source
    )


def test_atr_fallback_target_satisfies_the_risk_reward_policy():
    """2.2 ATR against a 1.6 ATR stop is 1.375 — the 1.50 gate rejects it."""
    source = _source()

    assert "TP_ATR_MULTIPLE = 2.2" in source
    assert "tp_distance = max(TP_ATR_MULTIPLE, min_rr * STOP_ATR_MULTIPLE) * atr" in source
    assert max(TP_ATR_MULTIPLE, 1.5 * STOP_ATR_MULTIPLE) * 1.0 >= 1.5 * STOP_ATR_MULTIPLE
