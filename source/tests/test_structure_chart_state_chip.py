"""Guards the public data-state chip above the structure chart."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "structure.js").read_text(encoding="utf-8")


def test_directional_chart_header_chip_is_removed() -> None:
    render_start = PAGE.index("function renderChart(")
    render_end = PAGE.index("\nfunction renderSummary(", render_start)
    block = PAGE[render_start:render_end]
    assert "structure-chart-bias" not in PAGE
    assert "局部${combinedBiasLabel" not in block
    assert "patternStateLabel(snapshot" not in block


def test_ready_snapshot_uses_a_compact_public_state_chip() -> None:
    assert 'id="structure-chart-state"' in PAGE
    assert '"快照可用 · 自动维护"' in PAGE
    assert '{ available: true }' in PAGE
    assert 'state.innerHTML = `<span class="status-chip ${chipTone}">' in PAGE
