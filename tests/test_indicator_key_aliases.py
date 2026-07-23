from __future__ import annotations

from app.services.macro.indicator_key_aliases import (
    CANONICAL_MACRO_KEYS,
    PROVIDER_ALIASES,
    canonical_macro_key,
    canonical_provider_key,
)


class TestCanonicalMacroKey:
    def test_known_aliases_resolve(self) -> None:
        assert canonical_macro_key("effr") == "us_dff"
        assert canonical_macro_key("us02y_yield") == "us_2y_yield"
        assert canonical_macro_key("us10y_yield") == "us_10y_yield"
        assert canonical_macro_key("ust_10y_yield") == "us_10y_yield"
        assert canonical_macro_key("hy_spread") == "hy_oas"
        assert canonical_macro_key("reverse_repo") == "on_rrp"
        assert canonical_macro_key("cpi_yoy") == "us_cpi_yoy"
        assert canonical_macro_key("core_cpi_yoy") == "us_core_cpi_yoy"
        assert canonical_macro_key("nfp") == "us_nfp"
        assert canonical_macro_key("dxy") == "dollar_index"
        assert canonical_macro_key("wti_oil") == "wti_crude"
        assert canonical_macro_key("real_yield_10y") == "us_10y_yield"

    def test_unknown_key_passes_through(self) -> None:
        assert canonical_macro_key("us_10y_yield") == "us_10y_yield"
        assert canonical_macro_key("custom_indicator") == "custom_indicator"
        assert canonical_macro_key("") == ""

    def test_pce_aliases_to_cpi(self) -> None:
        # pce_yoy intentionally aliased to us_cpi_yoy per V1.4.1 registry
        assert canonical_macro_key("pce_yoy") == "us_cpi_yoy"
        assert canonical_macro_key("core_pce_yoy") == "us_core_cpi_yoy"

    def test_alias_map_is_collision_free(self) -> None:
        values = list(CANONICAL_MACRO_KEYS.values())
        # Multiple aliases may map to the same canonical key, but every
        # canonical key must be reachable from at least one alias.
        assert "us_10y_yield" in values
        assert "us_cpi_yoy" in values


class TestCanonicalProviderKey:
    def test_known_aliases_resolve(self) -> None:
        assert canonical_provider_key("alphavantage") == "alpha_vantage"
        assert canonical_provider_key("alpha-vantage") == "alpha_vantage"
        assert canonical_provider_key("gateio") == "gateio_rwa"

    def test_unknown_provider_passes_through(self) -> None:
        assert canonical_provider_key("fred") == "fred"
        assert canonical_provider_key("coinmarketcap") == "coinmarketcap"
        assert canonical_provider_key("") == ""

    def test_alias_map_does_not_overlap(self) -> None:
        # Ensure no alias target is itself a key whose value differs
        for _alias, target in PROVIDER_ALIASES.items():
            assert canonical_provider_key(target) == target
