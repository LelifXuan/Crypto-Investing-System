"""Static guards for the editorial supply-event timeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "app" / "static" / "pages" / "market_events.js").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")


def test_supply_calendar_is_grouped_as_a_year_timeline() -> None:
    assert "function supplyCalendarDateParts" in PAGE
    assert 'class="supply-calendar-year"' in PAGE
    assert 'class="supply-calendar-ledger"' in PAGE
    assert 'class="supply-calendar-track"' in PAGE
    assert 'class="supply-calendar-summary"' in PAGE
    assert "质押解锁日历" in PAGE
    assert 'className: "supply-calendar-toggle"' in PAGE


def test_supply_calendar_displays_quantity_and_current_value() -> None:
    assert "function supplyQuantityLabel" in PAGE
    assert "function usdValueLabel" in PAGE
    assert 'class="supply-calendar-amount"' in PAGE
    assert 'class="supply-calendar-value"' in PAGE
    assert 'class="supply-calendar-coverage"' in PAGE


def test_calendar_controls_use_compact_editorial_treatment() -> None:
    assert 'class="dropdown supply-calendar-filter"' in PAGE
    assert 'density: "compact"' in PAGE
    assert 'body[data-page="market-events"] .supply-calendar-filter {' in EDITORIAL
    assert "renderDisclosureToggle" in PAGE
    assert 'className: "supply-calendar-toggle"' in PAGE
    assert "--disclosure-fg: var(--white);" in EDITORIAL


def test_event_stream_refresh_is_primary_and_translation_is_secondary() -> None:
    assert 'id="events-translate-toggle" class="ghost-button compact"' in PAGE
    assert 'id="events-refresh" class="primary-button compact"' in PAGE
    assert 'body[data-page="market-events"] #events-translate-toggle {' in EDITORIAL
    assert 'body[data-page="market-events"] #events-refresh {' in EDITORIAL


def test_event_stream_heading_metrics_and_actions_share_one_context_bar() -> None:
    # 2026-09-04 (V2.3 workbench): the events-hero context bar was replaced
    # by the shared context rail (summary fields) plus a feed-card header
    # that visually binds translate/refresh to the panel they operate on.
    # The old separate metrics grid must NOT come back.
    assert 'id="events-context-rail"' in PAGE
    assert "mountContextRail" in PAGE
    assert '<section class="grid cols-4 events-metrics-grid"' not in PAGE
    assert 'class="events-feed-actions"' in PAGE
    assert 'id="events-refresh"' in PAGE
    assert 'id="events-translate-toggle"' in PAGE


def test_collapsing_calendar_keeps_feed_below_sticky_topbar() -> None:
    assert 'scrollIntoView({ block: "start", behavior: "smooth" })' in PAGE
    assert "scroll-margin-top: calc(var(--topbar-height) + var(--space-card));" in EDITORIAL


def test_snapshot_identifier_is_replaced_by_readable_evidence_copy() -> None:
    assert "function supplyEvidenceLabel" in PAGE
    assert 'return "白皮书快照"' in PAGE
    assert "snapshot ${escapeHtml" not in PAGE


def test_supply_timeline_has_desktop_and_mobile_layouts() -> None:
    assert 'body[data-page="market-events"] .supply-calendar-node {' in EDITORIAL
    assert "grid-template-columns: 78px 22px" in EDITORIAL
    assert "@media (max-width: 900px)" in EDITORIAL
    assert "background: var(--accent-ghost)" in EDITORIAL
