from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALERTS_PAGE = PROJECT_ROOT / "app" / "static" / "pages" / "alerts.js"


def test_alerts_page_reads_bundle_backed_chip_structure() -> None:
    source = ALERTS_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert "api.getAlertsBundle(" in source
    assert "renderChipStructureCard(chipStructure)" in source
    assert '<section id="alerts-chip-structure"></section>' in source


def test_alerts_page_keeps_divergence_and_appendix_sections() -> None:
    source = ALERTS_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert "divergence-alert-card" in source
    assert 'id="alerts-divergence"' in source
    assert '<section id="alerts-chip-appendix"></section>' in source


def test_alerts_page_uses_business_facing_chip_structure_fields() -> None:
    source = ALERTS_PAGE.read_text(encoding="utf-8", errors="ignore")
    for field_name in (
        "state_label",
        "state_reason",
        "spot_allocation_label",
        "futures_allocation_label",
        "probe_position_label",
        "confidence_label",
        "execution_label",
        "risk_label",
        "explain",
        "components",
    ):
        assert field_name in source


def test_alerts_page_avoids_business_title_tooltips() -> None:
    source = ALERTS_PAGE.read_text(encoding="utf-8", errors="ignore")
    assert 'title="' not in source
    assert "knowledgeTooltip(" in source
    assert "knowledgeTooltipWrap(" in source
    assert "scheduleIdlePrecompute(" in source
