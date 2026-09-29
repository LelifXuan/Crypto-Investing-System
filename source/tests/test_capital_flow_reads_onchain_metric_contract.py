"""P1-QNT-002: capital-flow direction reads the onchain metric contract.

INV-002 — an absolute-positive market metric cannot be interpreted as a
positive flow unless the metric itself represents a change. These tests pin:

- the metric payload contract (dict with value/quality/age, read via the
  shared ``read_metric`` helper, per-metric freshness + quality gates);
- ``CapitalFlowEngine`` direction coming only from change features;
- ``OnchainFeatureEngine`` deriving real change features from observation
  history instead of faking deltas from levels.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def _metric(value, *, age_seconds=3600.0, quality=0.9):
    return {
        "value": value,
        "signal_state": "neutral",
        "source_provider": "test",
        "quality_score": quality,
        "observation_ts": (NOW - timedelta(seconds=age_seconds)).isoformat(),
        "age_seconds": age_seconds,
    }


def _context(metrics=None, flows=None, flow_bias="unknown"):
    onchain_features = {
        "metrics": metrics or {},
        "capital_flow_inputs": flows or {},
        "data_status": "fresh",
    }
    return SimpleNamespace(
        market_data={"flow_bias": flow_bias},
        onchain_features=onchain_features,
        cache_meta={"cache_state": "fresh"},
    )


def _compute(metrics=None, flows=None, flow_bias="unknown"):
    from app.services.strategy_unified.capital_flow import CapitalFlowEngine

    return CapitalFlowEngine().compute({"1d": _context(metrics, flows, flow_bias)})


def test_capital_flow_reads_onchain_metric_contract():
    """The metrics payload is a dict-of-dicts; the reader applies the gates."""
    from app.services.onchain.metric_reader import read_metric

    metrics = {"stablecoin_total_mcap": _metric(5.0e10)}
    reading = read_metric(metrics, "stablecoin_total_mcap")
    assert reading.usable and reading.fresh
    assert reading.value == 5.0e10

    # The historical bug: raw numbers instead of payloads must fail closed.
    raw = read_metric({"stablecoin_total_mcap": 5.0e10}, "stablecoin_total_mcap")
    assert not raw.usable and raw.unusable_reason == "missing_or_invalid_payload"
    missing = read_metric({}, "stablecoin_total_mcap")
    assert not missing.usable


def test_case_a_positive_level_without_delta_is_not_inflow():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10), "dex_volume_24h": _metric(3.0e9)},
    )
    assert dimension.state == "DATA_INSUFFICIENT"
    assert dimension.bias == "NEUTRAL"
    assert dimension.score == 0.0
    assert any("不构成流向证据" in line or "缺少" in line for line in dimension.evidence)


def test_case_b_positive_delta_forms_inflow():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10)},
        flows={"stablecoin_change_7d_pct": 2.5},
    )
    assert dimension.state == "CAPITAL_INFLOW"
    assert dimension.bias == "LONG"


def test_case_c_negative_delta_forms_outflow():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10)},
        flows={"stablecoin_change_7d_pct": -1.4},
    )
    assert dimension.state == "CAPITAL_OUTFLOW"
    assert dimension.bias == "SHORT"


def test_case_d_stale_observation_cannot_back_direction():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10, age_seconds=10 * 86400.0)},
        flows={"stablecoin_change_7d_pct": 5.0},
    )
    assert dimension.bias == "NEUTRAL"
    assert dimension.state == "DATA_INSUFFICIENT"
    assert any("stale_observation" in line for line in dimension.evidence)


def test_case_e_low_quality_observation_degrades_to_neutral():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10, quality=0.2)},
        flows={"stablecoin_change_7d_pct": 5.0},
    )
    assert dimension.bias == "NEUTRAL"
    assert dimension.state == "DATA_INSUFFICIENT"
    assert any("low_quality" in line for line in dimension.evidence)


def test_small_delta_stays_neutral_with_direction_zero():
    dimension = _compute(
        metrics={"stablecoin_total_mcap": _metric(5.0e10)},
        flows={"stablecoin_change_7d_pct": 0.2},
    )
    assert dimension.state == "CAPITAL_NEUTRAL"
    assert dimension.bias == "NEUTRAL"


def test_text_flow_bias_is_diagnostic_only():
    dimension = _compute(flow_bias="inflow")
    assert dimension.bias == "NEUTRAL"
    assert dimension.state == "CAPITAL_NEUTRAL"


def _observation(key: str, ts: datetime, value: float) -> object:
    from app.db.models.market import IndicatorObservation

    return IndicatorObservation(
        observation_id=f"{key}-{ts.isoformat()}",
        dedupe_key=f"{key}-{ts.isoformat()}",
        indicator_key=key,
        category="onchain",
        observation_ts=ts,
        value_num=Decimal(str(value)),
        quality_score=Decimal("0.9"),
        signal_state="neutral",
        source_provider="test",
        value_json={},
    )


class _FakeRepository:
    def __init__(self, observations):
        self._observations = observations

    async def list_latest_observations_by_key(self, **kwargs):
        return self._observations


def test_feature_engine_derives_change_features_from_history():
    from app.services.onchain.feature_engine import OnchainFeatureEngine

    observations = []
    for days in range(0, 9):
        ts = NOW - timedelta(days=days)
        observations.append(_observation("stablecoin_total_mcap", ts, 100.0 + (8 - days)))
        observations.append(_observation("dex_volume_24h", ts, 1000.0))
    engine = OnchainFeatureEngine(_FakeRepository(observations))

    import asyncio

    read = asyncio.run(engine.build(now=NOW))
    inputs = read.features["capital_flow_inputs"]
    assert inputs["available"] is True
    # stablecoin went 100 → 108 across the sampled window; the 7d reference
    # point is the observation closest to exactly 7 days ago (value 101).
    assert inputs["stablecoin_change_7d_pct"] is not None
    assert abs(inputs["stablecoin_change_7d_pct"] - 100.0 * (108 / 101 - 1)) < 0.1
    assert inputs["stablecoin_change_1d_pct"] is not None
    assert abs(inputs["stablecoin_change_1d_pct"] - 100.0 * (1 / 107)) < 0.5
    # Flat series yields ~0 change, never a fabricated direction.
    assert abs(inputs["dex_volume_change_7d_pct"]) < 0.01
    # metrics remain latest-per-key payloads under the documented contract.
    latest = read.features["metrics"]["stablecoin_total_mcap"]
    assert latest["value"] == 108.0
    assert latest["age_seconds"] == 0
