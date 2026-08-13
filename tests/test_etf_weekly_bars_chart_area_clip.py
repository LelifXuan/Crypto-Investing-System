"""Static guards for ETF weekly bars staying inside the plot area."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARTS = (ROOT / "app" / "static" / "ui" / "charts.js").read_text(encoding="utf-8")


def test_weekly_bar_baseline_is_clamped_to_visible_chart_area() -> None:
    assert "const rawBaseline = yScale.getPixelForValue(0)" in CHARTS
    assert "Math.min(chartArea.bottom, rawBaseline)" in CHARTS
    assert "Math.min(chartArea.bottom, yTop)" in CHARTS


def test_weekly_bar_overlay_clips_canvas_to_plot_rectangle() -> None:
    plugin_start = CHARTS.index('id: "weeklyBars"')
    plugin_end = CHARTS.index("function baseOptions()", plugin_start)
    plugin = CHARTS[plugin_start:plugin_end]

    assert "ctx.rect(" in plugin
    assert "chartArea.right - chartArea.left" in plugin
    assert "chartArea.bottom - chartArea.top" in plugin
    assert "ctx.clip()" in plugin
