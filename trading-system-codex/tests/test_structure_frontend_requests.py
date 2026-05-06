from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_PAGE = PROJECT_ROOT / "app" / "static" / "pages" / "structure.js"


def test_structure_page_uses_bundle_as_primary_data_source() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert "api.getStructureBundle" in source
    assert "api.getStructureSnapshot" not in source
    assert "api.getStructureEvents" not in source
    assert "api.getStructureAlerts" not in source
    assert "api.getStructureDiagnostics" not in source


def test_structure_page_local_filters_only_rerender() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert 'listen("#structure-system", "change"' in source
    assert 'listen("#structure-confidence", "change"' in source
    assert 'listen("#structure-viewmode", "change"' in source
    assert source.count("renderFromBundle(state.bundle);") >= 3


def test_structure_page_does_not_auto_live_sync_on_open() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    load_data_start = source.index("async function loadData")
    load_data_end = source.index("await loadData();", load_data_start)
    load_data_source = source[load_data_start:load_data_end]
    assert "api.refreshStructure" not in load_data_source
    assert "async function loadData({ forceRefresh = false } = {})" in source


def test_structure_page_manual_refresh_uses_refresh_then_bundle_reload() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert 'listen("#structure-refresh", "click", async () => {' in source
    assert "await api.refreshStructure(" in source
    assert "await loadData({ forceRefresh: true });" in source
