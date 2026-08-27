"""Static guards for the design-handbook alignment pass."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
PAGES = ROOT / "app/static/pages"


def test_application_shell_owns_the_only_page_h1() -> None:
    template = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    assert '<h1 id="app-page-title">' in template

    page_sources = [
        PAGES / "btc_derivatives.js",
        PAGES / "gold_v5.js",
        PAGES / "knowledge.js",
        PAGES / "strategy/index.js",
    ]
    for source_path in page_sources:
        source = source_path.read_text(encoding="utf-8")
        assert "<h1" not in source, source_path
        assert "page-display-title" in source, source_path


def test_strategy_page_loader_combines_explicit_and_shared_asset_versions() -> None:
    source = (ROOT / "app/static/main.js").read_text(encoding="utf-8")

    assert 'loadPageModule("./pages/strategy.js?v=opportunity-matrix-v2")' in source
    assert 'path.includes("?") ? "&" : "?"' in source
    assert "assetVersion.slice(1)" in source


def test_knowledge_reference_layout_collapses_before_it_overflows() -> None:
    start = EDITORIAL.index("@media (max-width: 1599px)")
    end = EDITORIAL.index("@media (max-width: 1279px)", start)
    breakpoint = EDITORIAL[start:end]

    assert 'body[data-page="knowledge-base"] .knowledge-workspace' in breakpoint
    assert "grid-template-columns: 220px minmax(0, 1fr)" in breakpoint
    assert 'body[data-page="knowledge-base"] .knowledge-reference-rail' in breakpoint
    assert "max-width: 1fr" not in EDITORIAL


def test_knowledge_section_cards_use_editorial_tokens() -> None:
    start = EDITORIAL.index(
        'body[data-page="knowledge-base"] .knowledge-section-card {'
    )
    end = EDITORIAL.index("}", start)
    block = EDITORIAL[start:end]

    assert "background: var(--surface-elevated)" in block
    assert "border: 1px solid var(--border)" in block
    assert "rgba(99, 102, 241" not in block


def test_gold_governance_uses_the_shared_ledger_contract() -> None:
    """2026-08-27 §13.2 #3: gold-allocation no longer inlines the
    governance section template — it delegates to renderGovernanceLedger()
    from ui/governanceLedger.js. The legacy inline `class="card governance-ledger gold-governance"`
    assertion must NOT pass; we assert the contract via the new
    imports + delegate call."""
    source = (PAGES / "gold_v5.js").read_text(encoding="utf-8")
    shared = (Path(__file__).resolve().parents[1] / "app/static/ui/governanceLedger.js").read_text(encoding="utf-8")

    # Page must import + delegate to the shared renderer.
    assert "renderGovernanceLedger" in source
    assert 'variant: "gold"' in source
    # Legacy inline section template must NOT be reintroduced.
    assert 'class="card governance-ledger gold-governance"' not in source
    # The shared module owns the canonical structure / class names.
    assert "governance-ledger__head" in shared
    assert "governance-ledger__grid" in shared
    assert "governance-ledger__item" in shared
    assert "governance-ledger__label" in shared
    assert "governance-ledger__dot" in shared


def test_monitoring_warming_shell_keeps_stable_page_structure() -> None:
    source = (PAGES / "monitoring.js").read_text(encoding="utf-8")
    start = source.index("function renderShellFallback(message)")
    end = source.index("function hasRenderedMonitoringShell()", start)
    fallback = source[start:end]

    assert 'id="monitoring-topbar"' in fallback
    assert "monitoring-summary-surface" in fallback
    assert 'id="monitoring-macro-grid"' in fallback
    assert "is-warming" in fallback
