"""Static guards for the compact source-health ledger."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_monitoring_sources_use_four_columns_on_wide_screens() -> None:
    assert 'body[data-page="monitoring-overview"] .monitoring-source-list' in EDITORIAL
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in EDITORIAL
    assert "min-height: 96px" in EDITORIAL


def test_monitoring_sources_collapse_responsively() -> None:
    assert "@media (max-width: 1279px)" in EDITORIAL
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in EDITORIAL
    assert "@media (max-width: 640px)" in EDITORIAL
