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


def test_gold_page_h1_legacy_class_is_fully_removed() -> None:
    """2026-08-27 §13.2 #2: the legacy `.gold-page-h1` class must not appear
    in CSS, JS, or page sources. Display styling falls back to the shared
    `page-display-title` class (see editorial.css §7.1)."""
    offenders: list[str] = []

    css_files = [
        ROOT / "app/static/styles.css",
        ROOT / "app/static/editorial.css",
    ]
    for css in css_files:
        text = css.read_text(encoding="utf-8")
        # Allow comments mentioning the legacy class as historical note.
        # Strip /* ... */ comments for a code-only check.
        import re as _re
        code = _re.sub(r"/\*.*?\*/", "", text, flags=_re.DOTALL)
        if "gold-page-h1" in code:
            offenders.append(str(css))

    page_sources = [
        PAGES / "gold_v5.js",
        PAGES / "btc_derivatives.js",
        PAGES / "knowledge.js",
        PAGES / "strategy/index.js",
    ]
    for source_path in page_sources:
        text = source_path.read_text(encoding="utf-8")
        if "gold-page-h1" in text:
            offenders.append(str(source_path))

    assert not offenders, (
        f"`.gold-page-h1` legacy class still present in: {offenders}"
    )


def test_macro_calendar_and_analysis_use_page_display_title() -> None:
    """2026-08-27 §13.2 #2: hero H2 in macro_calendar and analysis must
    adopt the shared `page-display-title` class to align with the other
    pages (btc-derivatives, ai-strategy, knowledge-base, gold-allocation)."""
    for page_name, expected_phrase in [
        ("macro_calendar.js", "page-display-title"),
        ("analysis.js", "page-display-title"),
    ]:
        text = (PAGES / page_name).read_text(encoding="utf-8")
        assert expected_phrase in text, (
            f"{page_name} should reference {expected_phrase} for the hero H2"
        )


def test_strategy_page_loader_combines_explicit_and_shared_asset_versions() -> None:
    source = (ROOT / "app/static/main.js").read_text(encoding="utf-8")

    assert 'loadPageModule("./pages/strategy.js?v=opportunity-matrix-v2")' in source
    assert 'path.includes("?") ? "&" : "?"' in source
    assert "assetVersion.slice(1)" in source


def test_knowledge_reference_layout_collapses_before_it_overflows() -> None:
    # 2026-08-27 §13.2 #7: 17→6 breakpoint consolidation rewrote @media
    # entries. The collapse contract itself is unchanged: knowledge-workspace
    # defines a 220px rail + 1fr flow at the desktop default, then a
    # narrower column under the small-desktop (1180px) breakpoint.
    assert 'body[data-page="knowledge-base"] .knowledge-workspace' in EDITORIAL
    assert "grid-template-columns: 220px minmax(0, 1fr)" in EDITORIAL
    assert 'body[data-page="knowledge-base"] .knowledge-reference-rail' in EDITORIAL

    # The collapse lives at the small-desktop tier (1180px). Confirm that a
    # 1180-or-narrower media block contains the collapse selector.
    collapse_idx = EDITORIAL.find(
        'body[data-page="knowledge-base"] .knowledge-workspace'
    )
    # The collapse rule emits `grid-template-columns: minmax(0, 1fr)` (rail
    # hidden) under the 1180px media block.
    collapse_block_idx = EDITORIAL.find(
        "grid-template-columns: minmax(0, 1fr)",
        collapse_idx,
    )
    assert collapse_block_idx != -1, (
        "knowledge workspace must collapse to single column at narrow viewport"
    )

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
    shared = (Path(__file__).resolve().parents[1] / "app/static/ui/governanceLedger.js").read_text(
        encoding="utf-8"
    )

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
    start = source.index("function renderShellFallback(message, pending = false)")
    end = source.index("function hasRenderedMonitoringShell()", start)
    fallback = source[start:end]

    assert 'id="monitoring-topbar"' in fallback
    assert "monitoring-summary-surface" in fallback
    assert 'id="monitoring-macro-grid"' in fallback
    assert "is-warming" in fallback
