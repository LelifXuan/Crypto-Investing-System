"""Static assertions for gold V5 frontend module — analysis-page visual alignment."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "app" / "static" / "pages" / "gold_v5.js"
TEMPLATE_PATH = REPO_ROOT / "app" / "templates" / "page.html"
CSS_PATH = REPO_ROOT / "app" / "static" / "styles.css"
MAIN_PATH = REPO_ROOT / "app" / "static" / "main.js"
API_PATH = REPO_ROOT / "app" / "static" / "core" / "api.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestGoldV5Exports:
    def test_module_exists(self):
        assert JS_PATH.exists(), f"missing {JS_PATH}"

    def test_exports_renderGoldV5(self):
        assert "export async function renderGoldV5" in _read(JS_PATH)

    def test_includes_unmount(self):
        """V5 module must export an `unmount` function — bare word match is
        too loose (a comment like `// unmount this later` would pass)."""
        import re
        src = _read(JS_PATH)
        assert re.search(r"export\s+(?:async\s+)?function\s+unmount\b", src), (
            "V5 module must export `unmount` as a function"
        )

    def test_includes_ready(self):
        """V5 module must export a `ready` symbol (function or const)."""
        import re
        src = _read(JS_PATH)
        assert re.search(
            r"export\s+(?:async\s+)?function\s+ready\b|export\s+const\s+ready\b",
            src,
        ), "V5 module must export `ready` (function or const)"


class TestGoldV5ChartIds:
    """The six chart cards keep stable IDs for Chart.js subscription."""
    def test_price_id(self):
        assert "gold-chart-price" in _read(JS_PATH)
    def test_rsi_id(self):
        assert "gold-chart-rsi" in _read(JS_PATH)
    def test_bollinger_id(self):
        assert "gold-chart-bollinger" in _read(JS_PATH)
    def test_volume_id(self):
        assert "gold-chart-volume" in _read(JS_PATH)
    def test_vegas_id(self):
        assert "gold-chart-vegas" in _read(JS_PATH)
    def test_macd_id(self):
        assert "gold-chart-macd" in _read(JS_PATH)
    def test_drawdown_chart_is_removed(self):
        src = _read(JS_PATH)
        assert "gold-chart-drawdown" not in src
        assert 'renderInto("drawdown"' not in src

    def test_chart_order_matches_analysis_workspace(self):
        src = _read(JS_PATH)
        expected = [
            "gold-chart-price",
            "gold-chart-vegas",
            "gold-chart-macd",
            "gold-chart-volume",
            "gold-chart-bollinger",
            "gold-chart-rsi",
        ]
        positions = [src.index(f'renderChartCard("{chart_id}"') for chart_id in expected]
        assert positions == sorted(positions)


class TestGoldV5Governance:
    def test_governance_grid_class(self):
        assert "gold-governance-grid" in _read(JS_PATH)

    def test_mini_card_class(self):
        assert "gold-mini-card" in _read(JS_PATH)

    def test_governance_uses_source_manifest(self):
        """V4 hallucinated payload.macro_bias / payload.sources[]; V5 must read
        the real schema field `source_manifest[]`."""
        src = _read(JS_PATH)
        assert "source_manifest" in src, (
            "V5 must read payload.source_manifest[] for governance "
            "(see spec §4.1 and gold.py:403-460)"
        )

    def test_governance_is_a_compact_source_ledger(self):
        """2026-08-27 §13.2 #3: gold-allocation now routes through the
        shared ui/governanceLedger.js renderer. The legacy inline section
        template + body[data-page="gold-allocation"] .gold-governance CSS
        block were both retired; the rendering contract is the
        .governance-ledger--gold variant in editorial.css + the
        renderGovernanceLedger() call."""
        src = _read(JS_PATH)
        css = _read(REPO_ROOT / "app" / "static" / "editorial.css")
        # gold_v5 imports the shared renderer and delegates to it.
        assert "renderGovernanceLedger" in src
        assert 'variant: "gold"' in src
        # Legacy inline templates and class hooks must NOT be reintroduced.
        assert 'class="card governance-ledger gold-governance"' not in src, (
            "gold_v5 must not inline a legacy governance section template; "
            "the renderer lives in ui/governanceLedger.js"
        )
        assert 'class="governance-ledger__item gold-governance-item"' not in src
        # The .gold-governance JS hook (gold_v5.js:566 querySelector) is
        # preserved as a class on the rendered section, not a CSS target.
        assert "formatSourceAge" in src
        assert "governanceMiniCard" not in src
        # The shared base + gold variant now lives in editorial.css.
        assert ".governance-ledger {" in css
        # The gold variant appears in editorial.css as either a standalone
        # block or one-or-more descendant selectors; the contract is that
        # at least one .governance-ledger--gold rule exists.
        assert ".governance-ledger--gold" in css, (
            "editorial.css must define at least one .governance-ledger--gold rule"
        )

    def test_no_v4_chip_warning_fallback(self):
        """V4 default was 'chip-warning' for any non-fresh governance row;
        V5 routes tone through statusTone() map. Negative + positive: a no-op
        implementation that just deletes the V4 literal would pass the
        negative check alone, so we also require the V5 statusTone helper."""
        src = _read(JS_PATH)
        assert 'class="status-chip ${healthy ? "chip-bullish-soft" : "chip-warning"}' not in src, (
            "V5 must not contain the V4 hard-coded chip-warning ternary"
        )
        assert "statusTone" in src, (
            "V5 must route chip tone through a statusTone() map (see spec §3.2)"
        )


class TestGoldV5DecisionSummary:
    def test_decision_cards_render_before_chart_grid(self):
        src = _read(JS_PATH)
        workbench = src.index('<section class="gold-workbench-grid">')
        chart = src.index('${hasChartSeries ? renderChartGrid() : renderChartGridEmptyState(data)}')
        assert workbench < chart

    def test_decision_cards_use_compact_summary_structure(self):
        src = _read(JS_PATH)
        css = _read(REPO_ROOT / "app" / "static" / "editorial.css")
        assert 'class="gold-dca-overview"' in src
        assert 'class="gold-dca-detail-grid"' in src
        assert src.count('<div class="gold-mini-grid">') == 1
        assert 'body[data-page="gold-allocation"] .gold-mini-grid {' in css
        assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css


class TestGoldV5VisualLanguage:
    def test_no_emoji(self):
        """V4 had zero emoji by user instruction; V5 keeps that guard.
        Scope: pictograph ranges only. JS comments are stripped before scanning
        so a future maintainer can write `// TODO: replace U+1F4C9 icon` without
        tripping the guard.
        """
        import re
        src = _read(JS_PATH)
        # Strip // line comments and /* block */ comments so notes can reference
        # emoji codepoints without tripping the scan.
        stripped = re.sub(r"//[^\n]*", "", src)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
        for ch in stripped:
            cp = ord(ch)
            # Pictographs / faces / dingbats — the ranges most likely to be
            # pasted from a chat client.
            assert not (0x1F300 <= cp <= 0x1F5FF), f"pictograph at U+{cp:04X}"
            assert not (0x1F600 <= cp <= 0x1F64F), f"face emoji at U+{cp:04X}"
            assert not (0x2700 <= cp <= 0x27BF), f"dingbat at U+{cp:04X}"

    def test_no_inline_style_attribute(self):
        """V4 had 11 `style="..."` literals; V5 uses class-based styling only."""
        assert 'style="' not in _read(JS_PATH)

    def test_no_select_literal(self):
        """V4 already complied; keep guard against regression."""
        assert "<select" not in _read(JS_PATH)

    def test_uses_analysis_hero_card_class(self):
        """Hero must reuse analysis-page .analysis-hero-card class."""
        assert "analysis-hero-card" in _read(JS_PATH)

    def test_uses_chart_wrap_class(self):
        """Each chart card must wrap canvas in .chart-wrap (matches analysis)."""
        assert "chart-wrap" in _read(JS_PATH)

    def test_uses_mini_card_class(self):
        """Contract-ref 2x2 tiles must use .mini-card directly."""
        assert "mini-card" in _read(JS_PATH)

    def test_uses_impact_chip_helper(self):
        """V5 must route chip tone through core/dom.js impactChip()."""
        src = _read(JS_PATH)
        assert "impactChip" in src


class TestGoldV5Template:
    def test_jinja_initial_shell_removed(self):
        """V5 deletes the duplicate Jinja hero so first paint is single hero."""
        template = _read(TEMPLATE_PATH)
        assert 'class="hero-card gold-initial-shell"' not in template, (
            "page.html:44-52 gold-initial-shell must be deleted in V5"
        )


class TestGoldV5Routing:
    def test_main_js_routes_to_v5(self):
        """main.js:21 maps gold-allocation → pages/gold_v5.js (not v4).
        Assert on three loose substrings instead of one exact line so a
        future Prettier reformat doesn't break the guard for cosmetic reasons.
        """
        src = _read(MAIN_PATH)
        assert '"gold-allocation"' in src, "main.js must reference gold-allocation page id"
        assert '"./pages/gold_v5.js"' in src, "main.js route must point to gold_v5.js (not v4)"
        assert "loadPageModule" in src, "main.js must use loadPageModule helper"

    def test_main_js_dispatcher_calls_renderGoldV5(self):
        """The dispatcher chain in main.js (~line 175-190) holds a fallback
        expression like `module.renderGoldV5 ||` followed by a single call site
        that invokes the resolved function. Verifying both ends independently
        would over-fit the test to one specific dispatcher shape; instead we
        require both (a) the renderGoldV5 token in the fallback chain and
        (b) the absence of the v4 fallback elsewhere."""
        src = _read(MAIN_PATH)
        assert "renderGoldV5" in src, "main.js dispatcher chain must reference renderGoldV5"
        # Old v4 dispatcher reference must be removed (single, idempotent check).
        assert "module.renderGoldV4 ||" not in src


class TestGoldV5ApiWiring:
    """The page must not call a non-existent API client method (P0: before
    this fix, api.getGoldWorkbench was undefined and every load hit a
    TypeError → only the error hero rendered)."""

    def test_api_exports_getGoldWorkbench(self):
        src = _read(API_PATH)
        assert "getGoldWorkbench(options = {})" in src
        assert '"/gold/workbench"' in src

    def test_api_exports_getGoldWorkbenchCharts(self):
        src = _read(API_PATH)
        assert "getGoldWorkbenchCharts(snapshotId, options = {})" in src
        # URL is built as a template literal with the snapshot_id encoded.
        assert "`/gold/workbench/charts/${encodeURIComponent(snapshotId)}`" in src

    def test_page_uses_api_gold_workbench_not_v3_adapter(self):
        src = _read(JS_PATH)
        assert "api.getGoldWorkbench({" in src, (
            "loadData() must call the workbench endpoint (rich V5 shape)"
        )
        assert "api.getGoldWorkbenchCharts(" in src

    def test_page_progressively_loads_core_charts_and_derivatives(self):
        src = _read(JS_PATH)
        assert "loadDerivativesEnhancement" in src
        assert "refreshGoldCore" in src
        assert "waitForPrecomputeTask" in src
        assert "renderGoldCharts(data, signal)" in src
        assert 'document.querySelector(".gold-contract-ref")' in src

    def test_page_background_work_is_abortable(self):
        src = _read(JS_PATH)
        assert "api.getGoldWorkbench({ force, signal" in src
        assert "api.getGoldDerivatives({ signal" in src
        assert "api.precomputeHint({" in src
        assert "}, { signal });" in src

    def test_chart_grid_gated_on_chart_token(self):
        """Charts must only render when chart_series_or_chart_token carries a
        path AND count > 0 — otherwise 5 dead <canvas> elements appear on
        every error/cold load with no user-visible message."""
        src = _read(JS_PATH)
        assert "hasChartSeries" in src
        assert "renderChartGridEmptyState" in src
        assert "chartToken.count" in src

    def test_render_gold_v5_returns_controller(self):
        """renderGoldV5 must return a controller object so the SPA router
        (main.js normalizeController) calls unmount() on navigation."""
        src = _read(JS_PATH)
        assert "return { unmount };" in src

    def test_hero_subtitle_distinguishes_neutral_from_degraded(self):
        """A healthy snapshot with no active macro scenario must show the
        neutral label, not the degraded one — the V5 hero used to fall back
        to DATA_DEGRADED for every empty scenario list."""
        src = _read(JS_PATH)
        assert "MACRO_NEUTRAL" in src
        assert "snapshotOk" in src


class TestGoldV5Css:
    def test_css_block_appended(self):
        css = _read(CSS_PATH)
        assert "=== gold-allocation v5" in css, (
            "styles.css must contain a v5 design block as final section"
        )

    def test_css_uses_dash_repeat_pattern(self):
        """Spec §2.2 mandates grid-template-columns: repeat(2, ...)."""
        css = _read(CSS_PATH)
        # locate v5 block
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert "grid-template-columns: repeat(2," in block

    def test_chart_grid_has_no_wide_modifier(self):
        css = _read(CSS_PATH)
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert ".gold-chart-card.is-wide" not in block

    def test_css_has_governance_repeat_4(self):
        """Spec §2.5: governance grid is repeat(4, 1fr). 2026-08-27
        §13.2 #3 cleanup moved the shared governance ledger base +
        .governance-ledger--gold variant into editorial.css; the legacy
        body[data-page="gold-allocation"] .gold-governance CSS block
        in styles.css is gone. We assert the contract via editorial.css
        now."""
        css = _read(REPO_ROOT / "app" / "static" / "editorial.css")
        assert ".governance-ledger--gold .governance-ledger__grid" in css, (
            "editorial.css must own the .governance-ledger--gold variant grid"
        )
        # The base class locks repeat(4, minmax(0, 1fr)) as the default
        # for variants that don't override gridCols.
        assert ".governance-ledger__grid {" in css
        base_match = re.search(
            r"\.governance-ledger__grid\s*\{[^}]*repeat\(4,\s*minmax\(0,\s*1fr\)\)",
            css,
            re.DOTALL,
        )
        assert base_match, (
            ".governance-ledger__grid base class must default to "
            "repeat(4, minmax(0, 1fr)) per spec §2.5"
        )


class TestGoldV5VegasComposition:
    """The VEGAS tunnel's short line is EMA12, not the raw close price.

    Canonical definition lives on the analysis page (analysis.js:1551 —
    EMA12 + 快轨 144/169 + 慢轨 576/676, with no price series) and in the
    知识百科 VEGAS entry, which reads EMA12 crossing 快轨/慢轨 as the signal.
    The gold page was the only VEGAS renderer that substituted priceSeries
    for EMA12, which made its short line a spiky close plot instead of the
    documented momentum line.
    """

    @staticmethod
    def _vegas_block() -> str:
        src = _read(JS_PATH)
        start = src.index('renderInto("vegas", {')
        end = src.index('renderInto("macd", {')
        assert start < end, "vegas chart must be rendered before the MACD chart"
        return src[start:end]

    def test_vegas_plots_ema12(self):
        block = self._vegas_block()
        assert 'lineDataset("EMA12", emaSeries(candles, 12)' in block, (
            "VEGAS short line must be EMA12 (analysis.js:1551 parity)"
        )
        assert 'getSeriesColor("EMA12")' in block, (
            "VEGAS EMA12 must use the registered --series-ema-short colour"
        )

    def test_vegas_does_not_plot_close_price(self):
        block = self._vegas_block()
        assert "priceSeries" not in block, (
            "VEGAS must not draw the raw close; price belongs to the TREND card"
        )
        assert 'lineDataset("XAUT"' not in block

    def test_vegas_keeps_all_four_tunnel_rails(self):
        block = self._vegas_block()
        for period in (144, 169, 576, 676):
            assert f"emaSeries(candles, {period})" in block, (
                f"VEGAS tunnel must keep EMA{period}"
            )

    def test_price_card_still_plots_close(self):
        """Guard the guard: the TREND card must keep the XAUT close series, so
        the EMA12 swap above stays scoped to the VEGAS card."""
        src = _read(JS_PATH)
        block = src[src.index('renderInto("price", {') : src.index('renderInto("vegas", {')]
        assert 'lineDataset("XAUT", priceSeries' in block


class TestGoldV5AmountCurrency:
    """Amounts must carry the policy's currency, not a hard-coded 元.

    The configured policy reports in USD (``gold_policy_versions.base_currency``
    is "USD"), but ``money()`` appended 元 unconditionally, so the SPOT DCA card
    rendered a USD 500 base order as "500 元" — a ~7x misstatement of the action
    the user is being told to take.
    """

    @staticmethod
    def _money_helpers() -> str:
        src = _read(JS_PATH)
        start = src.index("const CURRENCY_LABELS")
        end = src.index("// ----- Subtitle")
        assert start < end, "money helpers must precede the subtitle helpers"
        return src[start:end]

    @staticmethod
    def _run(amount: float, currency) -> str:
        import json
        import shutil
        import subprocess

        if shutil.which("node") is None:
            import pytest

            pytest.skip("node not available")
        args = f"{json.dumps(amount)}, 0, {json.dumps(currency)}"
        script = (
            # gold_v5 imports formatNumber from core/dom.js; stub it so the
            # helpers run standalone.
            "const formatNumber = (value, digits) => Number(value).toFixed(digits);\n"
            + TestGoldV5AmountCurrency._money_helpers()
            + f"\nconsole.log(JSON.stringify(money({args})));\n"
        )
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=30, check=False
        )
        assert result.returncode == 0, f"node failed: {result.stderr}"
        import json as _json

        return _json.loads(result.stdout.strip())

    def test_usd_policy_amount_is_not_labelled_as_yuan(self):
        assert self._run(500, "USD") == "500 USD"

    def test_cny_still_uses_the_yuan_label(self):
        assert self._run(500, "CNY") == "500 元"
        assert self._run(500, "rmb") == "500 元"

    def test_missing_amount_stays_a_dash(self):
        assert self._run(None, "USD") == "—"

    def test_currency_comes_from_the_payload(self):
        """The unit must be read from the policy, not defaulted in the helper."""
        src = _read(JS_PATH)
        assert "data?.portfolio?.base_currency" in src, (
            "renderSpotDca must read the policy currency from portfolio.base_currency"
        )
        assert "renderRecommendRow(base, dip, currency)" in src
        assert "renderFormulaBox(base, dip, currency)" in src

    def test_money_has_no_hardcoded_yuan_suffix(self):
        body = self._money_helpers()
        assert "} 元`" not in body, (
            "money() must not append 元 unconditionally; only CNY/RMB map to 元"
        )


class TestGoldPolicyForm:
    """The workbench setup_required empty state must offer a working write
    path on the same page — previously it pointed at a flow that did not
    exist ("请先在策略页配置"), so a lost policy row was unrecoverable."""

    def test_no_dead_strategy_page_pointer(self):
        src = _read(JS_PATH)
        assert "请先在策略页配置" not in src

    def test_form_renders_with_setup_hint(self):
        src = _read(JS_PATH)
        assert "gold-policy-form" in src
        assert "保存即追加新版本" in src

    def test_form_posts_and_reloads(self):
        src = _read(JS_PATH)
        assert "api.saveGoldPolicy(" in src
        assert "await loadData({ force: true })" in src

    def test_numeric_inputs_allow_decimals(self):
        src = _read(JS_PATH)
        assert src.count('step="any"') >= 1, (
            "policy money inputs must carry step=any (type=number defaults "
            "to step=1 and rejects decimals, cf. spot_price lesson)"
        )

    def test_api_exports_saveGoldPolicy(self):
        src = _read(API_PATH)
        assert "saveGoldPolicy(payload, options = {})" in src
        assert '"/gold/policy"' in src

    def test_form_styles_exist(self):
        css = _read(CSS_PATH)
        assert ".gold-policy-form" in css
        assert ".gold-policy-actions" in css
