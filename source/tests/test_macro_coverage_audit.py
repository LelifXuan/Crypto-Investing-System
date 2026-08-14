from __future__ import annotations

from pathlib import Path

from scripts.audit_macro_coverage import build_report

ROOT = Path(__file__).resolve().parents[1]


def _record(report: dict, indicator_id: str) -> dict:
    return next(item for item in report["records"] if item["indicator_id"] == indicator_id)


def test_macro_coverage_audit_has_no_unknown_indicators() -> None:
    report = build_report(ROOT)

    assert report["total"] >= 40
    assert report["unknown_count"] == 0


def test_macro_coverage_audit_resolves_legacy_aliases() -> None:
    report = build_report(ROOT)

    assert _record(report, "effr")["catalog_key"] == "us_dff"
    assert _record(report, "us10y_yield")["catalog_key"] in {"us_10y_yield", "ust_10y_yield"}
    assert _record(report, "hy_spread")["aliases"] == ["hy_oas"]


def test_macro_coverage_audit_classifies_optional_market_sources() -> None:
    report = build_report(ROOT)

    assert _record(report, "qqq")["classification"] == "optional_market_source"
    assert _record(report, "spy")["classification"] == "optional_market_source"
    assert _record(report, "a_share_cashflow_etf_159201")["classification"] == (
        "optional_market_source"
    )
