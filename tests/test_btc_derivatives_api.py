from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.btc_derivatives_sources import (
    LiveSnapshotEnvelope,
    NormalizedOptionQuote,
    NormalizedPerpSnapshot,
    ProviderStatus,
)
from app.services.btc_derivatives.chart_builder import REQUIRED_CHART_IDS
from app.services.btc_derivatives.live_service import (
    BtcDerivativesLiveService,
    btc_derivatives_live_service,
)
from app.services.btc_derivatives.service import BtcDerivativesService


def _client() -> TestClient:
    return TestClient(create_app(enable_lifespan=False))


def _live_envelope() -> LiveSnapshotEnvelope:
    now = datetime(2026, 6, 24, tzinfo=timezone.utc)
    options = []
    for expiry in ("2026-07-31", "2026-09-25"):
        for strike in (50_000, 55_000, 60_000, 65_000, 70_000):
            options.extend(
                [
                    NormalizedOptionQuote(
                        provider="deribit",
                        instrument=f"BTC-{expiry}-{strike}-C",
                        expiry=expiry,
                        strike=strike,
                        option_type="call",
                        bid=900,
                        ask=1_100,
                        mid=1_000,
                        mark_price=1_000,
                        underlying_price=61_000,
                        iv=0.6,
                        delta=0.25,
                        open_interest=100 + strike / 1_000,
                        volume_24h=20,
                        collected_at=now,
                    ),
                    NormalizedOptionQuote(
                        provider="deribit",
                        instrument=f"BTC-{expiry}-{strike}-P",
                        expiry=expiry,
                        strike=strike,
                        option_type="put",
                        bid=850,
                        ask=1_050,
                        mid=950,
                        mark_price=950,
                        underlying_price=61_000,
                        iv=0.62,
                        delta=-0.25,
                        open_interest=90 + (70_000 - strike) / 1_000,
                        volume_24h=18,
                        collected_at=now,
                    ),
                ]
            )
    return LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=now,
        options=options,
        perps=[
            NormalizedPerpSnapshot(
                provider="binance_futures",
                instrument="BTCUSDT",
                mark_price=61_000,
                index_price=60_990,
                funding_rate=0.0001,
                open_interest_contracts=100_000,
                open_interest_usd=6_100_000_000,
                volume_24h_usd=8_000_000_000,
                collected_at=now,
            )
        ],
        price_history=[
            {
                "timestamp": "2026-06-24",
                "spot_price": 61_000,
                "aggregate_oi_usd": 6_100_000_000,
                "funding_zscore": 0.5,
            }
        ],
        primary_option_provider="deribit",
        source_status=[
            ProviderStatus(
                provider="deribit",
                status="ok",
                capabilities=["options"],
            )
        ],
    )


def _wall_basis_envelope() -> LiveSnapshotEnvelope:
    now = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    options = []
    expiry = "2026-08-28"
    for strike in (50_000, 62_000, 72_000, 75_000):
        call_oi = 900 if strike == 75_000 else 100
        put_oi = 900 if strike == 50_000 else 100
        options.extend(
            [
                NormalizedOptionQuote(
                    provider="deribit",
                    instrument=f"BTC-{expiry}-{strike}-C",
                    expiry=expiry,
                    strike=strike,
                    option_type="call",
                    bid=900,
                    ask=1_100,
                    mid=1_000,
                    mark_price=1_000,
                    underlying_price=59_218.52,
                    iv=0.6,
                    delta=0.25,
                    open_interest=call_oi,
                    volume_24h=20,
                    collected_at=now,
                ),
                NormalizedOptionQuote(
                    provider="deribit",
                    instrument=f"BTC-{expiry}-{strike}-P",
                    expiry=expiry,
                    strike=strike,
                    option_type="put",
                    bid=850,
                    ask=1_050,
                    mid=950,
                    mark_price=950,
                    underlying_price=59_218.52,
                    iv=0.62,
                    delta=-0.25,
                    open_interest=put_oi,
                    volume_24h=18,
                    collected_at=now,
                ),
            ]
        )
    envelope = LiveSnapshotEnvelope(
        snapshot_state="stale",
        data_timestamp=now,
        options=options,
        perps=[
            NormalizedPerpSnapshot(
                provider="binance_futures",
                instrument="BTCUSDT",
                mark_price=59_218.52,
                index_price=59_218.52,
                funding_rate=0.0001,
                open_interest_contracts=100_000,
                open_interest_usd=5_900_000_000,
                volume_24h_usd=8_000_000_000,
                collected_at=now,
            )
        ],
        price_history=[
            {"timestamp": "2026-06-30T00:34:43.271173+00:00", "spot_price": 60_074.63},
            {"timestamp": "2026-07-01T09:00:00+00:00", "spot_price": 59_218.52},
        ],
        key_level_history=[
            {
                "timestamp": "2026-06-30T00:34:43.271173+00:00",
                "spot_price": 60_074.63,
                "call_wall_strike": 72_000,
                "put_wall_strike": 50_000,
                "max_pain_strike": 62_000,
                "source_provider": "deribit",
            },
            {
                "timestamp": "2026-07-01T08:30:00+00:00",
                "spot_price": 59_500,
                "call_wall_strike": 75_000,
                "put_wall_strike": 50_000,
                "max_pain_strike": 62_000,
                "source_provider": "deribit",
            },
        ],
        primary_option_provider="deribit",
    )
    return envelope


@pytest.fixture(autouse=True)
def stub_live_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = BtcDerivativesService()

    async def dashboard(**kwargs):
        return builder.build_dashboard(
            expiry=kwargs.get("expiry"),
            expiry_mode=kwargs.get("expiry_mode", "constant_maturity"),
            maturity_bucket=kwargs.get("maturity_bucket", "60D"),
            window=kwargs.get("window"),
            strike_range_pct=kwargs.get("strike_range_pct", "30"),
            live_snapshot=_live_envelope(),
        )

    monkeypatch.setattr(btc_derivatives_live_service, "dashboard", dashboard)


def test_dashboard_key_level_axis_uses_previous_utc_day_not_same_day_history() -> None:
    dashboard = BtcDerivativesService().build_dashboard(
        expiry_mode="constant_maturity",
        maturity_bucket="60D",
        live_snapshot=_wall_basis_envelope(),
    )

    signal = dashboard.options.metrics["options_wall_signal"]
    assert signal["comparison_basis"] == "previous_utc_day"
    assert signal["comparison_is_same_day"] is False
    assert signal["call_wall_previous"] == 72_000
    assert signal["call_wall_today"] == 75_000
    assert signal["call_wall_shift_pct"] == pytest.approx(0.0416666, rel=1e-4)
    assert signal["levels"]["call_wall"]["signal"] == "divergence_watch"
    assert signal["overall_signal"] != "wall_stable"


@pytest.mark.asyncio
async def test_live_dashboard_get_path_is_read_only_and_single_build() -> None:
    class Cache:
        def __init__(self) -> None:
            self.append_calls = 0

        def read_history(self) -> list[dict]:
            return []

        def append_daily(self, point: dict) -> list[dict]:
            self.append_calls += 1
            raise AssertionError("GET dashboard must not append daily history")

    class Archive:
        def append(self, **kwargs) -> None:
            raise AssertionError("GET dashboard must not write archive")

        def read_records(self, **kwargs) -> list[dict]:
            # Live dashboard read path consumes key-level history from the
            # archive but never writes; the test asserts the GET path is
            # read-only. An empty list is a valid response shape.
            return []

    class Collector:
        def __init__(self) -> None:
            self.cache = Cache()
            self.archive = Archive()

        async def snapshot(self, *, force: bool = False, allow_network: bool = True):
            assert force is False
            assert allow_network is False
            return _live_envelope()

    class CountingBuilder(BtcDerivativesService):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def build_dashboard(self, **kwargs):
            self.calls += 1
            return super().build_dashboard(**kwargs)

    collector = Collector()
    builder = CountingBuilder()
    service = BtcDerivativesLiveService(collector=collector, dashboard_builder=builder)

    dashboard = await service.dashboard(force=False)

    assert dashboard.snapshot_state == "live"
    assert builder.calls == 1
    assert collector.cache.append_calls == 0


def test_dashboard_endpoint_returns_stable_chart_first_contract() -> None:
    with _client() as client:
        response = client.get("/api/v1/btc-derivatives/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["underlying"] == "BTC"
    assert len(data["cards"]) == 3
    charts = {**data["futures"]["charts"], **data["options"]["charts"]}
    assert set(charts) == REQUIRED_CHART_IDS
    assert data["options"]["selected_expiry"] in data["options"]["expiries"]
    assert data["joint_analysis"]["direct_command"].startswith("none")
    assert data["data_quality"]["mode"] == "live"
    assert data["snapshot_state"] == "live"
    assert data["selection"]["expiry_mode"] == "constant_maturity"
    assert data["selection"]["maturity_bucket"] == "60D"
    assert data["chart_layout"]["cards"]["strike_surface"]["span"] == 12
    assert len(data["joint_analysis"]["inference_blocks"]) == 4
    assert len(data["options"]["key_level_cards"]) == 4
    assert (
        data["options"]["metrics"]["options_wall_signal"]["schema_version"]
        == "options_wall_signal.v1"
    )
    assert (
        data["joint_analysis"]["derivatives_axes"]["key_levels_axis"]["schema_version"]
        == "options_wall_signal.v1"
    )
    leverage = data["futures"]["charts"]["leverage_pressure_timeline"]
    levels = data["options"]["charts"]["key_levels_history"]
    surface = data["options"]["charts"]["strike_surface"]
    assert leverage["metadata"]["actual_window"] == "90D"
    assert levels["metadata"]["actual_window"] == "180D"
    assert surface["metadata"]["window_type"] == "current_cross_section"


def test_dashboard_allows_expiry_selection_and_enqueues_refresh() -> None:
    with _client() as client:
        initial = client.get("/api/v1/btc-derivatives/dashboard").json()
        expiry = initial["options"]["expiries"][-1]
        selected = client.get(
            "/api/v1/btc-derivatives/dashboard",
            params={"expiry": expiry, "expiry_mode": "fixed"},
        )
        refreshed = client.post(
            "/api/v1/btc-derivatives/dashboard/refresh",
            params={"expiry": expiry, "expiry_mode": "fixed"},
        )

    assert selected.status_code == 200
    assert selected.json()["options"]["selected_expiry"] == expiry
    assert refreshed.status_code == 202
    receipt = refreshed.json()
    assert receipt["scope"] == "btc_derivatives"
    assert receipt["status"] in {"queued", "running"}


def test_dashboard_refresh_wait_true_keeps_synchronous_diagnostic_path() -> None:
    with _client() as client:
        refreshed = client.post(
            "/api/v1/btc-derivatives/dashboard/refresh",
            params={"wait": "true"},
        )

    assert refreshed.status_code == 200
    assert refreshed.json()["snapshot_state"] == "live"


def test_dashboard_supports_window_constant_maturity_and_strike_range_params() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/btc-derivatives/dashboard",
            params={
                "expiry_mode": "constant_maturity",
                "maturity_bucket": "30D",
                "window": "7D",
                "strike_range_pct": "10",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["selection"]["expiry_mode"] == "constant_maturity"
    assert data["selection"]["maturity_bucket"] == "30D"
    assert data["selection"]["selected_expiry"] == data["options"]["selected_expiry"]
    assert data["selection"]["effective_expiry"] == data["options"]["selected_expiry"]
    assert data["selection"]["effective_dte"] > 0
    assert data["selection"]["selection_status"] == "ok"
    assert data["selection"]["window"] == "7D"
    assert data["selection"]["strike_range_pct"] == "10"
    assert data["maturity_selection"]["target_dte"] == 30
    leverage = data["futures"]["charts"]["leverage_pressure_timeline"]
    assert len(leverage["labels"]) <= 7
    assert "strike_surface" in data["options"]["charts"]


def test_hedge_plan_endpoint_returns_only_finite_risk_or_reduction_actions() -> None:
    payload = {
        "portfolio_type": "short_grid",
        "underlying": "BTC",
        "spot_price": 61_000,
        "grid_lower": 45_000,
        "grid_upper": 62_000,
        "net_notional_usd": 5_000,
        "hedge_budget_usd": 150,
        "preferred_expiry_bucket": "60D",
        "allow_debit_spread": True,
        "iv_state": "iv_high",
        "liquidity_state": "usable",
    }
    with _client() as client:
        response = client.post("/api/v1/btc-derivatives/hedge-plan", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["action"] in {
        "buy_call",
        "buy_put",
        "call_debit_spread",
        "put_debit_spread",
        "reduce_grid",
        "wait_due_to_high_iv",
        "wait_due_to_poor_liquidity",
        "no_hedge_needed",
        "data_insufficient",
    }
    serialized = str(data).lower()
    assert "naked_sell" not in serialized
    assert "ratio_spread" not in serialized
