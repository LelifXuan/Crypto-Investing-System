"""P0-QNT-001 frontend static guards: proxy-scope BTC derivatives data must be
labeled as cross-asset context, never as the viewed asset's own derivatives."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_decision_audit_labels_proxy_scope_signals():
    text = (ROOT / "app/static/pages/strategy/renderDecisionAudit.js").read_text(encoding="utf-8")
    assert "scopedSourceLabel" in text
    assert 'item.asset_scope === "proxy"' in text
    assert "BTC 代理上下文" in text


def test_data_source_status_card_names_btc_endpoint_explicitly():
    text = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    assert 'label: "BTC 衍生品(代理)"' in text


def test_backend_proxy_card_copy_is_labeled_context_only():
    text = (
        ROOT / "app/services/strategy_unified/direction_resolution.py"
    ).read_text(encoding="utf-8")
    assert "BTC 市场代理上下文：仅供市场环境参考，不参与本资产方向判定。" in text
    assert "asset_scope" in text
    service = (ROOT / "app/services/strategy_unified/unified_service.py").read_text(
        encoding="utf-8"
    )
    # Ownership stamping lives in the service that builds signals.
    assert "BTC_REFERENCE_INSTRUMENT" in service
    assert "_derivatives_ownership" in service
    # The resolver must receive the target instrument (INV-001 gate input).
    assert "target_instrument_id=instrument" in service


def test_no_default_asset_lens_on_generic_signal():
    text = (
        ROOT / "app/services/strategy_unified/direction_resolution.py"
    ).read_text(encoding="utf-8")
    # The generic ModuleSignal must not default to any asset lens; only the
    # BTC-specific derivatives builder may declare the BTC lens explicitly.
    assert 'asset_lens: str = ""' in text
    assert 'asset_lens=str(self.asset_lens or "")' in text
