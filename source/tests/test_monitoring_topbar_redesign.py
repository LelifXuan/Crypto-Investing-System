"""Static guards for the editorial monitoring context bar."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "monitoring.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_topbar_groups_context_metrics_and_sources() -> None:
    assert 'class="monitoring-topbar-item monitoring-topbar-context wide"' in PAGE
    assert 'class="monitoring-metric-rail"' in PAGE
    assert 'class="monitoring-source-rail-label"' in PAGE
    assert 'class="monitoring-top-status"' not in PAGE


def test_topbar_uses_editorial_three_zone_layout() -> None:
    assert "grid-template-columns: minmax(250px, 1.15fr) minmax(620px, 3fr) auto" in EDITORIAL
    assert ".monitoring-context-status::before" in EDITORIAL
    assert "grid-template-columns: repeat(5, minmax(104px, 1fr))" in EDITORIAL
    assert "background: var(--surface-muted)" in EDITORIAL
