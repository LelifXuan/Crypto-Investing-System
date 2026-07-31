"""Static assertions for gold V5 frontend module — analysis-page visual alignment."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "app" / "static" / "pages" / "gold_v5.js"
TEMPLATE_PATH = REPO_ROOT / "app" / "templates" / "page.html"
CSS_PATH = REPO_ROOT / "app" / "static" / "styles.css"
MAIN_PATH = REPO_ROOT / "app" / "static" / "main.js"


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
    """The 5 chart cards must keep stable IDs for Chart.js subscription."""
    def test_price_id(self):
        assert "gold-chart-price" in _read(JS_PATH)
    def test_rsi_id(self):
        assert "gold-chart-rsi" in _read(JS_PATH)
    def test_bollinger_id(self):
        assert "gold-chart-bollinger" in _read(JS_PATH)
    def test_volume_id(self):
        assert "gold-chart-volume" in _read(JS_PATH)
    def test_drawdown_id(self):
        assert "gold-chart-drawdown" in _read(JS_PATH)


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
        # Old v4 dispatcher reference must be removed
        assert "module.renderGoldV4 ||" not in src
        assert "module.renderGoldV4 ||" not in src


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

    def test_css_has_is_wide_modifier(self):
        """Spec §2.2: price card uses .is-wide to span 2 columns."""
        css = _read(CSS_PATH)
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert ".gold-chart-card.is-wide" in block
        assert "grid-column: span 2" in block

    def test_css_has_governance_repeat_4(self):
        """Spec §2.5: governance grid is repeat(4, 1fr)."""
        css = _read(CSS_PATH)
        start = css.index("=== gold-allocation v5")
        block = css[start:]
        assert "repeat(4, minmax(0, 1fr))" in block
