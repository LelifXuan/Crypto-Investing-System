from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAIL = (ROOT / "app/static/ui/contextRail.js").read_text(encoding="utf-8")
MONITORING = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
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


def test_both_pilots_mount_the_shared_context_rail() -> None:
    assert "mountContextRail" in MONITORING
    assert "monitoring-context-rail" in MONITORING
    assert "mountContextRail" in BTC
    assert "btc-context-rail" in BTC
    assert "regime: actualMacroRegime(macro)" in MONITORING
    assert 'value: "后台准备中"' in MONITORING
