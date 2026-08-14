from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ALIAS_MAP = {
    "effr": ("us_dff",),
    "us02y_yield": ("us_2y_yield",),
    "us10y_yield": ("us_10y_yield", "ust_10y_yield"),
    "us10y_2y_spread": ("us_10y_2y_spread",),
    "cpi_yoy": ("us_cpi_yoy",),
    "core_cpi_yoy": ("us_core_cpi_yoy",),
    "nfp": ("us_nfp",),
    "unemployment_rate": ("us_unemployment_rate",),
    "hy_spread": ("hy_oas",),
    "reverse_repo": ("on_rrp",),
    "wti_oil": ("wti_crude",),
    "dxy": ("dollar_index",),
}

DERIVED_INDICATORS = {
    "us10y_2y_spread",
    "us10y_3m_spread",
    "real_yield_10y",
    "real_yield_5y",
    "cpi_mom",
    "core_cpi_mom",
    "pce_yoy",
    "core_pce_yoy",
    "pce_mom",
    "core_pce_mom",
    "average_hourly_earnings_yoy",
}

OPTIONAL_MARKET_INDICATORS = {
    "qqq",
    "spy",
    "hyg",
    "btc_usdt",
    "eth_usdt",
    "eth_btc",
    "usd_cny",
    "a_share_cashflow_etf_159201",
    "wti_oil",
}

IMPLEMENTED_SOURCES = {
    "fred",
    "bls",
    "bea",
    "federal_reserve",
    "treasury",
    "gateio",
    "gateio_rwa",
    "eastmoney",
    "eastmoney_quote",
    "coinmarketcap",
    "openexchangerates",
    "tiingo",
    "twelvedata",
    "alpha_vantage",
    "alphavantage",
    "tushare",
    "zhituapi",
    "agushuju",
}

SOURCE_ALIASES = {
    "alphavantage": "alpha_vantage",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _macro_map_ids(config: dict[str, Any]) -> set[str]:
    indicators = config.get("indicators", {})
    if isinstance(indicators, dict):
        return set(indicators)
    if isinstance(indicators, list):
        return {str(item.get("indicator_id") or item.get("indicator_key")) for item in indicators}
    return set()


def _catalog_entries(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = catalog.get("indicators") or []
    result: dict[str, dict[str, Any]] = {}
    for item in entries:
        key = item.get("indicator_key") or item.get("id")
        if key:
            result[str(key)] = item
    return result


def _policy_keys(policies: dict[str, Any]) -> set[str]:
    raw = policies.get("refresh_policies") or {}
    keys: set[str] = set()
    if isinstance(raw, dict):
        groups = raw.values()
    else:
        groups = raw
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            key = item.get("indicator_key") or item.get("indicator_id")
            if key:
                keys.add(str(key))
    return keys


def _candidate_keys(indicator_id: str) -> tuple[str, ...]:
    return (indicator_id, *ALIAS_MAP.get(indicator_id, ()))


def _resolve_key(indicator_id: str, known_keys: set[str]) -> str | None:
    for key in _candidate_keys(indicator_id):
        if key in known_keys:
            return key
    return None


def _sources_for(config: dict[str, Any], indicator_id: str) -> set[str]:
    item = (config.get("indicators") or {}).get(indicator_id, {})
    return {
        SOURCE_ALIASES.get(str(source.get("source")), str(source.get("source")))
        for source in item.get("sources", [])
        if isinstance(source, dict) and source.get("source")
    }


def _classify(
    indicator_id: str,
    *,
    macro_config: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    policy_keys: set[str],
) -> dict[str, Any]:
    catalog_key = _resolve_key(indicator_id, set(catalog))
    policy_key = _resolve_key(indicator_id, policy_keys)
    sources = _sources_for(macro_config, indicator_id)
    unknown_sources = sorted(source for source in sources if source not in IMPLEMENTED_SOURCES)

    if indicator_id in OPTIONAL_MARKET_INDICATORS:
        classification = "optional_market_source"
    elif indicator_id in DERIVED_INDICATORS:
        classification = "derived"
    elif catalog_key and policy_key and not unknown_sources:
        classification = "direct_fetch"
    elif unknown_sources:
        classification = "provider_not_implemented"
    elif catalog_key or policy_key:
        classification = "partially_configured"
    else:
        classification = "unknown"

    return {
        "indicator_id": indicator_id,
        "classification": classification,
        "catalog_key": catalog_key,
        "policy_key": policy_key,
        "sources": sorted(sources),
        "unknown_sources": unknown_sources,
        "aliases": list(ALIAS_MAP.get(indicator_id, ())),
    }


def build_report(repo: Path) -> dict[str, Any]:
    config_dir = repo / "app" / "monitoring" / "configs"
    macro_config = _read_json(config_dir / "macro_indicator_api_map.v1.json")
    catalog = _catalog_entries(_read_yaml(config_dir / "indicator_catalog.yaml"))
    policy_keys = _policy_keys(_read_yaml(config_dir / "refresh_policies.yaml"))

    records = [
        _classify(
            indicator_id,
            macro_config=macro_config,
            catalog=catalog,
            policy_keys=policy_keys,
        )
        for indicator_id in sorted(_macro_map_ids(macro_config))
    ]
    counts = Counter(item["classification"] for item in records)
    unknown = [item for item in records if item["classification"] == "unknown"]

    return {
        "macro_map_version": macro_config.get("version"),
        "total": len(records),
        "counts": dict(sorted(counts.items())),
        "unknown_count": len(unknown),
        "unknown": unknown,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit macro indicator source coverage.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--fail-on-unknown", action="store_true")
    args = parser.parse_args()

    report = build_report(args.repo.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if args.fail_on_unknown and report["unknown_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
