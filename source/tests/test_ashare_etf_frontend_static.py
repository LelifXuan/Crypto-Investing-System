"""Static guards for the ETF equity-curve (strategy-simulation) frontend.

Regression (2026-08-07): the equity-curve section is rebuilt from innerHTML
on every response, and the 初始建仓 / 每期定投 / 调仓延后 inputs used
hard-coded template literals (``value="100000"`` / ``"5000"`` / ``"0"``).
Any value the user typed was silently discarded by the post-fetch re-render —
the chart kept replaying the default parameters. The fix captures the current
input values before rebuilding and reuses them as the new defaults.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "app" / "static" / "pages" / "ashare_etf.js"


def _read() -> str:
    return JS_PATH.read_text(encoding="utf-8")


class TestInputValuePreservation:
    def test_capture_helper_exists(self):
        src = _read()
        assert "function _captureEquityInputValues(root)" in src

    def test_capture_reads_all_simulation_controls(self):
        """Every editable simulation control must be captured before rebuild:
        from-month, initial capital, period amount, rebalance offset."""
        src = _read()
        for control_id in (
            "etf-equity-from-month",
            "etf-equity-from-date",
            "etf-equity-initial-capital",
            "etf-equity-monthly-amount",
            "etf-equity-offset-days",
        ):
            assert control_id in src, f"capture helper must read #{control_id}"

    def test_template_uses_captured_defaults_not_literals(self):
        """The re-rendered inputs must carry the captured values (so user
        edits survive the fetch round-trip), not the hard-coded defaults."""
        src = _read()
        assert 'value="${escapeHtml(capitalDefault)}"' in src
        assert 'value="${escapeHtml(periodDefault)}"' in src
        assert 'value="${escapeHtml(offsetDefault)}"' in src

    def test_no_hard_coded_money_literals_in_inputs(self):
        """Guard against regressing to the silent-reset behavior."""
        src = _read()
        assert 'value="100000"' not in src, (
            "initial-capital input must not hard-code 100000 (silent reset)"
        )
        assert 'value="5000"' not in src, (
            "period-amount input must not hard-code 5000 (silent reset)"
        )

    def test_capital_default_falls_back_to_spec_when_missing(self):
        """First render (no inputs yet) still defaults to the spec amounts."""
        src = _read()
        assert 'const capitalDefault = prevInputs.initialCapital !== null' in src
        assert '? prevInputs.initialCapital' in src
        assert ': "10000";' in src
        assert ': "1000";' in src


class TestPresentValueView:
    """Present-value chart view (2026-08-07): the simulation curves plot
    money (策略市值 / 累计投入 / 一次性投入 市值) on one yuan axis instead of
    return percentages. The old yield view's two percent curves were
    dominated by the early lump-sum deployment and looked near-identical to
    the benchmark, so the strategy-vs-buy-and-hold gap was unreadable."""

    def test_curves_are_present_value_not_returns(self):
        src = _read()
        assert 'lineDataset("策略权益"' in src
        assert '"一次性投入 权益"' in src
        # Old percentage curves must be gone.
        assert '"定投收益率"' not in src
        assert '"一次性投入 收益率"' not in src

    def test_strategy_curve_plots_total_value(self):
        """The strategy line must be the full-strategy present value
        (initial build + 定投 + quarter rebalances), not return_pct."""
        src = _read()
        assert "strategyValue" in src
        assert "Number(p.total_value || 0)" in src
        assert "return_pct" not in src.split("_renderEquityChart")[1].split("else {")[0], (
            "simulation chart must not plot return_pct"
        )

    def test_single_yuan_axis(self):
        """All three money curves share one yuan axis — no percent axis, no
        dual-axis y1."""
        src = _read()
        assert 'profile: "raw"' in src
        assert 'value_format: "integer"' in src
        assert 'position: "left"' in src
        assert "yAxisID" not in src, "no dataset may bind to a second axis"
        assert 'y1:' not in src, "dual-axis y1 must be removed"

    def test_tooltip_formats_money_not_percent(self):
        """The present-value tooltip prints yuan amounts; the old
        percent-multiplier branch (×100 + %) must be gone."""
        src = _read()
        assert 'label.includes("收益率")' not in src
        assert "ctx.parsed.y * 100" not in src

    def test_stat_cards_compare_present_values(self):
        src = _read()
        # Simulation branch only: from `if (mode === "simulation")` up to the
        # holdings branch marker — the percent headline must be gone there.
        sim_slice = src.split('if (mode === "simulation")')[1].split(
            "holdings (legacy equity curve)"
        )[0]
        assert '"策略权益"' in sim_slice
        assert '"一次性投入 权益"' in sim_slice
        assert '"策略 vs 一次性"' in sim_slice
        assert "moneySigned(excess)" in sim_slice
        assert '"累计收益率"' not in sim_slice, (
            "simulation stat cards must not show a return-percentage headline"
        )
        # Holdings mode keeps its own return card — untouched.
        assert '"累计收益率"' in src


class TestFullStrategyWeeklyDcaCashflow:
    """Full-strategy wiring (2026-08-07): weekly DCA default + the 6:1
    HALO:cashflow split sent to the backend + cashflow stat cards."""

    def test_frequency_defaults_to_week(self):
        src = _read()
        assert 'let equityCurveFrequency = "week";' in src, (
            "full strategy runs on weekly DCA by default"
        )

    def test_payload_sends_cashflow_ratio(self):
        src = _read()
        assert "cashflow_ratio: 6," in src, (
            "simulation payload must split weekly cash HALO:cashflow = 6:1"
        )

    def test_cashflow_stat_card_rendered(self):
        src = _read()
        assert '"现金流ETF 权益"' in src
        assert "final_cashflow_value" in src
        assert "final_cashflow_shares" in src
        assert "final_cashflow_cash" in src

    def test_simulation_title_mentions_cashflow_leg(self):
        src = _read()
        assert "HALO & 现金流 ETF" in src
        assert "etf-equity-strategy-note" in src


class TestWeeklyBarsOverlay:
    """Weekly x-axis granularity + one coloured vertical bar per ISO
    week (2026-08-07). When the backend emits ``weekly_series`` the
    frontend must switch the equity-curve labels and the dataset
    source to the weekly trail, build the per-week bar overlay, and
    forward it to the custom weeklyBars chart.js plugin. Tooltip must
    surface the per-week strategy-vs-lump-sum return pcts that drive
    the bar colour."""

    def test_weekly_series_drives_labels_and_datasets(self):
        src = _read()
        assert "weekly_series" in src, (
            "_renderEquityChart must read data.weekly_series to switch to "
            "weekly x-axis granularity when the backend emits it"
        )
        assert "data.weeks" in src, (
            "_renderEquityChart must read data.weeks (1:1-aligned with "
            "weekly_series) for the weekly x-axis labels"
        )

    def test_weekly_bars_items_built_per_week(self):
        src = _read()
        assert "weeklyBarsItems" in src, (
            "the weekly-bars overlay array must be built from weekly_series"
        )
        assert "diffPct" in src, (
            "each weekly-bars item must carry the strategy-vs-lump-sum "
            "return-pct delta that drives the bar colour"
        )

    def test_weekly_bars_forwarded_to_render_chart(self):
        src = _read()
        # The weekly bars config must reach the renderChart call (top
        # level AND options.plugins.weeklyBars, mirroring the
        # referenceLines double-rail forwarding pattern).
        assert "weeklyBars: weeklyBarsItems" in src, (
            "weeklyBars must be forwarded at the top level of renderChart config"
        )
        assert "weeklyBars: {" in src and "items: weeklyBarsItems" in src, (
            "weeklyBars must ALSO be mirrored into options.plugins.weeklyBars so "
            "the plugin receives the items regardless of how renderChart merges config"
        )

    def test_tooltip_surfaces_weekly_pct(self):
        src = _read()
        assert "weeklyByDate" in src, (
            "tooltip must look up the weekly mark-to-market pcts via a date Map"
        )
        assert "本周策略" in src and "差" in src, (
            "tooltip must surface the per-week strategy / lump-sum / delta pcts"
        )


class TestQuarterlyTopupStat:
    """季末加码(方案 A, 2026-08-11): 统计卡展示独立计数,与调仓(必须含
    卖出)语义分离。调仓竖线仍只画 quarterly_rebalance,topup 不误标。"""

    def test_summary_card_shows_topup_count(self):
        src = _read()
        assert "quarterly_topup_count" in src
        assert "次季末加码" in src

    def test_rebalance_lines_ignore_topup(self):
        src = _read()
        assert 'e.kind === "quarterly_rebalance"' in src, (
            "调仓竖线/工具提示必须只认 quarterly_rebalance,quarterly_topup 不画线"
        )
