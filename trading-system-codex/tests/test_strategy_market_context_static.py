from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_exposes_market_context_client() -> None:
    source = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "getMarketContext(" in source
    assert '"/market-context/snapshot"' in source


def test_strategy_page_loads_unified_strategy_stack() -> None:
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    assert "api.getUnifiedStrategy" in source
    assert "api.getMonitoringDashboard" in source
    assert "api.getBtcDerivativesDashboard" in source
    assert "api.getMacroOverview" in source
    assert "Promise.allSettled" in source
    assert "normalizeUnifiedStrategy" in source
    assert "buildDataDegradedCard" in source
    assert "timeframe_stack" in adapter
    assert "horizon_views" in adapter
    assert "horizon_governance" in adapter
    assert "event_watch" in adapter
    assert "evidence_ref" in adapter
    assert "evidence_confidence" in adapter
    assert "data_access" in adapter


def test_strategy_v2_renderers_show_real_unified_payload_fields() -> None:
    operation = (ROOT / "app/static/pages/strategy/renderMarketOperation.js").read_text(
        encoding="utf-8"
    )
    event_watch = (ROOT / "app/static/pages/strategy/renderEventWatch.js").read_text(
        encoding="utf-8"
    )
    risk_panel = (ROOT / "app/static/pages/strategy/renderRiskPanel.js").read_text(
        encoding="utf-8"
    )
    evidence = (ROOT / "app/static/pages/strategy/renderEvidenceTrace.js").read_text(
        encoding="utf-8"
    )
    trade_plans = (ROOT / "app/static/pages/strategy/renderTradePlans.js").read_text(
        encoding="utf-8"
    )
    horizon_stack = (ROOT / "app/static/pages/strategy/renderHorizonStack.js").read_text(
        encoding="utf-8"
    )

    assert "safe.evidence" in operation
    assert "safe.details" in operation
    assert "evidence_confidence" in operation
    assert "isRoutineEvent" in event_watch
    assert "清晰" in event_watch
    assert "normal" in event_watch
    assert "dedupeRisks" in risk_panel
    assert "risk.id" in risk_panel or "risk.key" in risk_panel
    # v1.7: evidence card no longer renders calculation_rule / input_features /
    # source_modules as visible text.
    assert "计算规则" not in evidence
    assert "输入特征" not in evidence
    assert "human_explanation" in evidence
    assert "freshnessLabel" in evidence
    assert "入场区间" in trade_plans
    assert "失效条件" in trade_plans
    assert "verdictLabel" in horizon_stack
    assert "evidence_confidence" in horizon_stack


def test_strategy_snapshot_builder_attaches_market_context() -> None:
    source = (ROOT / "app/services/strategy_signal/snapshot_builder.py").read_text(
        encoding="utf-8"
    )
    assert "MarketContextBuilder" in source
    assert '"market_context"' in source


def test_strategy_evidence_trace_omits_internal_namespace_labels() -> None:
    """v1.7: ensure internal algorithm names never reach the user-facing evidence card."""
    source = (ROOT / "app/static/pages/strategy/renderEvidenceTrace.js").read_text(
        encoding="utf-8"
    )
    forbidden = [
        "weighted_direction_score",
        "higher_tf_constraint + tactical_conflict",
        "market_operation.<key>.bias",
        "horizon_views.<key>.direction",
    ]
    for token in forbidden:
        assert token not in source, f"evidence card should not render: {token}"


def test_strategy_render_does_not_expose_calculation_rule_input_features() -> None:
    """v1.7: payload may still contain them, but the renderer must not display them."""
    evidence = (ROOT / "app/static/pages/strategy/renderEvidenceTrace.js").read_text(
        encoding="utf-8"
    )
    trade_plans = (ROOT / "app/static/pages/strategy/renderTradePlans.js").read_text(
        encoding="utf-8"
    )
    # The renderer must not read calculation_rule / input_features as displayed text.
    for token in ("calculation_rule", "input_features"):
        assert token not in evidence, f"renderEvidenceTrace must not display {token}"
        assert token not in trade_plans, f"renderTradePlans must not display {token}"


def test_strategy_data_degraded_footer_endpoint_set() -> None:
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    for label in ("统一策略", "监控总览", "衍生品", "宏观"):
        assert label in adapter
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "buildDataDegradedCard(model)" in index


def test_strategy_risk_gate_uses_chinese_labels() -> None:
    risk_gate = (ROOT / "app/services/strategy_unified/risk_gate.py").read_text(
        encoding="utf-8"
    )
    for label in ("核心周期数据缺失", "高影响事件窗口", "衍生品确认降级", "链上数据缺失"):
        assert label in risk_gate, f"risk_gate must use Chinese label: {label}"


def test_strategy_macro_regime_emits_human_explanation() -> None:
    macro = (ROOT / "app/services/strategy_unified/macro_regime.py").read_text(
        encoding="utf-8"
    )
    assert "human_explanation" in macro
    assert "宏观" in macro


def test_strategy_onchain_observation_writes_indicator_observations() -> None:
    policy = (ROOT / "app/services/onchain/policy_adapter.py").read_text(encoding="utf-8")
    indicator_monitoring = (
        ROOT / "app/services/indicator_monitoring.py"
    ).read_text(encoding="utf-8")
    assert "DefiLlamaPolicyAdapter" in policy or "collect_via_router" in policy
    assert "ensure_defillama_definitions" in policy
    assert "persist_drafts" in policy
    assert "collect_via_router" in indicator_monitoring
    assert "ensure_defillama_definitions" in indicator_monitoring


def test_strategy_verdict_for_node_handles_all_states() -> None:
    from app.services.strategy_unified.contracts import verdict_for_node

    # Sanity: function is importable and resolves all canonical cases.
    assert callable(verdict_for_node)
    assert verdict_for_node("NO_EDGE", "NEUTRAL", "1d") == "RANGE_NO_EDGE"
    assert verdict_for_node("CONTEXT_LONG", "LONG", "1M") == "STRATEGIC_LONG_TACTICAL_LONG"
    assert verdict_for_node("CONTEXT_LONG", "LONG", "4h") == "CONTEXT_ALIGNED_LONG"
    assert verdict_for_node("CONTEXT_SHORT", "SHORT", "1M") == "STRATEGIC_SHORT_TACTICAL_SHORT"
    assert verdict_for_node("CONTEXT_SHORT", "SHORT", "1h") == "CONTEXT_ALIGNED_SHORT"
    assert verdict_for_node("EVENT_LOCKED", "NEUTRAL", "1d") == "EVENT_LOCKED"
    assert verdict_for_node("DATA_DEGRADED", "NEUTRAL", "1d") == "DATA_DEGRADED"
    assert verdict_for_node("CONTEXT_MISSING", "NEUTRAL", "1d") == "DATA_DEGRADED"
    assert verdict_for_node("UNKNOWN_STATE", "NEUTRAL", "1d") == "RANGE_NO_EDGE"