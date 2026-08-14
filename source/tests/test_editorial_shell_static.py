from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO_ROOT / "app" / "templates" / "page.html").read_text(encoding="utf-8")
MAIN = (REPO_ROOT / "app" / "static" / "main.js").read_text(encoding="utf-8")
EDITORIAL = (REPO_ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_full_canvas_shell_contract_is_present() -> None:
    for selector_id in ("app-sidebar", "app-page-title", "app-page-context", "page-root"):
        assert f'id="{selector_id}"' in TEMPLATE
    assert "/static/editorial.css" in TEMPLATE
    assert "data-shell-action=\"toggle-sidebar\"" in TEMPLATE
    assert 'id="app-inspector"' not in TEMPLATE


def test_shared_back_to_top_control_is_available_on_every_page() -> None:
    assert 'class="app-back-top"' in TEMPLATE
    assert 'data-shell-action="back-to-top"' in TEMPLATE
    assert 'aria-label="返回页面顶部"' in TEMPLATE
    assert 'if (action === "back-to-top") scrollPageToTop();' in MAIN
    assert 'prefers-reduced-motion: reduce' in MAIN
    assert ".app-back-top {" in EDITORIAL
    assert "knowledge-back-top" not in TEMPLATE


def test_page_meta_is_the_shared_route_and_layout_registry() -> None:
    assert "const PAGE_META" in MAIN
    for page_id in (
        "monitoring-overview",
        "market-events",
        "macro-calendar",
        "market-analysis",
        "market-structure",
        "btc-derivatives",
        "ai-strategy",
        "ashare-etf",
        "gold-allocation",
        "knowledge-base",
    ):
        assert f'"{page_id}":' in MAIN
    assert "renderNavSkeleton(PAGE_META[pageId])" in MAIN
    assert "mountInspector" not in MAIN


def test_editorial_tokens_and_responsive_breakpoints_are_locked() -> None:
    required = {
        "--sidebar-width: 216px",
        "--sidebar-collapsed-width: 64px",
        "--topbar-height: 64px",
        "--reading-measure: 800px",
        "--accent: #66548e",
        "--info: #3e6f9f",
        "@media (max-width: 1279px)",
        "@media (max-width: 767px)",
    }
    for fragment in required:
        assert fragment in EDITORIAL


def test_shell_has_no_external_assets_or_native_select() -> None:
    assert "http://" not in TEMPLATE
    assert "https://" not in TEMPLATE
    assert "<select" not in TEMPLATE.lower()
