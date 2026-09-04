from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = (ROOT / "app/static/ui/inspector.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")


def test_inspector_has_dock_and_responsive_dialog_semantics() -> None:
    assert 'role", drawer ? "dialog" : "complementary"' in INSPECTOR
    assert 'aria-modal", drawer ? "true" : "false"' in INSPECTOR
    assert "(max-width: 1180px)" in INSPECTOR
    assert "@media (max-width: 1180px)" in CSS
    assert "@media (max-width: 900px)" in CSS


def test_inspector_escape_focus_and_empty_section_contract() -> None:
    assert 'event.key === "Escape"' in INSPECTOR
    assert "state.clearSelection()" in INSPECTOR
    assert "if (!content) return" in INSPECTOR
    assert "workbench-inspector-close" in INSPECTOR
    assert 'aria-label="关闭上下文详情"' in INSPECTOR
    assert "returnFocus = null" in INSPECTOR
    assert "is-workbench-inspector-drawer-open" in INSPECTOR
    assert "body.is-workbench-inspector-drawer-open { overflow: hidden; }" in CSS
    drawer_root = CSS[CSS.index("body.is-workbench-inspector-drawer-open #page-root") :]
    drawer_root = drawer_root[: drawer_root.index("}")]
    assert "animation: none" in drawer_root
    assert "transform: none" in drawer_root
    assert "will-change: auto" in drawer_root
