from __future__ import annotations

from app.schemas.market import MonitoringDashboardRead
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.terminal_summary_engine import TerminalSummaryEngine


def test_terminal_summary_contains_required_contract() -> None:
    summary = TerminalSummaryEngine().build(
        macro_overview={
            "total_score": 43,
            "score_band": "温和偏紧",
            "data_completeness": {"effective_count": 37, "total_count": 41},
        },
        technical_observations=[
            {
                "indicator_key": "ema_20",
                "value_num": 100,
                "signal_state": "bearish",
                "signal_label": "EMA20压制",
            },
            {
                "indicator_key": "ema_50",
                "value_num": 105,
                "signal_state": "bearish",
                "signal_label": "EMA50压制",
            },
            {
                "indicator_key": "rsi_14",
                "value_num": 25,
                "signal_state": "risk_cold",
                "signal_label": "超卖修复",
            },
            {
                "indicator_key": "adx_14",
                "value_num": 29,
                "signal_state": "neutral",
                "signal_label": "趋势成形",
            },
        ],
    )

    assert set(
        [
            "regime",
            "bias",
            "confidence",
            "headline",
            "module_scores",
            "main_conflict",
            "strategy_implication",
            "watch_points",
            "bullish_reversal_conditions",
            "bearish_continuation_conditions",
            "evidence",
        ]
    ).issubset(summary)
    assert set(
        ["macro", "technical_trend", "momentum_volume", "volatility", "structure", "event_risk"]
    ).issubset(summary["module_scores"])
    assert summary["watch_points"]
    assert "开仓" not in summary["strategy_implication"]


def test_rsi_oversold_is_execution_risk_not_bullish() -> None:
    summary = TerminalSummaryEngine().build(
        technical_observations=[
            {
                "indicator_key": "rsi_14",
                "value_num": 24,
                "signal_state": "risk_cold",
                "signal_label": "超卖修复",
            },
        ],
    )

    momentum = summary["module_scores"]["momentum_volume"]
    assert momentum["impact"] != "bullish"
    assert momentum["evidence"][0]["impact"] == "execution_risk"


def test_volatility_does_not_become_directional() -> None:
    summary = TerminalSummaryEngine().build(
        technical_observations=[
            {
                "indicator_key": "bbands",
                "value_num": 100,
                "signal_state": "volatility_breakout_down",
                "tone": "event",
            },
            {
                "indicator_key": "adx_14",
                "value_num": 31,
                "signal_state": "neutral",
                "signal_label": "方向待确认",
            },
        ],
    )

    volatility = summary["module_scores"]["volatility"]
    assert volatility["impact"] in {"neutral", "execution_risk", "unknown"}
    assert volatility["impact"] not in {"bullish", "bearish"}


def test_macro_missing_data_degrades_confidence_without_zero_bearish() -> None:
    summary = TerminalSummaryEngine().build(
        macro_overview={
            "total_score": 50,
            "score_band": "宏观中性",
            "data_completeness": {"effective_count": 1, "total_count": 10},
        },
    )

    macro = summary["module_scores"]["macro"]
    assert macro["score"] == 50
    assert macro["confidence"] <= 0.42
    assert macro["impact"] == "neutral"


def test_monitoring_dashboard_schema_accepts_terminal_summary() -> None:
    summary = TerminalSummaryEngine().build()
    payload = MonitoringDashboardRead.model_validate(
        {
            "instrument_id": "btc-usdt-perp",
            "timeframe": "1d",
            "terminal_summary": summary,
            "status": "ready",
        }
    )

    assert payload.terminal_summary is not None
    assert payload.terminal_summary["module_scores"]["macro"]


def test_monitoring_service_builds_terminal_summary_from_partial_payload() -> None:
    summary = MonitoringDashboardService._terminal_summary_payload(
        None,
        None,
        [{"indicator_key": "ema_20", "signal_state": "bearish", "value_num": 100}],
    )

    assert summary["module_scores"]["technical_trend"]["score"] < 50
    assert summary["module_scores"]["macro"]["score"] == 50


def test_terminal_summary_detects_ema_bearish_stack_from_snapshot() -> None:
    summary = TerminalSummaryEngine().build(
        macro_overview={
            "total_score": 43,
            "score_band": "温和偏紧",
            "data_completeness": {"effective_count": 37, "total_count": 41},
        },
        technical_observations=[
            {"indicator_key": "ema_20", "value_num": 95, "value_json": {"close": 90}},
            {"indicator_key": "ema_50", "value_num": 100, "value_json": {"close": 90}},
            {"indicator_key": "ema_200", "value_num": 110, "value_json": {"close": 90}},
            {"indicator_key": "rsi_14", "value_num": 38},
            {"indicator_key": "macd_hist", "value_num": -4},
        ],
    )

    trend = summary["module_scores"]["technical_trend"]
    assert trend["score"] < 42
    assert trend["impact"] in {"bearish", "mild_bearish"}
    assert summary["regime"] != "中性震荡"


def test_terminal_summary_detects_ema_bullish_stack_from_snapshot() -> None:
    summary = TerminalSummaryEngine().build(
        technical_observations=[
            {"indicator_key": "ema_20", "value_num": 105, "value_json": {"close": 112}},
            {"indicator_key": "ema_50", "value_num": 100, "value_json": {"close": 112}},
            {"indicator_key": "ema_200", "value_num": 92, "value_json": {"close": 112}},
            {"indicator_key": "rsi_14", "value_num": 64},
        ],
    )

    trend = summary["module_scores"]["technical_trend"]
    assert trend["score"] > 58
    assert trend["impact"] in {"bullish", "mild_bullish"}


def test_terminal_summary_rebuild_ignores_cached_neutral_payload() -> None:
    cached = {
        "module_scores": {"technical_trend": {"score": 50, "state": "中性", "impact": "neutral"}}
    }
    summary = MonitoringDashboardService._terminal_summary_payload(
        cached,
        {"total_score": 43, "data_completeness": {"effective_count": 37, "total_count": 41}},
        [
            {"indicator_key": "ema_20", "value_num": 95, "value_json": {"close": 90}},
            {"indicator_key": "ema_50", "value_num": 100, "value_json": {"close": 90}},
            {"indicator_key": "ema_200", "value_num": 110, "value_json": {"close": 90}},
        ],
    )

    assert summary["module_scores"]["technical_trend"]["score"] < 42


def test_terminal_summary_uses_btc_daily_context_after_sharp_drop() -> None:
    summary = TerminalSummaryEngine().build(
        macro_overview={
            "total_score": 43,
            "score_band": "温和偏紧",
            "data_completeness": {"effective_count": 37, "total_count": 41},
        },
        technical_observations=[
            {
                "indicator_key": "ema_20",
                "value_num": 98000,
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "value_json": {
                    "close": 92000,
                    "previous_close": 96500,
                    "close_change_pct": -4.66,
                },
            },
            {"indicator_key": "ema_50", "value_num": 101000, "value_json": {"close": 92000}},
            {"indicator_key": "ema_200", "value_num": 108000, "value_json": {"close": 92000}},
            {"indicator_key": "vwap_50", "value_num": 97000, "value_json": {"close": 92000}},
            {"indicator_key": "rsi_14", "value_num": 31},
            {"indicator_key": "macd_hist", "value_num": -350},
            {"indicator_key": "adx_14", "value_num": 28},
            {"indicator_key": "plus_di", "value_num": 16},
            {"indicator_key": "minus_di", "value_num": 31},
        ],
    )

    joined_text = " ".join(
        [
            summary["headline"],
            summary["strategy_implication"],
            *summary["watch_points"],
        ]
    )
    assert "BTC 日线" in joined_text
    assert "刚经历急跌" in joined_text
    assert "低位追空" in joined_text
    assert "反弹" in joined_text
    assert "右侧开多" in joined_text
    assert summary["module_scores"]["technical_trend"]["score"] < 42


# ---------------------------------------------------------------------------
# decision_brief tests (V1.5)
# ---------------------------------------------------------------------------


def test_decision_brief_has_exactly_three_required_rows() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bearish", "state": "pressure"},
            "divergence_summary": {"overall": {"tone": "bearish"}},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "blocked",
                "strategy_permission": "等待确认",
                "strategy_bias": "bearish",
            }
        },
        timeframe_snapshots={
            "4h": {"bias": "neutral"},
            "1d": {"bias": "bearish"},
            "1w": {"bias": "bearish"},
        },
    )

    brief = summary["decision_brief"]
    assert brief["version"] == "monitoring_decision_brief_v1"
    assert [row["key"] for row in brief["rows"]] == [
        "market_situation",
        "trading_guidance",
        "risk_invalidation",
    ]
    assert [row["title"] for row in brief["rows"]] == [
        "市场情况",
        "交易指引",
        "风险点 / 失效条件",
    ]


def test_decision_brief_preserves_legacy_fields() -> None:
    summary = TerminalSummaryEngine().build(
        technical_observations=[{"indicator_key": "ema_20", "value_num": 100}],
    )
    legacy_keys = {
        "regime",
        "bias",
        "confidence",
        "headline",
        "module_scores",
        "main_conflict",
        "strategy_implication",
        "watch_points",
        "bullish_reversal_conditions",
        "bearish_continuation_conditions",
        "evidence",
    }
    assert legacy_keys.issubset(summary)
    assert "decision_brief" in summary


def test_decision_brief_marks_degraded_when_alerts_missing() -> None:
    summary = TerminalSummaryEngine().build(
        timeframe_snapshots={"4h": {"bias": "bearish"}, "1d": {"bias": "bearish"}},
    )
    alignment = summary["decision_brief"]["source_alignment"]
    assert alignment["consistency"] == "degraded"
    assert "alerts_bundle" in alignment["missing_sources"]
    assert "strategy_bundle" in alignment["missing_sources"]


def test_decision_brief_detects_cross_source_conflict() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bearish", "state": "pressure"},
            "divergence_summary": {"overall": {"tone": "bullish"}},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "ready",
                "strategy_bias": "bullish",
                "strategy_permission": "允许试探",
            }
        },
        timeframe_snapshots={
            "4h": {"bias": "bullish"},
            "1d": {"bias": "bearish"},
            "1w": {"bias": "bullish"},
        },
    )
    alignment = summary["decision_brief"]["source_alignment"]
    assert alignment["consistency"] == "conflict"
    assert any("方向证据冲突" in item for item in alignment["conflicts"])
    assert any("4h/1d/1w" in item for item in alignment["conflicts"])
    rows_by_key = {row["key"]: row for row in summary["decision_brief"]["rows"]}
    trading = rows_by_key["trading_guidance"]
    assert trading["tone"] == "warning"
    assert "等待确认" in trading["summary"] or "冲突" in trading["summary"]


def test_decision_brief_includes_strategy_gates_and_no_trade_reasons() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={"chip_structure": {"direction": "bearish"}},
        strategy_bundle={
            "decision": {
                "strategy_state": "blocked",
                "strategy_permission": "禁止追单",
                "strategy_bias": "bearish",
                "gates": ["OI 不足", "流动性不足"],
                "no_trade_reasons": ["合约准入未通过"],
            }
        },
        timeframe_snapshots={"4h": {"bias": "bearish"}, "1d": {"bias": "bearish"}},
    )
    rows_by_key = {row["key"]: row for row in summary["decision_brief"]["rows"]}
    trading = rows_by_key["trading_guidance"]
    joined = " ".join(trading["bullets"])
    assert "策略状态" in joined
    assert "禁止追单" in joined
    assert "OI 不足" in joined or "合约准入" in joined
    risk = rows_by_key["risk_invalidation"]
    risk_joined = " ".join(risk["bullets"])
    assert "策略门槛" in risk_joined or "不交易原因" in risk_joined
    market = rows_by_key["market_situation"]
    assert "alerts.chip_structure" in market["source_refs"]
    assert "strategy.decision" in trading["source_refs"]


def test_decision_brief_does_not_use_unconditional_trade_language() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bullish"},
            "divergence_summary": {"overall": {"tone": "bullish"}},
        },
        strategy_bundle={
            "decision": {
                "strategy_state": "ready",
                "strategy_bias": "bullish",
                "strategy_permission": "允许条件触发",
                "next_trigger": {"timeframe": "4h", "condition": "站稳 VWAP50"},
            }
        },
        timeframe_snapshots={
            "4h": {"bias": "bullish"},
            "1d": {"bias": "bullish"},
            "1w": {"bias": "bullish"},
        },
    )
    joined = " ".join(
        row["summary"] + " ".join(row["bullets"])
        for row in summary["decision_brief"]["rows"]
    )
    forbidden = ["现在开多", "现在开空", "立刻追多", "立刻追空", "无脑开多", "无脑开空"]
    for token in forbidden:
        assert token not in joined
    assert "确认" in joined or "等待" in joined or "允许" in joined


# ---------------------------------------------------------------------------
# Multi-period conflict matrix tests (V1.5 P3)
# ---------------------------------------------------------------------------


def test_decision_brief_matrix_has_six_rows_in_fixed_order() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bearish", "confidence_score": 0.7},
        },
        strategy_bundle={
            "decision": {
                "strategy_bias": "bearish",
                "strategy_state": "blocked",
                "confidence_score": 0.6,
            }
        },
        timeframe_snapshots={
            "4h": {"bias": "bearish", "confidence": 0.5},
            "1d": {"bias": "bearish", "confidence": 0.8},
            "1w": {"bias": "bearish", "confidence": 0.7},
        },
    )
    matrix = summary["decision_brief"]["source_alignment"]["matrix"]
    assert [row["key"] for row in matrix] == [
        "1w_trend",
        "1d_bias",
        "4h_trigger",
        "chip_structure",
        "divergence_summary",
        "strategy_gates",
    ]
    weights = [row["weight"] for row in matrix]
    assert 0.99 <= sum(weights) <= 1.01
    for row in matrix:
        assert row["direction"] in {"bullish", "bearish", "neutral", "missing"}
        assert 0.0 <= row["evidence_strength"] <= 1.0


def test_decision_brief_matrix_marks_missing_sources() -> None:
    summary = TerminalSummaryEngine().build(
        timeframe_snapshots={"1d": {"bias": "bearish", "confidence": 0.8}},
    )
    matrix = summary["decision_brief"]["source_alignment"]["matrix"]
    by_key = {row["key"]: row for row in matrix}
    assert by_key["1d_bias"]["direction"] == "bearish"
    assert by_key["1w_trend"]["direction"] == "missing"
    assert by_key["4h_trigger"]["direction"] == "missing"
    assert by_key["chip_structure"]["direction"] == "missing"
    assert by_key["divergence_summary"]["direction"] == "missing"
    assert by_key["strategy_gates"]["direction"] == "missing"
    assert by_key["1w_trend"]["evidence_strength"] == 0.0


def test_decision_brief_matrix_reflects_cross_source_conflict() -> None:
    summary = TerminalSummaryEngine().build(
        alerts_bundle={
            "chip_structure": {"direction": "bullish", "confidence_score": 0.7},
        },
        strategy_bundle={
            "decision": {
                "strategy_bias": "bullish",
                "strategy_state": "ready",
                "confidence_score": 0.8,
            }
        },
        timeframe_snapshots={
            "4h": {"bias": "bullish", "confidence": 0.6},
            "1d": {"bias": "bearish", "confidence": 0.7},
            "1w": {"bias": "bearish", "confidence": 0.8},
        },
    )
    matrix = summary["decision_brief"]["source_alignment"]["matrix"]
    by_key = {row["key"]: row for row in matrix}
    # 4h bullish vs 1d/1w bearish should be a multi-period conflict.
    assert by_key["4h_trigger"]["direction"] == "bullish"
    assert by_key["1d_bias"]["direction"] == "bearish"
    assert by_key["1w_trend"]["direction"] == "bearish"
    assert summary["decision_brief"]["source_alignment"]["consistency"] == "conflict"
