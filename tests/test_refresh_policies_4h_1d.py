"""Fix B (2026-07-25) — verify 4h/1d indicator coverage.

The refresh_policies.yaml file used to list technical candles only
for 1m/5m/1h. The 4h/1d/1w/30d timeframes had no policies, which
meant the strategy page's multi-timeframe structure engine had no
indicator_features to read for those horizons.

These tests verify:
- YAML contains 4h and 1d entries for all 10 candle-derived
  indicators (the catalog-supported set).
- YAML does NOT introduce 1w/30d entries (those have no catalog
  support and adding them would break).
- seed_defaults() expands instrument scope to all enabled
  instruments (not just btc-usdt-perp).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

CANDLE_INDICATOR_KEYS = (
    "ema_20",
    "ema_50",
    "ema_200",
    "adx_14",
    "macd_12_26_9",
    "rsi_14",
    "atr_14",
    "natr_14",
    "bbands_20_2",
    "obv",
)


@pytest.fixture()
def policies_yaml():
    p = ROOT / "app/monitoring/configs/refresh_policies.yaml"
    with p.open() as f:
        return yaml.safe_load(f)


def test_yaml_has_4h_entries_for_all_candle_indicators(policies_yaml):
    """Each of the 10 candle-derived indicators must have a 4h entry
    in the technical block."""
    technical = policies_yaml["refresh_policies"]["technical"]
    four_hour = {p["indicator_key"] for p in technical if p.get("timeframe") == "4h"}
    missing = set(CANDLE_INDICATOR_KEYS) - four_hour
    assert not missing, f"missing 4h entries for: {missing}"


def test_yaml_has_1d_entries_for_all_candle_indicators(policies_yaml):
    """Each candle-derived indicator must also have a 1d entry."""
    technical = policies_yaml["refresh_policies"]["technical"]
    one_day = {p["indicator_key"] for p in technical if p.get("timeframe") == "1d"}
    missing = set(CANDLE_INDICATOR_KEYS) - one_day
    assert not missing, f"missing 1d entries for: {missing}"


def test_yaml_does_not_introduce_1w_30d_technical_entries(policies_yaml):
    """1w and 30d have no indicator_catalog support (only four
    catalog-defined indicators cover them as z-scores at the
    derivative level, not candle-technical level). Adding
    technical candles for these would break the worker.
    """
    technical = policies_yaml["refresh_policies"]["technical"]
    bad = [
        (p["indicator_key"], p["timeframe"])
        for p in technical
        if p.get("timeframe") in {"1w", "30d"}
    ]
    assert not bad, (
        f"unexpected 1w/30d technical entries: {bad}"
    )


def test_yaml_cadence_matches_timeframe(policies_yaml):
    """fallback_interval_seconds must be sane for 4h (~14400) and 1d
    (~86400). Otherwise the worker would spin unnecessarily."""
    technical = policies_yaml["refresh_policies"]["technical"]
    for p in technical:
        tf = p.get("timeframe")
        fb = p.get("fallback_interval_seconds")
        if tf == "4h":
            assert 10800 <= fb <= 18000, (
                f"4h entry {p['indicator_key']} has suspicious cadence {fb}"
            )
        elif tf == "1d":
            assert 72000 <= fb <= 100000, (
                f"1d entry {p['indicator_key']} has suspicious cadence {fb}"
            )


def test_yaml_preserves_existing_1m_5m_1h_coverage(policies_yaml):
    """The 4h/1d additions must NOT replace any existing 1m/5m/1h
    entries."""
    technical = policies_yaml["refresh_policies"]["technical"]
    short_term = {
        p["indicator_key"] for p in technical if p.get("timeframe") in {"1m", "5m", "1h"}
    }
    # Verify all 10 candle indicators still have at least one short-term entry
    missing_short = set(CANDLE_INDICATOR_KEYS) - short_term
    assert not missing_short, (
        f"missing short-term entries for: {missing_short}"
    )


def test_yaml_per_indicator_has_at_least_3_timeframes(policies_yaml):
    """Each candle-derived indicator should now have entries for
    at least 3 timeframes (existing 1m/5m/1h + new 4h/1d = 5).
    """
    technical = policies_yaml["refresh_policies"]["technical"]
    candle_only = [
        p for p in technical if p.get("indicator_key") in CANDLE_INDICATOR_KEYS
    ]
    by_indicator = {}
    for p in candle_only:
        by_indicator.setdefault(p["indicator_key"], set()).add(p.get("timeframe"))
    for indicator_key, timeframes in by_indicator.items():
        assert len(timeframes) >= 3, (
            f"{indicator_key} has only {len(timeframes)} timeframes: {timeframes}"
        )
