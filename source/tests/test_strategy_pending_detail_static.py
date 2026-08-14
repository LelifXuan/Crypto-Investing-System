from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unpublished_strategy_detail_uses_compact_recovery_state():
    source = (ROOT / "app/static/pages/strategy/renderDetailPanel.js").read_text(
        encoding="utf-8"
    )

    assert "function hasPublishedDetail" in source
    assert "strategy-detail-pending" in source
    assert "策略详情尚未形成" in source
    assert "if (pending)" in source
    assert source.index("if (pending)") < source.index("const sections = [")
    pending_block = source[source.index("if (pending)"):source.index("const sections = [")]
    assert "renderMarketOperation" not in pending_block
    assert "renderDecisionAudit" not in pending_block


def test_pending_scan_cells_are_not_clickable_as_complete_reports():
    source = (ROOT / "app/static/pages/strategy/renderScanMatrix.js").read_text(
        encoding="utf-8"
    )

    assert "数据构建中" in source
    assert 'disabled aria-disabled="true"' in source


def test_scan_backend_requires_published_detail_before_marking_cell_ready():
    source = (
        ROOT / "app/services/strategy_unified/opportunity_scanner.py"
    ).read_text(encoding="utf-8")

    assert "has_published_detail" in source
    assert "or not has_published_detail" in source
