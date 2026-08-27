from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_research_registry_is_frozen_and_forbids_first_round_composite() -> None:
    registry = json.loads(
        (ROOT / "app/monitoring/configs/btc_volatility_research_registry.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert registry["status"] == "frozen"
    assert registry["canonical_strategy_effect"] == "none"
    assert registry["multiple_testing"]["first_round_composite_or_ml_allowed"] is False
    assert registry["source_policy"]["synthetic_backfill_allowed"] is False
    assert registry["source_policy"]["missing_value_policy"] == "data_insufficient"


def test_all_ordered_first_round_reports_exist() -> None:
    report_dir = ROOT / "docs/research/btc_volatility"
    expected = {
        "BTC_REALIZED_VOLATILITY_BASELINE.md",
        "BTC_IMPLIED_VOLATILITY_INDEX_RESEARCH.md",
        "BTC_IV_RV_RELATIONSHIP_RESEARCH.md",
        "BTC_VOLATILITY_TERM_STRUCTURE_RESEARCH.md",
        "BTC_OPTION_SKEW_RESEARCH.md",
        "BTC_VOL_SURFACE_TAIL_RESEARCH.md",
        "BTC_OPEN_INTEREST_VOLATILITY_RESEARCH.md",
        "BTC_FUNDING_VOLATILITY_RESEARCH.md",
        "BTC_LIQUIDATION_PRESSURE_RESEARCH.md",
        "BTC_FUTURES_BASIS_VOLATILITY_RESEARCH.md",
        "BTC_VOLATILITY_DATA_AVAILABILITY_MAP.md",
        "OPEN_QUESTIONS_BTC_NATIVE_VOLATILITY.md",
    }
    assert expected <= {path.name for path in report_dir.glob("*.md")}


def test_shadow_service_is_not_imported_by_canonical_strategy_modules() -> None:
    canonical = [
        ROOT / "app/services/strategy_signal/snapshot_builder.py",
        ROOT / "app/services/strategy_signal/strategy_generator.py",
        ROOT / "app/services/strategy_unified/unified_service.py",
        ROOT / "app/services/terminal_summary_engine.py",
    ]
    for path in canonical:
        assert "volatility_research" not in path.read_text(encoding="utf-8")


def test_legacy_ratio_is_not_described_as_true_percentile_in_new_contract() -> None:
    service = (ROOT / "app/services/volatility_research/service.py").read_text(encoding="utf-8")
    audit = (
        ROOT / "docs/research/btc_volatility/CURRENT_VOLATILITY_BASELINE_AUDIT.md"
    ).read_text(encoding="utf-8")
    assert "bollinger_bandwidth_empirical_percentile" in service
    assert "incorrectly described as percentile rank" in audit
    assert "unchanged_shadow_only" in service
    legacy = (
        ROOT / "app/services/strategy_signal/snapshot_builder.py"
    ).read_text(encoding="utf-8")
    assert 'vol_compression_formula_version"] = "legacy-bb-width-ratio-v1"' in legacy
    assert 'vol_compression_is_empirical_percentile"] = False' in legacy


def test_rest_contract_uses_decimal_strings_and_writer_gate() -> None:
    schema = (ROOT / "app/schemas/volatility_research.py").read_text(encoding="utf-8")
    endpoint = (
        ROOT / "app/api/v1/endpoints/volatility_research.py"
    ).read_text(encoding="utf-8")
    assert "value: str | None" in schema
    assert "get_db_writer_session" in endpoint
    assert 'integration_status="shadow"' in (
        ROOT / "app/services/volatility_research/service.py"
    ).read_text(encoding="utf-8")


def test_knowledge_distinguishes_legacy_ratio_from_empirical_percentile() -> None:
    knowledge = (ROOT / "app/static/core/knowledge.js").read_text(encoding="utf-8")
    assert "它不是 percentile rank" in knowledge
    assert "bollinger_bandwidth_empirical_percentile" in knowledge
    assert "shadow 指标不会改变仓位、杠杆或方向" in knowledge
