"""CSS scope and rendered geometry guards for the shared desktop regression.

Component geometry uses the real stylesheets without network/data dependencies.
Full-page lifecycle and populated charts are covered by verify_pages + UI audit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "app/static"


def css_scopes(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Track block ancestry, rejecting orphan declarations and braces.

    Strings/comments are masked so braces in SVG data URLs do not affect scope.
    This deliberately checks structure, not CSS property semantics.
    """
    text = re.sub(r'/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: "\n" * m.group().count("\n") or " ", text, flags=re.S)
    stack: list[str] = []
    rules = []
    pending = ""
    for match in re.finditer(r"[^{};]+|[{};]", text):
        token = match.group()
        if token == "{":
            header = pending.strip()
            assert header, "Missing block selector"
            rules.append((header, tuple(stack)))
            stack.append(header)
            pending = ""
        elif token == "}":
            assert stack, "Unmatched closing brace"
            stack.pop()
            pending = ""
        elif token == ";":
            assert stack or pending.strip().startswith("@"), "Orphan CSS declaration"
            pending = ""
        else:
            pending += token
    assert not stack, f"Unclosed blocks: {stack}"
    assert not pending.strip(), "Unterminated CSS rule"
    return rules


@pytest.mark.parametrize("filename", ["styles.css", "editorial.css"])
def test_shared_css_has_balanced_scopes(filename):
    css_scopes((STATIC / filename).read_text(encoding="utf-8"))


def test_desktop_components_are_not_trapped_in_mobile_media():
    rules = css_scopes((STATIC / "styles.css").read_text(encoding="utf-8"))
    for selector in [".dropdown", ".page-guide-fab", ".page-guide-panel",
                     ".gold-chart-grid", ".gold-workbench-grid", ".strategy-scan-page"]:
        assert (selector, ()) in rules, f"{selector} has no unconditional base rule"


def test_legacy_warm_surface_palette_is_absent_from_shared_css():
    """Generic surfaces may not reintroduce the retired beige/brown palette."""
    css = "\n".join(
        (STATIC / filename).read_text(encoding="utf-8")
        for filename in ("styles.css", "editorial.css")
    )
    retired_fragments = (
        "rgba(183, 121, 31,",
        "rgba(175, 154, 123,",
        "rgba(148, 129, 101,",
        "rgba(219, 209, 194,",
        "rgba(247, 243, 236,",
        "rgba(255, 248, 237,",
        "rgba(255, 248, 235,",
    )
    assert not [fragment for fragment in retired_fragments if fragment in css]


def test_sidebar_small_text_uses_aa_contrast_token():
    css = (STATIC / "editorial.css").read_text(encoding="utf-8")
    assert ".app-sidebar-brand > div > span { color: var(--text-secondary);" in css
    assert re.search(
        r"\.editorial-nav-group h2\s*\{[^}]*color:\s*var\(--text-secondary\)",
        css,
        re.S,
    )
    assert re.search(
        r"\.editorial-nav a\s*\{[^}]*color:\s*var\(--text-secondary\)",
        css,
        re.S,
    )


@pytest.mark.parametrize("broken", ["}", ".a {", "color: red;", ".a {} padding: 2px; }"])
def test_scope_guard_rejects_malformed_css(broken):
    with pytest.raises(AssertionError):
        css_scopes(broken)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 2560, "height": 1440})
    page.set_content("""<!doctype html><html><body data-page="gold-allocation">
      <div class="app-shell">
        <aside class="app-sidebar">
          <nav class="editorial-nav">Navigation</nav>
          <div class="app-sidebar-guide"><button class="page-guide-fab">
            <svg viewBox="0 0 24 24"><path d="M5 4h10v16H5z"/></svg>
            <span>页面使用指南</span></button></div>
          <div class="app-sidebar-foot">系统在线</div>
        </aside>
        <main><div id="page-root">
          <section class="gold-cockpit-header"><section class="gold-workbench-grid">
            <article class="card gold-workbench-card">配置建议</article>
            <article class="card gold-workbench-card">合约参考</article>
          </section></section>
          <section class="gold-chart-grid">
            <article class="card gold-chart-card">EMA</article>
            <article class="card gold-chart-card">VEGAS</article>
            <article class="card gold-chart-card">MACD</article>
            <article class="card gold-chart-card">Volume</article>
            <article class="card gold-chart-card">BOLL</article>
            <article class="card gold-chart-card">RSI</article>
          </section>
          <section class="card toolbar-grid">
            <button class="dropdown" data-dropdown-size="compact">BTC · Bitcoin</button>
            <button class="dropdown" data-dropdown-size="default">全部系统</button>
            <button class="dropdown" data-dropdown-size="compact" disabled>数据缺失</button>
            <button class="primary-button compact">刷新分析</button>
          </section>
          <article class="card macro-calendar-card is-collapsed">
            <div class="macro-calendar-head">
              <div class="macro-context-copy"><p class="eyebrow">CALENDAR</p>
                <h2 class="page-display-title">宏观日历</h2></div>
              <dl class="macro-metrics-grid">
                <div class="macro-inline-metric"><dt>已发布</dt><dd>15</dd></div>
                <div class="macro-inline-metric"><dt>待发布</dt><dd>16</dd></div>
              </dl><button class="primary-button compact">更新日历</button>
            </div></article>
        </div></main>
      </div><aside class="page-guide-panel" hidden><a href="#">Guide content</a></aside>
    </body></html>""")
    for filename in ["styles.css", "editorial.css"]:
        page.add_style_tag(path=str(STATIC / filename))
    # Style injection can start transitions from UA defaults. Measure the
    # settled component state, not the first frame of that artificial change.
    page.evaluate("""() => {
      document.body.getBoundingClientRect();
      for (const a of document.getAnimations()) {
        if (a.effect.getComputedTiming().iterations !== Infinity) a.finish();
      }
    }""")
    yield page
    page.close()


def test_controls_have_readable_colors_and_compact_heights(page):
    styles = page.locator(".dropdown").evaluate_all("""elements => elements.map(e => {
      const s = getComputedStyle(e);
      return {height: e.getBoundingClientRect().height, color: s.color,
              background: s.backgroundColor, opacity: s.opacity};
    })""")
    assert [s["height"] for s in styles] == [38, 40, 38]
    assert styles[0]["color"] == "rgb(33, 29, 43)"
    assert styles[0]["background"] == "rgb(245, 247, 250)"
    assert styles[2]["color"] == "rgb(95, 89, 104)"
    assert styles[2]["opacity"] == "1"
    assert page.locator(".primary-button").first.evaluate(
        "e => getComputedStyle(e).backgroundColor") == "rgb(64, 54, 95)"


@pytest.mark.parametrize("width, columns", [(2560, 2), (1280, 2), (900, 1), (390, 1)])
def test_gold_columns_and_spacing_at_breakpoints(page, width, columns):
    page.set_viewport_size({"width": width, "height": 1440})
    for selector in [".gold-workbench-grid", ".gold-chart-grid"]:
        grid = page.locator(selector)
        tracks = grid.evaluate("e => getComputedStyle(e).gridTemplateColumns.split(' ')")
        assert len(tracks) == columns
        assert grid.evaluate("e => getComputedStyle(e).gap") == "16px"
        boxes = grid.locator(":scope > article").evaluate_all(
            "es => es.map(e => e.getBoundingClientRect().toJSON())")
        assert abs(boxes[0]["width"] - boxes[1]["width"]) < 1
        if columns == 2:
            assert abs(boxes[0]["y"] - boxes[1]["y"]) < 1
            assert abs(boxes[1]["x"] - boxes[0]["right"] - 16) < 1
    gap = page.evaluate("""() => document.querySelector('.gold-chart-grid')
      .getBoundingClientRect().top - document.querySelector('.gold-cockpit-header')
      .getBoundingClientRect().bottom""")
    assert abs(gap - 24) < 1


def test_calendar_header_is_compact(page):
    page.evaluate("document.body.dataset.page = 'macro-calendar'")
    assert 80 <= page.locator(".macro-calendar-card").bounding_box()["height"] <= 88
    assert page.locator(".macro-context-copy h2").evaluate(
        "e => getComputedStyle(e).fontSize") == "20px"


def test_guide_stays_at_sidebar_foot_and_outside_sidebar(page):
    fab = page.locator(".page-guide-fab")
    assert fab.locator("svg").evaluate("e => getComputedStyle(e).fill") == "none"
    assert fab.bounding_box()["y"] > 1200
    foot = page.locator(".app-sidebar-foot").bounding_box()
    box = fab.bounding_box()
    assert 0 <= foot["y"] - box["y"] - box["height"] <= 12
    panel = page.locator(".page-guide-panel")
    assert panel.evaluate("e => getComputedStyle(e).display") == "none"
    panel.evaluate("e => e.hidden = false")
    for collapsed in [False, True]:
        page.evaluate("v => document.body.classList.toggle('is-sidebar-collapsed', v)", collapsed)
        box = panel.bounding_box()
        sidebar = page.locator(".app-sidebar").bounding_box()
        assert box["x"] >= sidebar["x"] + sidebar["width"]
        assert box["x"] + box["width"] <= 2560
    page.set_viewport_size({"width": 390, "height": 844})
    box = panel.bounding_box()
    assert box["x"] >= 16 and box["x"] + box["width"] <= 374


def test_structure_chart_surfaces_use_cool_neutral_palette(page):
    page.evaluate("document.body.dataset.page = 'market-structure'")
    page.locator("#page-root").evaluate("""root => {
      root.innerHTML = `<section class="structure-page">
        <article class="card structure-main-card">
          <div class="structure-chart-panel">
            <div class="structure-chart-shell"></div>
          </div>
        </article>
      </section>`;
    }""")
    expected_background = (
        "linear-gradient(rgba(251, 252, 254, 0.9), "
        "rgba(238, 242, 247, 0.82))"
    )
    for selector in [".structure-chart-panel", ".structure-chart-shell"]:
        styles = page.locator(selector).evaluate("""element => {
          const style = getComputedStyle(element);
          return { backgroundImage: style.backgroundImage, borderColor: style.borderColor };
        }""")
        assert styles["backgroundImage"] == expected_background
        assert styles["borderColor"] == "rgba(104, 117, 135, 0.16)"

    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    source = (STATIC / "pages/structure.js").read_text(encoding="utf-8")
    assert "#fff8ed" not in source
    assert "stroke: #fff8ed" not in css


def test_monitoring_low_confidence_uses_blue_companion_palette(page):
    page.evaluate("document.body.dataset.page = 'monitoring-overview'")
    page.locator("#page-root").evaluate("""root => {
      root.innerHTML = `<div class="monitoring-metric-rail">
        <article class="monitoring-topbar-item monitoring-confidence-item">
          <span>数据置信度</span>
          <span class="monitoring-confidence-chip" data-confidence-tone="warning">不足</span>
        </article>
      </div>`;
    }""")
    styles = page.locator(".monitoring-confidence-chip").evaluate("""element => {
      const style = getComputedStyle(element);
      return {
        background: style.backgroundColor,
        border: style.borderColor,
        color: style.color,
        boxShadow: style.boxShadow,
      };
    }""")
    assert styles == {
        "background": "rgb(230, 238, 246)",
        "border": "rgba(65, 89, 119, 0.14)",
        "color": "rgb(46, 87, 126)",
        "boxShadow": "none",
    }
