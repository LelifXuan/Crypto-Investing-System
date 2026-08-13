"""Static guards for the knowledge reference workspace redesign."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "knowledge.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_knowledge_page_uses_reference_workspace_structure() -> None:
    assert 'class="knowledge-workspace"' in PAGE
    assert 'class="knowledge-index-rail"' in PAGE
    assert 'class="knowledge-content-column"' in PAGE
    assert 'class="knowledge-reference-rail"' in PAGE
    assert "研究参考手册" in PAGE


def test_term_cards_are_rendered_as_continuous_reading_entries() -> None:
    assert 'class="knowledge-entry-list knowledge-card-grid"' in PAGE
    assert "${pageRefs.length} 页可用" in PAGE
    assert "[data-toggle-label]" in PAGE
    assert "展开详情" not in PAGE
    assert "[...new Set(tags.map" in PAGE


def test_reference_workspace_obeys_reading_measure_and_responsive_rules() -> None:
    assert "grid-template-columns: 240px minmax(560px, var(--reading-measure))" in EDITORIAL
    assert "max-width: var(--reading-measure)" in EDITORIAL
    assert 'body[data-page="knowledge-base"] .knowledge-entry-list' in EDITORIAL
    assert "@media (max-width: 900px)" in EDITORIAL


def test_reference_filters_only_keep_section_and_level() -> None:
    assert 'data-dropdown-id="knowledge-section-filter"' in PAGE
    assert 'data-dropdown-id="knowledge-level-filter"' in PAGE
    assert 'data-dropdown-id="knowledge-page-filter"' not in PAGE
    assert 'data-dropdown-id="knowledge-family-filter"' not in PAGE
    assert "knowledgePageFilters" not in PAGE
    assert "familyOptions" not in PAGE
