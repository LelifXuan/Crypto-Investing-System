from __future__ import annotations


def test_macro_long_price_short_resolves_to_long_term_watch_short_tactical() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    result = DirectionResolutionEngine().resolve(
        signals=[
            ModuleSignal(
                module="macro",
                indicator_key="risk_appetite",
                horizon="strategic",
                window="1w",
                direction="LONG",
                signal_role="macro_pressure",
                action_effect="support",
                score=72,
                confidence=75,
                freshness="fresh",
                reason="macro supports risk appetite",
            ),
            ModuleSignal(
                module="price_structure",
                indicator_key="daily_structure",
                horizon="tactical",
                window="1d/4h",
                direction="SHORT",
                signal_role="structure",
                action_effect="support",
                score=74,
                confidence=82,
                freshness="fresh",
                reason="daily and 4h structure are bearish",
            ),
        ],
        next_check="next_4h_close",
    )

    assert result.unified_code == "STRATEGIC_LONG_TACTICAL_SHORT"
    assert result.position_cap == "reduced"
    assert result.permission == "conditional"
    assert any(c.conflict_type == "cross_horizon_direction_conflict" for c in result.conflicts)
    assert "operation_bias" not in str(result.as_dict())
    assert "regime_key" not in str(result.as_dict())


def test_derivatives_funding_hot_and_option_walls_do_not_become_direction() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        derivatives_subsignals_from_features,
    )

    signals = derivatives_subsignals_from_features(
        {
            "funding_state": "positive_hot",
            "key_levels_axis": {"call_wall": 68000, "put_wall": 60000, "max_pain": 64000},
        }
    )

    funding = next(item for item in signals if item.indicator_key == "funding_rate")
    walls = [
        item
        for item in signals
        if item.indicator_key in {"call_wall", "put_wall", "max_pain"}
    ]
    assert funding.direction == "NEUTRAL"
    assert funding.action_effect == "downgrade"
    assert all(item.direction == "NEUTRAL" and item.action_effect == "level_only" for item in walls)

    result = DirectionResolutionEngine().resolve(signals=signals)
    derivatives_card = next(card for card in result.operation_cards if card.key == "derivatives")
    assert derivatives_card.direction == "NEUTRAL"
    assert derivatives_card.action_effect == "downgrade"
    assert result.unified_code == "RANGE_NO_EDGE"


def test_execution_signal_cannot_override_tactical_short() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    result = DirectionResolutionEngine().resolve(
        signals=[
            ModuleSignal(
                module="price_structure",
                indicator_key="daily_structure",
                horizon="tactical",
                window="1d",
                direction="SHORT",
                signal_role="structure",
                action_effect="support",
                score=78,
                confidence=80,
                freshness="fresh",
                reason="daily structure is bearish",
            ),
            ModuleSignal(
                module="price_structure",
                indicator_key="h1_trigger",
                horizon="execution",
                window="1h",
                direction="LONG",
                signal_role="momentum",
                action_effect="confirm",
                score=80,
                confidence=82,
                freshness="fresh",
                reason="1h rebound trigger appeared",
            ),
        ]
    )

    assert result.tactical_direction == "SHORT"
    assert result.execution_direction == "WAIT_SHORT_TRIGGER"
    assert result.unified_code == "RANGE_NO_EDGE"
    assert any(
        "1h" in text.lower() or "lower timeframe" in text.lower()
        for text in result.blocked_actions
    )


def test_low_timeframe_signal_cannot_create_trade_direction_without_1d_4h() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    result = DirectionResolutionEngine().resolve(
        signals=[
            ModuleSignal(
                module="price_structure",
                indicator_key="h1_trigger",
                horizon="execution",
                window="1h",
                direction="LONG",
                signal_role="momentum",
                action_effect="confirm",
                score=90,
                confidence=90,
                freshness="fresh",
            )
        ]
    )

    assert result.tactical_direction == "NEUTRAL"
    assert result.execution_direction == "WAIT"
    assert result.position_cap == "observe"


def test_missing_onchain_degrades_confidence_without_blocking_tactical_plan() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    result = DirectionResolutionEngine().resolve(
        signals=[
            ModuleSignal(
                module="price_structure",
                indicator_key="daily_structure",
                horizon="tactical",
                window="1d",
                direction="SHORT",
                signal_role="structure",
                action_effect="support",
                score=72,
                confidence=76,
                freshness="fresh",
                reason="daily structure is bearish",
            ),
            ModuleSignal(
                module="onchain",
                indicator_key="onchain_observations",
                horizon="strategic",
                window="1d",
                direction="NEUTRAL",
                signal_role="data_quality",
                action_effect="observe",
                score=0,
                confidence=0,
                freshness="missing",
                reason="onchain data is not available",
            ),
        ]
    )

    assert result.permission != "no_trade"
    assert result.position_cap == "standard"
    onchain_card = next(card for card in result.operation_cards if card.key == "onchain")
    assert onchain_card.confidence == 0
    assert "waiting" in onchain_card.next_check.lower() or "data" in onchain_card.next_check.lower()


def test_data_quality_blocker_forces_no_trade() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
    )

    result = DirectionResolutionEngine().resolve(
        signals=[
            ModuleSignal(
                module="data",
                indicator_key="core_cycles",
                horizon="risk_filter",
                window="global",
                direction="NEUTRAL",
                signal_role="data_quality",
                action_effect="block",
                score=0,
                confidence=0,
                freshness="missing",
                reason="core timeframe data missing",
            )
        ]
    )

    assert result.permission == "no_trade"
    assert result.position_cap == "no_trade"
    assert result.unified_code == "DATA_DEGRADED"


def test_expired_signal_contributes_zero_and_is_reported_excluded() -> None:
    from app.services.strategy_unified.direction_resolution import (
        DirectionResolutionEngine,
        ModuleSignal,
        effective_weight,
    )

    expired = ModuleSignal(
        module="technical",
        indicator_key="ema_adx_trend",
        horizon="tactical",
        window="4h",
        direction="LONG",
        signal_role="trend",
        action_effect="support",
        score=90,
        confidence=95,
        freshness="expired",
    )

    result = DirectionResolutionEngine().resolve(signals=[expired])

    assert effective_weight(expired.normalized()) == 0
    assert expired.as_dict()["usage_status"] == "excluded"
    assert result.tactical_direction == "NEUTRAL"


def test_actual_price_oi_states_produce_confirmation_without_overwrite() -> None:
    from app.services.strategy_unified.direction_resolution import (
        derivatives_subsignals_from_features,
    )

    signals = derivatives_subsignals_from_features(
        {
            "funding_state": "positive_hot",
            "oi_state": "price_down_oi_up",
            "basis_state": "basis_rising",
        }
    )

    by_key = {item.indicator_key: item for item in signals}
    assert by_key["funding_rate"].direction == "NEUTRAL"
    assert by_key["open_interest"].direction == "SHORT"
    assert by_key["basis"].direction == "LONG"
