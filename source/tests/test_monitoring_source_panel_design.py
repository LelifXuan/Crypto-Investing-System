"""Static guards for the compact monitoring source-status ledger."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "monitoring.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_source_availability_does_not_reuse_direction_tones() -> None:
    block = PAGE[PAGE.index("const SOURCE_STATUS_META"):PAGE.index("const LAYER_LABELS")]
    assert '"chip-bullish"' not in block
    assert '"chip-bearish"' not in block
    for tone in ('"live"', '"stale"', '"offline"', '"unavailable"'):
        assert tone in block
    assert 'data-source-state="${meta.tone}"' in PAGE


def test_source_rows_have_semantic_time_and_compact_heading() -> None:
    assert 'class="monitoring-source-heading"' in PAGE
    assert 'class="monitoring-source-time"' in PAGE
    assert '<time datetime="${escapeHtml(source.updatedAt)}">' in PAGE


def test_source_panel_has_a_container_responsive_single_column_mode() -> None:
    assert ".monitoring-source-panel" in STYLES
    assert "container-type: inline-size" in STYLES
    assert "@container (max-width: 620px)" in STYLES
