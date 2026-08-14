from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETAIL_PANEL = ROOT / "app" / "static" / "pages" / "strategy" / "renderDetailPanel.js"
STRATEGY_PAGE = ROOT / "app" / "static" / "pages" / "strategy" / "index.js"


def test_detail_panel_closes_for_any_pointer_outside_the_drawer() -> None:
    source = DETAIL_PANEL.read_text(encoding="utf-8")

    assert 'document.addEventListener("pointerdown", outsidePointerHandler, true)' in source
    assert "if (!panel.contains(event.target)) close();" in source
    assert 'document.removeEventListener("pointerdown", outsidePointerHandler, true)' in source


def test_detail_panel_cleanup_runs_when_strategy_page_unmounts() -> None:
    source = STRATEGY_PAGE.read_text(encoding="utf-8")
    unmount = source[source.index("unmount: async () => {") :]

    assert "activeDetailPanelClose?.();" in unmount
    assert "detailLoadController?.abort();" in unmount


def test_detail_panel_exposes_dialog_semantics_and_close_handle() -> None:
    source = DETAIL_PANEL.read_text(encoding="utf-8")

    assert 'panel.setAttribute("role", "dialog")' in source
    assert 'panel.setAttribute("aria-modal", "true")' in source
    assert 'panel.setAttribute("aria-labelledby", "strategy-detail-title")' in source
    assert "return close;" in source
