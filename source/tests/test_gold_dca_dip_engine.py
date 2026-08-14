from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.gold_dca_dip import (
    GoldExecutionComposer,
    GoldExecutionState,
    GoldSettings,
    IndicatorSnapshot,
    QuoteSnapshot,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _quote(now: datetime | None = None, price: float = 4400) -> QuoteSnapshot:
    return QuoteSnapshot(price=price, updated_at=now or _now())


def _settings(**overrides) -> GoldSettings:
    payload = {
        "daily_dca_amount": 100,
        "dip_add_amount": 500,
        "available_cash": 2000,
        "cooldown_days": 7,
        "quote_max_age_seconds": 900,
    }
    payload.update(overrides)
    return GoldSettings(**payload)


def _oversold_indicators() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        close=4200,
        rsi_14=28,
        ema_20=4330,
        ema_50=4420,
        ema_200=4500,
        percent_b=-0.05,
        cci_20=-165,
        atr_14=120,
        natr_14=0.028,
        return_7d=-0.04,
        return_14d=-0.06,
        drawdown_from_30d_high=-0.07,
        drawdown_from_60d_high=-0.09,
        close_vs_ema20_pct=-0.03,
        close_vs_ema50_pct=-0.05,
    )


def test_daily_dca_executes_without_waiting_for_technical_signals() -> None:
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(),
        now=_now(),
        settings=_settings(),
        state=GoldExecutionState(),
        indicators=None,
    ).to_dict()

    assert plan["daily_dca"]["status"] == "execute"
    assert plan["daily_dca"]["amount"] == 100
    assert plan["dip_add"]["status"] == "insufficient_data"
    assert plan["execution"]["action"] == "daily_dca_only"
    assert plan["execution"]["total_amount"] == 100


def test_dip_add_triggers_fixed_extra_amount_on_daily_oversold_cluster() -> None:
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(price=4000),
        now=_now(),
        settings=_settings(dip_add_amount=600),
        state=GoldExecutionState(),
        indicators=_oversold_indicators(),
    ).to_dict()

    assert plan["dip_add"]["status"] == "triggered"
    assert plan["dip_add"]["amount"] == 600
    assert plan["execution"]["action"] == "daily_dca_plus_dip_add"
    assert plan["execution"]["base_dca_amount"] == 100
    assert plan["execution"]["dip_add_amount"] == 600
    assert plan["execution"]["total_amount"] == 700
    assert "倍增" not in str(plan)


def test_execution_plan_returns_formula_and_indicator_cards() -> None:
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(price=4000),
        now=_now(),
        settings=_settings(),
        state=GoldExecutionState(),
        indicators=_oversold_indicators(),
    ).to_dict()

    diagnostics = plan["diagnostics"]
    assert diagnostics["strategy_formula"] == {
        "base": "x",
        "dip": "n × x",
        "total_when_triggered": "x + n × x",
    }
    assert len(diagnostics["core_indicator_cards"]) == 8
    assert len(diagnostics["derived_indicator_cards"]) == 6
    core_labels = {item["label"] for item in diagnostics["core_indicator_cards"]}
    derived_labels = {item["label"] for item in diagnostics["derived_indicator_cards"]}
    assert core_labels >= {"RSI14", "EMA20", "BOLL 位置"}
    assert derived_labels >= {"7 日变化", "30 日高点回撤", "相对 EMA20"}


def test_indicator_cards_degrade_when_indicators_missing() -> None:
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(),
        now=_now(),
        settings=_settings(),
        state=GoldExecutionState(),
        indicators=None,
    ).to_dict()

    cards = (
        plan["diagnostics"]["core_indicator_cards"]
        + plan["diagnostics"]["derived_indicator_cards"]
    )
    assert len(plan["diagnostics"]["core_indicator_cards"]) == 8
    assert len(plan["diagnostics"]["derived_indicator_cards"]) == 6
    assert {item["status"] for item in cards} == {"数据不足"}


def test_dip_add_does_not_repeat_during_cooldown_or_same_cycle() -> None:
    now = _now()
    state = GoldExecutionState(
        last_dip_add_date=now.date() - timedelta(days=2),
        last_dip_cycle_id="2026-06-08-rsi25",
    )
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(now=now),
        now=now,
        settings=_settings(),
        state=state,
        indicators=_oversold_indicators(),
    ).to_dict()

    assert plan["dip_add"]["status"] == "cooldown"
    assert plan["execution"]["dip_add_amount"] == 0
    assert plan["execution"]["action"] == "daily_dca_only"


def test_stale_quote_forces_manual_check_without_execution_amounts() -> None:
    now = _now()
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(now=now - timedelta(hours=2)),
        now=now,
        settings=_settings(quote_max_age_seconds=900),
        state=GoldExecutionState(),
        indicators=_oversold_indicators(),
    ).to_dict()

    assert plan["daily_dca"]["status"] == "stale_quote"
    assert plan["dip_add"]["status"] == "stale_quote"
    assert plan["execution"]["action"] == "manual_check"
    assert plan["execution"]["total_amount"] == 0


def test_execution_plan_does_not_expose_forbidden_trading_actions() -> None:
    plan = GoldExecutionComposer().compose(
        symbol="XAUT_USDT",
        quote=_quote(),
        now=_now(),
        settings=_settings(),
        state=GoldExecutionState(),
        indicators=_oversold_indicators(),
    ).to_dict()

    rendered = str(plan)
    forbidden = {
        "sell",
        "trim",
        "reduce",
        "stop_loss",
        "take_profit",
        "做多",
        "做空",
        "开仓",
        "止损",
        "止盈",
        "追突破",
        "减仓",
        "卖出",
        "马丁格尔",
        "倍增加仓",
        "榛",
        "鎶",
        "鍏",
        "姣",
        "鍊",
    }
    for token in forbidden:
        assert token not in rendered


from app.services.gold_dca_dip import _bias_for_indicator


def test_bias_for_indicator_none_returns_missing():
    assert _bias_for_indicator("rsi_14", None, lower=30, upper=70) == "missing"


def test_bias_for_indicator_no_threshold_returns_neutral():
    # ema_20/ema_50/ema_200/atr_14/natr_14 没有 lower/upper
    assert _bias_for_indicator("ema_20", 4138.26) == "neutral"


def test_bias_for_indicator_rsi_bullish_low():
    # rsi_14 ∈ bullish_low: 越低越看多
    assert _bias_for_indicator("rsi_14", 20, lower=30, upper=70) == "strong_bullish"
    assert _bias_for_indicator("rsi_14", 28, lower=30, upper=70) == "bullish"
    assert _bias_for_indicator("rsi_14", 50, lower=30, upper=70) == "neutral"


def test_bias_for_indicator_rsi_bearish_high():
    assert _bias_for_indicator("rsi_14", 91, lower=30, upper=70) == "strong_bearish"
    assert _bias_for_indicator("rsi_14", 75, lower=30, upper=70) == "bearish"


def test_bias_for_indicator_drawdown_bearish_low():
    # drawdown_from_60d_high ∈ bearish_low: 越低越看空
    # value=-0.15 (15% 回撤), lower=-0.08 → strong_bearish
    assert _bias_for_indicator("drawdown_from_60d_high", -0.15, lower=-0.08) == "strong_bearish"
    assert _bias_for_indicator("drawdown_from_60d_high", -0.09, lower=-0.08) == "bearish"


def test_bias_for_indicator_unknown_key_no_threshold():
    # 未知 key + 无阈值 → neutral
    assert _bias_for_indicator("custom_unknown", 50.0) == "neutral"
