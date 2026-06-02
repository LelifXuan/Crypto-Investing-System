from __future__ import annotations

CANONICAL_MACRO_KEYS: dict[str, str] = {
    "effr": "us_dff",
    "us02y_yield": "us_2y_yield",
    "us10y_yield": "us_10y_yield",
    "ust_10y_yield": "us_10y_yield",
    "us10y_2y_spread": "us_10y_2y_spread",
    "us10y_3m_spread": "us_10y_3m_spread",
    "hy_spread": "hy_oas",
    "reverse_repo": "on_rrp",
    "cpi_yoy": "us_cpi_yoy",
    "cpi_mom": "us_cpi_yoy",
    "core_cpi_yoy": "us_core_cpi_yoy",
    "core_cpi_mom": "us_core_cpi_yoy",
    "nfp": "us_nfp",
    "unemployment_rate": "us_unemployment_rate",
    "dxy": "dollar_index",
    "wti_oil": "wti_crude",
    "ism_manufacturing": "ism_mfg_pmi",
    "ism_services": "ism_srv_pmi",
    "pce_yoy": "us_cpi_yoy",
    "core_pce_yoy": "us_core_cpi_yoy",
    "real_yield_10y": "us_10y_yield",
}

PROVIDER_ALIASES: dict[str, str] = {
    "alphavantage": "alpha_vantage",
    "alpha-vantage": "alpha_vantage",
    "gateio": "gateio_rwa",
}


def canonical_macro_key(key: str) -> str:
    return CANONICAL_MACRO_KEYS.get(key, key)


def canonical_provider_key(key: str) -> str:
    return PROVIDER_ALIASES.get(key, key)
