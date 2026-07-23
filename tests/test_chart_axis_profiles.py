from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_chart_module(script_body: str) -> dict:
    module_path = ROOT / "app/static/ui/charts.js"
    script = f"""
import {{
  sanitizeChartSeries,
  collectFiniteDatasetValues,
  buildAdaptiveAxisOptions,
  buildAdaptiveScaleOptionsForAxes,
  candleDataset,
  lineDataset,
}} from 'file:///{module_path.as_posix()}';
{script_body}
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_chart_series_keeps_missing_values_out_of_numeric_domain() -> None:
    result = _run_chart_module(
        """
const clean = sanitizeChartSeries([65000, null, "", "66000", NaN, Infinity]);
const candle = candleDataset("K", [
  { open: 65000, high: 65500, low: 64500, close: 65200 },
  { open: null, high: null, low: null, close: null },
]);
console.log(JSON.stringify({ clean, candleData: candle.data, candles: candle.candles }));
"""
    )

    assert result["clean"] == [65000, None, None, 66000, None, None]
    assert result["candleData"] == [65200, None]
    assert result["candles"][1] is None


def test_price_axis_uses_only_valid_visible_price_data() -> None:
    result = _run_chart_module(
        """
const datasets = [
  { data: [62000, null, 67000] },
  { data: [62500, 64000, 66500] },
  { data: [null, null, null] },
];
const values = collectFiniteDatasetValues(datasets);
const axis = buildAdaptiveAxisOptions("price", datasets);
console.log(JSON.stringify({ values, axis }));
"""
    )

    assert result["values"] == [62000, 67000, 62500, 64000, 66500]
    assert 61000 < result["axis"]["min"] < 62000
    assert 67000 < result["axis"]["max"] < 68000


def test_semantic_axis_profiles_preserve_financial_reference_points() -> None:
    result = _run_chart_module(
        """
const oscillator = buildAdaptiveAxisOptions("oscillator", [{ data: [41, 52, 58] }]);
const volume = buildAdaptiveAxisOptions("volume", [{ data: [100, 250, 180] }]);
const macd = buildAdaptiveAxisOptions("centeredZero", [{ data: [-15, 8, 12] }]);
const equal = buildAdaptiveAxisOptions("generic", [{ data: [50, 50, 50] }]);
console.log(JSON.stringify({ oscillator, volume, macd, equal }));
"""
    )

    assert result["oscillator"]["min"] == 0
    assert result["oscillator"]["max"] == 100
    assert result["volume"]["min"] == 0
    assert result["volume"]["max"] > 250
    assert result["macd"]["min"] == -result["macd"]["max"]
    assert result["macd"]["min"] < -15
    assert result["equal"]["min"] < 50 < result["equal"]["max"]


def test_percent_and_ratio_profiles_preserve_financial_reference_points() -> None:
    result = _run_chart_module(
        """
const percent = buildAdaptiveAxisOptions("percent", [{ data: [0.42, 0.66] }]);
const negativePercent = buildAdaptiveAxisOptions("percent", [{ data: [-0.04, 0.03] }]);
const ratio = buildAdaptiveAxisOptions("ratio", [{ data: [0.72, 0.96] }]);
console.log(JSON.stringify({ percent, negativePercent, ratio }));
"""
    )

    assert 0 < result["percent"]["min"] < 0.42
    assert result["percent"]["max"] > 0.66
    assert result["negativePercent"]["min"] < -0.04
    assert result["negativePercent"]["max"] > 0.03
    assert result["ratio"]["min"] < 0.72
    assert result["ratio"]["max"] > 1


def test_skew_profile_and_axis_annotations_are_included_in_domain() -> None:
    result = _run_chart_module(
        """
const skew = buildAdaptiveAxisOptions("skew", [{ data: [0.02, 0.04] }]);
const axes = {
  y_price: {
    profile: "price",
    position: "left",
    include_annotations: true,
    padding_ratio: 0.04,
  },
};
const datasets = [
  { label: "Price", yAxisID: "y_price", data: [60000, 61000] },
];
const annotations = [
  { type: "horizontalLine", axis_id: "y_price", y: 65000 },
];
const scales = buildAdaptiveScaleOptionsForAxes(axes, datasets, annotations);
console.log(JSON.stringify({ skew, price: scales.y_price }));
"""
    )

    assert result["skew"]["min"] < 0 < result["skew"]["max"]
    assert result["price"]["max"] > 65_000


def test_dataset_opacity_is_applied_without_dropping_other_style_fields() -> None:
    result = _run_chart_module(
        """
const line = lineDataset("Max Pain", [60000], "#64748b", {
  opacity: 0.55,
  borderDash: [2, 5],
  borderWidth: 1.5,
});
console.log(JSON.stringify(line));
"""
    )

    assert result["borderColor"].startswith("rgba(")
    assert result["backgroundColor"].startswith("rgba(")
    assert result["borderDash"] == [2, 5]
    assert result["borderWidth"] == 1.5
    assert "opacity" not in result


def test_multi_axis_domains_use_only_datasets_assigned_to_each_axis() -> None:
    result = _run_chart_module(
        """
const axes = {
  y_price: { profile: "price", position: "left", unit: "USD" },
  y_oi: { profile: "volume", position: "right", unit: "USD" },
  y_funding: { profile: "centeredZero", position: "right", unit: "zscore" },
};
const datasets = [
  { label: "Price", yAxisID: "y_price", data: [58000, 61000] },
  { label: "OI", yAxisID: "y_oi", data: [13e9, 15e9] },
  { label: "Funding", yAxisID: "y_funding", data: [-0.2, 1.0] },
];
const scales = buildAdaptiveScaleOptionsForAxes(axes, datasets);
console.log(JSON.stringify(scales));
"""
    )

    assert 55_000 < result["y_price"]["min"] < 58_000
    assert 61_000 < result["y_price"]["max"] < 64_000
    assert result["y_oi"]["min"] == 0
    assert result["y_oi"]["max"] > 15e9
    assert result["y_funding"]["min"] == -result["y_funding"]["max"]
    assert result["y_oi"]["ticks"]["display"] is True


def test_multi_axis_render_hides_the_unused_default_y_axis() -> None:
    source = (ROOT / "app/static/ui/charts.js").read_text(encoding="utf-8")

    assert "hideDefaultYAxis()" in source
    assert "...hideDefaultYAxis()," in source


def test_reference_line_plugin_is_registered_without_external_dependency() -> None:
    source = (ROOT / "app/static/ui/charts.js").read_text(encoding="utf-8")

    assert 'id: "referenceLines"' in source
    assert "config.annotations" in source
    assert "referenceLinePluginRegistered" in source
    assert "scale.options.display === false" in source


def test_bollinger_price_axis_includes_candle_extremes_and_bands() -> None:
    result = _run_chart_module(
        """
const candle = candleDataset("K", [
  { open: 64000, high: 66800, low: 63200, close: 65000 },
  { open: 65000, high: 67100, low: 64500, close: 66500 },
]);
const datasets = [
  candle,
  { data: [67500, 67600] },
  { data: [62500, 62800] },
];
const values = collectFiniteDatasetValues(datasets);
const axis = buildAdaptiveAxisOptions("price", datasets);
console.log(JSON.stringify({ values, axis }));
"""
    )

    assert min(result["values"]) == 62500
    assert max(result["values"]) == 67600
    assert result["axis"]["min"] < 62500
    assert result["axis"]["max"] > 67600


def test_analysis_assigns_an_axis_profile_to_every_chart() -> None:
    source = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")

    assert source.count('axisProfile: "price"') == 3
    assert 'axisProfile: "oscillator"' in source
    assert 'axisProfile: "volume"' in source
    assert 'axisProfile: "centeredZero"' in source
    assert "finiteInputNumber(item.open)" in source
    assert "open: Number(item.open)" not in source[
        source.index("function normalizeOhlcCandles") :
    ]
    chart_source = (ROOT / "app/static/ui/charts.js").read_text(encoding="utf-8")
    assert "chart.canvas.dataset.axisProfile" in chart_source
    assert "chart.canvas.dataset.axisMin" in chart_source
    assert "chart.canvas.dataset.axisMax" in chart_source
    assert 'plugins: { adaptiveAxis: { profile: axisProfile } }' in chart_source
    plugin = chart_source[
        chart_source.index("const adaptiveAxisPlugin") :
        chart_source.index("function renderChartError")
    ]
    assert "deepMerge(y.ticks" not in plugin
    assert "deepMerge(x.ticks" not in plugin
    batch = source[
        source.index("function renderChartBatch") : source.index("async function loadAll")
    ]
    assert "requestAnimationFrame" not in batch
    assert "window.setTimeout(step, 0)" in batch


def test_structure_chart_never_falls_back_to_zero_price() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    path_function = source[
        source.index("function buildLinePath") : source.index("function buildAxisMarkup")
    ]

    assert "point.close ?? 0" not in path_function
    assert "Number.isFinite" in path_function


def test_hidden_tooltips_do_not_create_mobile_horizontal_overflow() -> None:
    source = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    tooltip = source[source.index(".tooltip-bubble {") : source.index(".tooltip-bubble::after")]
    visible = source[
        source.index(".tooltip-anchor:hover .tooltip-bubble") :
        source.index(".tooltip-link")
    ]

    assert "display: none;" in tooltip
    assert "display: block;" in visible
