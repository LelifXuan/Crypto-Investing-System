from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITORING = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
BTC = (ROOT / "app/static/pages/btc_derivatives.js").read_text(encoding="utf-8")


def test_both_pilots_destroy_page_scoped_workbench_state() -> None:
    for source in (MONITORING, BTC):
        assert "createWorkbenchState" in source
        assert "workbenchState?.destroy()" in source
        assert "interactionController?.abort()" in source
        assert "workbenchUnsubscribe?.()" in source
    assert "observeChartsForPage" in BTC
    assert "{ signal }" in BTC


def test_linked_selection_uses_explicit_ids_not_text_matching() -> None:
    assert "DATASET_INSPECTION_MAP" in BTC
    assert "relatedIds" in BTC
    assert "monitoring:terminal:macro" in MONITORING
    assert "markWorkbenchRelations(root, snapshot)" in BTC
    assert "markWorkbenchRelations(root, snapshot)" in MONITORING


def test_missing_market_facts_are_omitted_from_inspection_adapters() -> None:
    assert "actualMacroScore" in MONITORING
    assert "actualMacroRegime" in MONITORING
    assert "current: score === null ? null" in MONITORING
    assert "current: currentValue === null ? null" in BTC
    assert "btcSourcesForProviders" in BTC
