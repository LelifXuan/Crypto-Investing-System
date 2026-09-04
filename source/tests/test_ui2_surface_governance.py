import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")


def test_ui2_declares_exactly_four_named_surface_roles() -> None:
    for role in ("canvas", "section", "panel", "floating"):
        assert f".workbench-surface-{role}" in CSS
    assert ".workbench-surface-card" not in CSS


def test_editorial_remains_the_only_canonical_root_and_ui2_avoids_transition_all() -> None:
    assert STYLES.count(":root {") == 0
    assert len(re.findall(r"^:root\s*\{", CSS, flags=re.MULTILINE)) == 1
    ui2 = CSS[CSS.index("CIS Workbench UI 2.0") :]
    assert "transition: all" not in ui2
    static_contract = ui2.split("Workbench pilots", 1)[0]
    filters = re.findall(r"backdrop-filter\s*:\s*([^;}]+)", static_contract)
    assert all(value.strip() == "none" for value in filters)


def test_pilot_static_sections_are_flat_and_floating_surface_is_explicit() -> None:
    assert ".workbench-surface-panel" in CSS
    assert (
        "box-shadow: none;"
        in CSS[CSS.index(".workbench-surface-panel") : CSS.index(".workbench-surface-floating")]
    )
    assert 'body[data-page="btc-derivatives"] .btc-cockpit-header' in CSS
    cockpit = CSS[CSS.index('body[data-page="btc-derivatives"] .btc-cockpit-header') :]
    assert "box-shadow: none;" in cockpit.split("}", 1)[0]
    monitoring = CSS[CSS.index('body[data-page="monitoring-overview"] .monitoring-panel,') :]
    assert "box-shadow: none;" in monitoring.split("}", 1)[0]
