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
    # 2026-07-30: native <select> was replaced with mountDropdown; local filter
    # onChange handlers now call renderFromBundle(state.bundle) instead of
    # listening to "change" events.
    assert 'data-dropdown-id="structure-system"' in source
    assert 'data-dropdown-id="structure-confidence"' in source
    assert 'data-dropdown-id="structure-viewmode"' in source
    assert source.count("renderFromBundle(state.bundle);") >= 3


def test_structure_page_recovers_a_missing_snapshot_once_on_open() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    # 2026-08-13: loadData is no longer `async function loadData` — the
    # compact redesign uses `function loadData({ forceRefresh } = {})` with
    # the async refresh handled inside.
    load_data_start = source.index("function loadData({ forceRefresh")
    # V1.5.x: loadData is now invoked via .catch() so the page
    # returns a controller object immediately and the load
    # either settles or aborts in the background. Either of
    # these two patterns must be present:
    try:
        load_data_end = source.index("loadData().catch", load_data_start)
    except ValueError:
        load_data_end = source.index("await loadData();", load_data_start)
    load_data_source = source[load_data_start:load_data_end]
    assert "!state.recoveryKeys.has(recoveryKey)" in load_data_source
    assert "state.recoveryKeys.add(recoveryKey)" in load_data_source
    assert "await api.refreshStructure(instrumentId, timeframe)" in load_data_source
    assert "force: true" in load_data_source
    # 2026-08-13: loadData is no longer `async` at declaration — the
    # recovery/refresh path is awaited internally (line ~46 above).
    assert "function loadData({ forceRefresh = false } = {})" in source


def test_structure_page_manual_refresh_uses_refresh_then_bundle_reload() -> None:
    source = STRUCTURE_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert 'listen("#structure-refresh", "click", async () => {' in source
    assert "await api.refreshStructure(" in source
    assert "await loadData({ forceRefresh: true });" in source
