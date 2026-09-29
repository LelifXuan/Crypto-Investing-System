"""P0-QNT-001 cross-asset signal isolation invariants.

INV-001 — a BTC-specific exact signal cannot directly change a non-BTC
strategy direction. These tests drive the production ownership-stamping path
(``UnifiedDataService._signals_from_dimension``) and the resolver eligibility
gate with strongly bullish vs strongly bearish BTC derivatives features, and
assert non-BTC strategies are invariant in direction, plan inputs, permission
and key levels — while BTC itself still responds (positive control).
"""

from __future__ import annotations

from types import SimpleNamespace

BTC = "btc-usdt-perp"
NON_BTC_TARGETS = ("eth-usdt-perp", "bnb-usdt-perp", "hype-usdt-perp", "okb-usdt-perp")

BULLISH_FEATURES = {
    "snapshot_state": "live",
    "funding_state": "neutral",
    "oi_state": "buildup_long",
    "basis_state": "basis_rising",
    "skew_state": "call_skew_high",
    "call_wall_strike": 68000.0,
    "put_wall_strike": 60000.0,
    "max_pain_strike": 64000.0,
    "key_levels_axis": {"call_wall": 68000, "put_wall": 60000, "max_pain": 64000},
    "data_timestamp": "2026-09-30T00:00:00Z",
}
BEARISH_FEATURES = {
    **BULLISH_FEATURES,
    "oi_state": "buildup_short",
    "basis_state": "basis_falling",
    "skew_state": "put_skew_high",
}

BTC_WALL_LEVELS = {68000.0, 60000.0, 64000.0}


def _derivatives_signals(target: str, features: dict) -> list:
    from app.services.strategy_unified.derivatives_regime import DerivativesRegimeEngine
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    context = SimpleNamespace(
        derivatives_features=features,
        cache_meta={"cache_state": "fresh"},
    )
    dimension = DerivativesRegimeEngine().compute({"4h": context})
    service = UnifiedStrategyService(repository=None)
    return service._signals_from_dimension("derivatives_regime", dimension, target)


def _own_structure_signals(instrument_id: str) -> list:
    from app.services.strategy_unified.direction_resolution import ModuleSignal

    return [
        ModuleSignal(
            module="price_structure",
            indicator_key="daily_structure",
            horizon="tactical",
            window="1d",
            direction="LONG",
            signal_role="structure",
            action_effect="support",
            score=74,
            confidence=82,
            freshness="fresh",
            reason="daily structure is bullish",
            instrument_id=instrument_id,
            asset_scope="exact",
        ),
        ModuleSignal(
            module="macro",
            indicator_key="risk_appetite",
            horizon="strategic",
            window="1w",
            direction="NEUTRAL",
            signal_role="macro_pressure",
            action_effect="observe",
            score=50,
            confidence=50,
            freshness="fresh",
            reason="macro neutral",
            instrument_id="",
            asset_scope="global",
        ),
    ]


def _outcome(signals: list, target: str) -> dict:
    from app.services.strategy_unified.direction_resolution import DirectionResolutionEngine

    result = DirectionResolutionEngine().resolve(
        signals=signals, target_instrument_id=target
    )
    payload = result.as_dict()
    btc_levels = [
        level
        for card in payload["operation_cards"]
        for level in card["key_levels"].values()
        if level in BTC_WALL_LEVELS
    ]
    return {
        "strategic": payload["strategic_direction"],
        "tactical": payload["tactical_direction"],
        "unified_code": payload["unified_code"],
        "position_cap": payload["position_cap"],
        "permission": payload["permission"],
        "trade_plan_inputs": payload["trade_plan_inputs"],
        "conflict_types": sorted(c["conflict_type"] for c in payload["conflicts"]),
        "derivatives_card": next(
            (card for card in payload["operation_cards"] if card["key"] == "derivatives"),
            None,
        ),
        "btc_levels_leaked": btc_levels,
    }


def test_btc_derivatives_can_affect_btc_strategy() -> None:
    """Positive control: the isolation gate must not kill the BTC pathway."""
    bull = _outcome(
        [*_derivatives_signals(BTC, BULLISH_FEATURES), *_own_structure_signals(BTC)],
        BTC,
    )
    bear = _outcome(
        [*_derivatives_signals(BTC, BEARISH_FEATURES), *_own_structure_signals(BTC)],
        BTC,
    )
    assert bull["tactical"] == "LONG", bull
    assert bear["tactical"] == "SHORT", bear
    assert bull["derivatives_card"] and bull["derivatives_card"]["direction"] == "LONG"
    assert bear["derivatives_card"] and bear["derivatives_card"]["direction"] == "SHORT"
    # Exact ownership means no isolation record for the matching asset.
    assert "cross_asset_signal_isolated" not in bull["conflict_types"]
    assert "cross_asset_signal_isolated" not in bear["conflict_types"]


def test_btc_derivatives_cannot_change_eth_direction() -> None:
    _assert_non_btc_invariant("eth-usdt-perp")


def test_btc_derivatives_cannot_change_bnb_direction() -> None:
    _assert_non_btc_invariant("bnb-usdt-perp")


def test_btc_derivatives_cannot_change_hype_direction() -> None:
    _assert_non_btc_invariant("hype-usdt-perp")


def test_btc_derivatives_cannot_change_okb_direction() -> None:
    _assert_non_btc_invariant("okb-usdt-perp")


def _assert_non_btc_invariant(target: str) -> None:
    baseline = _outcome(_own_structure_signals(target), target)
    bull = _outcome(
        [*_derivatives_signals(target, BULLISH_FEATURES), *_own_structure_signals(target)],
        target,
    )
    bear = _outcome(
        [*_derivatives_signals(target, BEARISH_FEATURES), *_own_structure_signals(target)],
        target,
    )
    for scenario in (bull, bear):
        assert scenario["strategic"] == baseline["strategic"], (target, scenario)
        assert scenario["tactical"] == baseline["tactical"], (target, scenario)
        assert scenario["unified_code"] == baseline["unified_code"], (target, scenario)
        assert scenario["position_cap"] == baseline["position_cap"], (target, scenario)
        assert scenario["permission"] == baseline["permission"], (target, scenario)
        assert scenario["trade_plan_inputs"] == baseline["trade_plan_inputs"], (target, scenario)
        assert scenario["btc_levels_leaked"] == [], (target, scenario)
        assert "cross_asset_signal_isolated" in scenario["conflict_types"], (target, scenario)
    # The BTC flip itself must not matter at all: bull == bear for the target.
    for key in ("strategic", "tactical", "unified_code", "position_cap", "permission"):
        assert bull[key] == bear[key], (target, key, bull[key], bear[key])
    # Proxy derivatives remain visible, but only as explicitly labeled context.
    assert bull["derivatives_card"]["direction"] == "NEUTRAL"
    assert "BTC 市场代理上下文" in bull["derivatives_card"]["title"]


def test_exact_scope_mismatch_is_isolated() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    btc_only = ModuleSignal(
        module="derivatives",
        indicator_key="open_interest",
        horizon="tactical",
        window="4h",
        direction="LONG",
        signal_role="derivatives_confirmation",
        action_effect="confirm",
        score=90,
        confidence=95,
        freshness="fresh",
        reason="strong BTC OI confirmation",
        instrument_id=BTC,
        asset_scope="exact",
    )
    result = DirectionResolutionEngine().resolve(
        signals=[btc_only], target_instrument_id="eth-usdt-perp"
    )
    assert result.tactical_direction == "NEUTRAL"
    assert result.position_cap == "observe"
    assert any(c.conflict_type == "cross_asset_signal_isolated" for c in result.conflicts)
    # The isolated signal must not inject its key levels into any card.
    assert all(
        level not in BTC_WALL_LEVELS
        for card in result.operation_cards
        for level in card.key_levels.values()
    )


def test_unknown_scope_fails_closed() -> None:
    """No dangerous default: an undeclared scope never votes on direction."""
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    undeclared = ModuleSignal(
        module="derivatives",
        indicator_key="open_interest",
        horizon="tactical",
        window="4h",
        direction="LONG",
        signal_role="derivatives_confirmation",
        action_effect="confirm",
        score=90,
        confidence=95,
        freshness="fresh",
        reason="ownership not declared",
    )
    assert undeclared.normalized().asset_scope == "unknown"
    result = DirectionResolutionEngine().resolve(
        signals=[undeclared], target_instrument_id=BTC
    )
    assert result.tactical_direction == "NEUTRAL"
    assert result.position_cap == "observe"
    assert any(c.conflict_type == "cross_asset_signal_isolated" for c in result.conflicts)


def test_module_signals_default_to_unknown_scope() -> None:
    """Guard against reintroducing an implicit asset lens default."""
    from app.services.strategy_unified.direction_resolution import ModuleSignal

    signal = ModuleSignal(
        module="derivatives",
        indicator_key="open_interest",
        horizon="tactical",
        window="4h",
        direction="LONG",
        signal_role="derivatives_confirmation",
        action_effect="confirm",
    )
    assert signal.asset_lens == ""
    assert signal.instrument_id == ""
    assert signal.asset_scope == "unknown"
