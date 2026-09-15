from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAIL = (ROOT / "app/static/ui/contextRail.js").read_text(encoding="utf-8")
MONITORING = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
MACRO = (ROOT / "app/static/pages/macro_calendar.js").read_text(encoding="utf-8")
EVENTS = (ROOT / "app/static/pages/market_events.js").read_text(encoding="utf-8")
BTC = (ROOT / "app/static/pages/btc_derivatives.js").read_text(encoding="utf-8")


def test_context_rail_fields_are_optional_and_have_no_fake_zero_default() -> None:
    for field in (
        "instrument",
        "primaryValue",
        "change",
        "timeframe",
        "regime",
        "marketRisk",
        "freshness",
        "sourceSummary",
    ):
        assert f"model.{field}" in RAIL
    assert 'value: "0"' not in RAIL
    assert "if (!present(input)) return null" in RAIL
    assert 'field("数据", model.freshness, "unavailable")' in RAIL
    assert 'field("信源", model.sourceSummary, "unavailable")' in RAIL


def test_requested_pages_omit_the_shared_context_rail() -> None:
    assert "mountContextRail" not in MONITORING
    assert "monitoring-context-rail" not in MONITORING
    assert "mountContextRail" not in MACRO
    assert "macro-context-rail" not in MACRO
    assert "mountContextRail" not in EVENTS
    assert "events-context-rail" not in EVENTS
    assert "mountContextRail" not in BTC
    assert "btc-context-rail" not in BTC
