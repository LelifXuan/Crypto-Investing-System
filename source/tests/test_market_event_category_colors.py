from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_macro_and_regulatory_categories_use_distinct_semantic_tones():
    page = (ROOT / "app/static/pages/market_events.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

    assert 'data-event-category="${eventCategoryKey(item.category)}"' in page
    assert '.status-chip[data-event-category="macro"]' in css
    assert '.status-chip[data-event-category="regulatory"]' in css
    assert "background: var(--info-soft)" in css
    assert "background: var(--accent-soft)" in css
