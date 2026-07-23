#!/usr/bin/env python
"""Batch-add missing macro indicators to catalog and refresh policies."""

import yaml

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

# Load catalog
with open(ROOT / "app/monitoring/configs/indicator_catalog.yaml", "r", encoding="utf-8") as f:
    catalog = yaml.safe_load(f)

# All missing non-derived indicators for P1-02
NEW_INDICATORS = [
    # policy_rates
    ("sofr", "SOFR", "policy_rates", "fred", "raw_series", {"external_symbol": "SOFR"}, ["1d"], "macro_regime"),
    ("us03m_yield", "US 3M Yield", "policy_rates", "fred", "raw_series", {"external_symbol": "DGS3MO"}, ["1d"], "macro_regime"),
    ("us30y_yield", "US 30Y Yield", "policy_rates", "fred", "raw_series", {"external_symbol": "DGS30"}, ["1d"], "macro_regime"),
    # inflation_prices
    ("breakeven_5y", "5Y Breakeven", "inflation_prices", "fred", "raw_series", {"external_symbol": "T5YIE"}, ["1d"], "macro_regime"),
    ("breakeven_10y", "10Y Breakeven", "inflation_prices", "fred", "raw_series", {"external_symbol": "T10YIE"}, ["1d"], "macro_regime"),
    ("cpi_mom", "CPI MoM", "inflation_prices", "fred", "raw_series", {"external_symbol": "CPIAUCSL", "transform": "mom_pct"}, ["1d"], "macro_regime"),
    ("core_cpi_mom", "Core CPI MoM", "inflation_prices", "fred", "raw_series", {"external_symbol": "CPILFESL", "transform": "mom_pct"}, ["1d"], "macro_regime"),
    ("pce_yoy", "PCE YoY", "inflation_prices", "fred", "raw_series", {"external_symbol": "PCEPI", "transform": "yoy_pct"}, ["1d"], "macro_regime"),
    ("core_pce_yoy", "Core PCE YoY", "inflation_prices", "fred", "raw_series", {"external_symbol": "PCEPILFE", "transform": "yoy_pct"}, ["1d"], "macro_regime"),
    # growth_jobs
    ("average_hourly_earnings_yoy", "Avg Hourly Earnings YoY", "growth_jobs", "fred", "raw_series", {"external_symbol": "CES0500000003", "transform": "yoy_pct"}, ["1d"], "macro_regime"),
    ("initial_claims", "Initial Jobless Claims", "growth_jobs", "fred", "raw_series", {"external_symbol": "ICSA"}, ["1d"], "macro_regime"),
    ("continuing_claims", "Continuing Claims", "growth_jobs", "fred", "raw_series", {"external_symbol": "CCSA"}, ["1d"], "macro_regime"),
    ("jolts_openings", "JOLTS Job Openings", "growth_jobs", "fred", "raw_series", {"external_symbol": "JTSJOL"}, ["1d"], "macro_regime"),
    ("gdp_qoq", "GDP QoQ Annualized", "growth_jobs", "fred", "raw_series", {"external_symbol": "A191RL1Q225SBEA"}, ["1d"], "macro_regime"),
    # liquidity_credit
    ("fed_balance_sheet", "Fed Balance Sheet", "liquidity_credit", "fred", "raw_series", {"external_symbol": "WALCL"}, ["1d"], "macro_regime"),
    ("bank_reserves", "Bank Reserves", "liquidity_credit", "fred", "raw_series", {"external_symbol": "WRESBAL"}, ["1d"], "macro_regime"),
    ("m2", "M2 Money Supply", "liquidity_credit", "fred", "raw_series", {"external_symbol": "M2SL"}, ["1d"], "macro_regime"),
    ("ig_spread", "IG Credit Spread", "liquidity_credit", "fred", "raw_series", {"external_symbol": "BAMLC0A0CM"}, ["1d"], "macro_regime"),
    # cross_asset (market data)
    ("qqq", "QQQ", "cross_asset", "tiingo", "raw_series", {"external_symbol": "QQQ"}, ["1d"], "cross_asset_confirmation"),
    ("spy", "SPY", "cross_asset", "tiingo", "raw_series", {"external_symbol": "SPY"}, ["1d"], "cross_asset_confirmation"),
    ("hyg", "HYG", "cross_asset", "tiingo", "raw_series", {"external_symbol": "HYG"}, ["1d"], "cross_asset_confirmation"),
    ("btc_usdt", "BTC/USDT", "cross_asset", "gateio", "raw_series", {"external_symbol": "BTC_USDT"}, ["1d"], "crypto_market"),
    ("eth_usdt", "ETH/USDT", "cross_asset", "gateio", "raw_series", {"external_symbol": "ETH_USDT"}, ["1d"], "crypto_market"),
    ("eth_btc", "ETH/BTC", "cross_asset", "gateio", "raw_series", {"external_symbol": "ETH_BTC"}, ["1d"], "crypto_market"),
    ("usd_cny", "USD/CNY", "cross_asset", "openexchangerates", "raw_series", {"external_symbol": "CNY"}, ["1d"], "fx_rate"),
]

for ik, dn, fam, sp, sk, cp, stf, uc in NEW_INDICATORS:
    if any(r["indicator_key"] == ik for r in catalog["indicators"]):
        continue
    catalog["indicators"].append({
        "indicator_key": ik,
        "display_name": dn,
        "category": "macro",
        "family": fam,
        "source_provider": sp,
        "source_kind": sk,
        "calc_engine": "raw",
        "calc_params": cp,
        "supported_assets": ["global"],
        "supported_timeframes": stf,
        "output_fields": ["value"],
        "signal_states": ["rising", "neutral", "falling"],
        "default_thresholds": {},
        "use_cases": [uc],
        "is_enabled": True,
    })

with open(ROOT / "app/monitoring/configs/indicator_catalog.yaml", "w", encoding="utf-8") as f:
    yaml.dump(catalog, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"Catalog: {len(NEW_INDICATORS)} indicators added, total macro: {sum(1 for r in catalog['indicators'] if r.get('category')=='macro')}")

# Now add refresh policies
with open(ROOT / "app/monitoring/configs/refresh_policies.yaml", "r", encoding="utf-8") as f:
    policies = yaml.safe_load(f)

macro_pols = policies["refresh_policies"]["macro"]
existing_keys = {p["indicator_key"] for p in macro_pols}
added = 0
for ik, dn, fam, sp, sk, cp, stf, uc in NEW_INDICATORS:
    if ik in existing_keys:
        continue
    is_daily = "1d" in stf
    macro_pols.append({
        "indicator_key": ik,
        "scope_type": "global",
        "mode": "cron",
        "cron_expr": "37 8,14,20 * * 1-5" if is_daily else "42 8 * * 1-5",
        "timezone": "UTC",
        "priority": 7,
    })
    added += 1

with open(ROOT / "app/monitoring/configs/refresh_policies.yaml", "w", encoding="utf-8") as f:
    yaml.dump(policies, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"Policies: {added} added, total macro: {len(macro_pols)}")
