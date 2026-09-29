"""P1-SEM-001 / INV-003: a heuristic evidence score must never be presented
as a calibrated probability (win rate, success probability, XX% certainty)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategy_renderers_do_not_show_confidence_as_percentage():
    for name in ("renderScanRanked.js", "renderTimeframeFocus.js", "renderScanMatrix.js"):
        text = (ROOT / "app/static/pages/strategy" / name).read_text(encoding="utf-8")
        assert "置信度" not in text, name
    ranked = (ROOT / "app/static/pages/strategy/renderScanRanked.js").read_text(
        encoding="utf-8"
    )
    assert "证据质量 ${escapeHtml(String(Math.round(item.confidence)))}/100" in ranked
    assert "不代表预测胜率或盈利概率" in ranked


def test_matrix_gate_label_references_evidence_quality():
    text = (ROOT / "app/static/pages/strategy/renderScanMatrix.js").read_text(
        encoding="utf-8"
    )
    assert 'confidence_below_gate: "证据质量未达门槛"' in text


def test_scan_item_declares_confidence_semantics():
    text = (
        ROOT / "app/services/strategy_unified/opportunity_scanner.py"
    ).read_text(encoding="utf-8")
    assert 'confidence_kind: str = "evidence_quality"' in text
    assert "confidence_is_probability: bool = False" in text


def test_decision_audit_payload_declares_confidence_semantics():
    text = (ROOT / "app/services/strategy_unified/unified_service.py").read_text(
        encoding="utf-8"
    )
    assert text.count('"confidence_is_probability": False') >= 2


def test_knowledge_term_states_non_probability_semantics():
    text = (ROOT / "app/static/core/knowledge.js").read_text(encoding="utf-8")
    assert "证据质量评分衡量数据新鲜度、证据覆盖和信号一致性，不代表预测胜率或盈利概率" in text
    assert "不是校准概率" in text
