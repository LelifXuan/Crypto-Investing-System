from __future__ import annotations

from pathlib import Path

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.services.btc_derivatives.chart_builder import (
    REQUIRED_CHART_IDS,
    build_consolidated_dashboard_charts,
)


REPO = Path(__file__).resolve().parents[1]


def _inputs() -> dict:
    history = [
        {
            "timestamp": "2026-06-01",
            "spot_price": 58_000,
            "call_wall_strike": 60_000,
            "put_wall_strike": 45_000,
            "max_pain_strike": 55_000,
            "skew_25d": -0.02,
            "put_call_oi_ratio": 0.96,
            "put_call_volume_ratio": 1.02,
            "call_protection_cost_pct": 0.021,
            "put_protection_cost_pct": 0.023,
            "debit_spread_cost_pct": 0.013,
            "source_expiry": "2026-07-31",
            "source_dte": 60,
            "maturity_bucket": "60D",
            "rollover": False,
        }
    ]
    return {
        "price_history": [
            {
                "timestamp": "2026-06-01",
                "spot_price": 58_000,
                "aggregate_oi_usd": 13.1e9,
                "funding_zscore": -0.2,
            }
        ],
        "futures_rows": [
            {
                "exchange": "Deribit",
                "open_interest_usd": 4.8e9,
                "oi_change_pct": 0.09,
                "funding_rate": 0.00018,
                "basis_pct": 0.012,
            }
        ],
        "basis_points": [
            {
                "expiry": "2026-07-31",
                "basis_pct": 0.012,
                "annualized_basis_pct": 0.121,
            }
        ],
        "atm_iv_points": [{"expiry": "2026-07-31", "atm_iv": 0.66}],
        "strike_rows": [
            {
                "strike": 60_000,
                "call_oi": 2_300,
                "put_oi": 1_000,
                "call_iv": 0.60,
                "put_iv": 0.61,
            }
        ],
        "history": history,
        "spot_price": 58_000,
        "call_wall": 60_000,
        "put_wall": 45_000,
        "max_pain": 55_000,
    }


def test_consolidated_dashboard_contains_only_six_decision_charts() -> None:
    result = build_consolidated_dashboard_charts(**_inputs())

    assert set(result["charts"]) == REQUIRED_CHART_IDS == {
        "leverage_pressure_timeline",
        "exchange_crowding_snapshot",
        "term_structure",
        "strike_surface",
        "key_levels_history",
        "options_risk_premium_history",
    }
    assert not {
        "walls_history",
        "max_pain_history",
        "iv_smile",
        "oi_by_strike",
    } & set(result["charts"])


def test_merged_charts_keep_key_levels_and_strike_surface_series() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]

    assert [item["label"] for item in charts["key_levels_history"]["datasets"]] == [
        "Spot",
        "Call Wall",
        "Put Wall",
        "Max Pain",
    ]
    assert [item["label"] for item in charts["strike_surface"]["datasets"]] == [
        "Call OI",
        "Put OI",
        "Call IV",
        "Put IV",
    ]
    assert {item["label"] for item in charts["strike_surface"]["annotations"]} == {
        "Spot",
        "Call Wall",
        "Put Wall",
        "Max Pain",
    }


def test_leverage_timeline_contains_one_funding_z_series() -> None:
    chart = build_consolidated_dashboard_charts(**_inputs())["charts"][
        "leverage_pressure_timeline"
    ]

    funding_series = [item for item in chart["datasets"] if item["label"] == "Funding Z"]
    assert len(funding_series) == 1
    assert funding_series[0]["data"] == [-0.2]


def test_dashboard_schema_accepts_axes_layout_and_selection_metadata() -> None:
    result = build_consolidated_dashboard_charts(**_inputs())
    payload = {
        "generated_at": "2026-06-24T00:00:00Z",
        "underlying": "BTC",
        "cards": [],
        "futures": {"rows": [], "metrics": {}, "charts": result["charts"]},
        "options": {
            "selected_expiry": "2026-07-31",
            "expiries": ["2026-07-31"],
            "chain": [],
            "metrics": {},
            "walls": {},
            "max_pain": {},
            "charts": {},
        },
        "chart_layout": result["chart_layout"],
        "selection": {
            "expiry_mode": "constant_maturity",
            "maturity_bucket": "60D",
            "selected_expiry": "2026-07-31",
            "window": None,
            "strike_range_pct": "30",
        },
        "maturity_selection": {
            "expiry": "2026-07-31",
            "dte": 37,
            "target_dte": 60,
            "status": "ok",
        },
        "joint_analysis": {},
        "hedge_context": {},
        "data_quality": {},
    }

    validated = BtcDerivativesDashboardResponse.model_validate(payload)

    assert validated.chart_layout.cards["strike_surface"].span == 12
    assert (
        validated.chart_layout.cards["term_structure"].span
        + validated.chart_layout.cards["exchange_crowding_snapshot"].span
        == 12
    )
    assert (
        validated.chart_layout.cards["key_levels_history"].span
        + validated.chart_layout.cards["options_risk_premium_history"].span
        == 12
    )
    assert validated.futures.charts["leverage_pressure_timeline"].axes["y_price"].profile == "price"
    assert validated.selection.expiry_mode == "constant_maturity"


def test_futures_layout_prioritizes_crowding_chart_width() -> None:
    three_exchanges = _inputs()
    three_exchanges["futures_rows"] = [
        {**three_exchanges["futures_rows"][0], "exchange": exchange}
        for exchange in ("Deribit", "Binance", "OKX")
    ]
    three = build_consolidated_dashboard_charts(**three_exchanges)["chart_layout"]["cards"]
    assert three["exchange_crowding_snapshot"]["span"] == 8
    assert three["term_structure"]["span"] == 4

    four_exchanges = _inputs()
    four_exchanges["futures_rows"] = [
        {**four_exchanges["futures_rows"][0], "exchange": exchange}
        for exchange in ("Deribit", "Binance", "OKX", "Bybit")
    ]
    four = build_consolidated_dashboard_charts(**four_exchanges)["chart_layout"]["cards"]
    assert four["exchange_crowding_snapshot"]["span"] == 12
    assert four["term_structure"]["span"] == 12


def test_term_structure_keeps_basis_curves_when_futures_basis_is_available() -> None:
    charts = build_consolidated_dashboard_charts(**_inputs())["charts"]
    term = charts["term_structure"]
    datasets = {item["label"]: item["data"] for item in term["datasets"]}

    assert term["labels"] == ["2026-07-31"]
    assert datasets["年化 Basis"] == [0.121]
    assert datasets["Basis"] == [0.012]


# ---------------------------------------------------------------------------
# 2026-07-23: split the buggy "exchange_crowding_snapshot" mixed chart
# (mixed-axis confusion between venue names and date strings) into a
# per-venue table + a standalone 90D aggregate-OI line chart. The chart
# payload still exists in the API response (any non-page consumer can use
# it), but the page no longer renders it as a <canvas>.
# ---------------------------------------------------------------------------


def test_crowding_snapshot_no_longer_renders_as_chart() -> None:
    """The page JS must NOT dispatch renderSingleChart for the
    'exchange_crowding_snapshot' id any more — neither as a literal call
    nor as part of the chart-id list that renderChartSections iterates."""
    content = (REPO / "app" / "static" / "pages" / "btc_derivatives.js").read_text(encoding="utf-8")
    forbidden = (
        'renderSingleChart("exchange_crowding_snapshot")',
        "renderSingleChart('exchange_crowding_snapshot')",
        # Indirect dispatch via the chart-id list in any section.charts
        # array. The chart id must not appear in any string-literal
        # context that drives a renderSingleChart dispatch.
        '"exchange_crowding_snapshot"',
    )
    for pattern in forbidden:
        assert pattern not in content, (
            f"btc_derivatives.js still renders the buggy mixed chart "
            f"via {pattern!r}; replace with renderCrowdingTable + "
            f"renderAggregateOiChart."
        )


def test_btc_derivatives_exposes_render_crowding_table() -> None:
    """The page JS must expose a per-venue crowding table renderer and
    consume the per-venue cross-section. The function may be named
    renderFuturesTable or renderCrowdingTable — both are accepted. The
    contract is that the futures section renders a <table> populated
    from the cross-section payload, not a <canvas>."""
    content = (REPO / "app" / "static" / "pages" / "btc_derivatives.js").read_text(encoding="utf-8")
    has_crowding = "renderCrowdingTable" in content or "renderFuturesTable" in content
    assert has_crowding, (
        "btc_derivatives.js must expose a per-venue crowding table "
        "renderer (renderCrowdingTable or renderFuturesTable)"
    )
    # Match either `dashboard.futures.rows` or `futures?.rows` (optional chaining).
    has_rows_read = (
        "futures.rows" in content
        or "futures?.rows" in content
    )
    assert has_rows_read, (
        "the crowding renderer must read from dashboard.futures.rows "
        "(or futures?.rows with optional chaining); the API already "
        "returns the per-venue cross-section in this field"
    )


def test_btc_derivatives_exposes_aggregate_oi_90d_chart() -> None:
    """The page JS must define renderAggregateOiChart that consumes the
    existing leverage_pressure_timeline chart payload (the 聚合 OI
    dataset)."""
    content = (REPO / "app" / "static" / "pages" / "btc_derivatives.js").read_text(encoding="utf-8")
    assert "renderAggregateOiChart" in content, (
        "btc_derivatives.js must define renderAggregateOiChart for the "
        "new 90D aggregate-OI line chart"
    )
    assert "leverage_pressure_timeline" in content, (
        "renderAggregateOiChart must read from the existing "
        "leverage_pressure_timeline chart payload (aggregate_oi_usd series)"
    )


# ---------------------------------------------------------------------------
# 2026-07-23: cumulative cache for price_history. Each per-day row from
# binance_futures must be appended to the existing LiveSourceCache +
# DerivativesArchive so the time-series chart fills in gaps over time.
# ---------------------------------------------------------------------------


def test_collector_persists_price_history_to_cache() -> None:
    """LiveCollector must call cache.append_daily() for every per-day
    row in result.history, with a stable series_key so the row is
    deduped across re-runs."""
    from pathlib import Path
    import tempfile

    from app.services.btc_derivatives.sources.cache import LiveSourceCache
    from app.services.btc_derivatives.sources.collector import LiveCollector
    from app.services.btc_derivatives.sources.adapters import AdapterResult

    with tempfile.TemporaryDirectory() as tmp:
        cache = LiveSourceCache(root=Path(tmp))
        collector = LiveCollector(cache=cache)
        result = AdapterResult(provider="binance_futures")
        for day in ("2026-07-20", "2026-07-21", "2026-07-22"):
            result.history.append({
                "timestamp": day,
                "spot_price": 67000.0,
                "aggregate_oi_usd": 4_200_000_000.0,
                "funding_rate": 0.00018,
                "funding_zscore": 0.5,
                "provider": "binance_futures",
            })
        collector._persist_price_history([result])
        cached = cache.read_history()
        cached_days = {row.get("timestamp"): row for row in cached}
        assert set(cached_days) == {"2026-07-20", "2026-07-21", "2026-07-22"}, (
            f"expected 3 cached rows, got {list(cached_days)}"
        )
        for day, row in cached_days.items():
            assert row.get("series_key") == "binance_futures:BTC", (
                f"row for {day} missing series_key, got {row}"
            )


def test_collector_dedupes_price_history_by_day() -> None:
    """A second persist call with overlapping days must replace (not
    duplicate) the same day's row in the cache. The freshest value wins."""
    from pathlib import Path
    import tempfile

    from app.services.btc_derivatives.sources.cache import LiveSourceCache
    from app.services.btc_derivatives.sources.collector import LiveCollector
    from app.services.btc_derivatives.sources.adapters import AdapterResult

    with tempfile.TemporaryDirectory() as tmp:
        cache = LiveSourceCache(root=Path(tmp))
        collector = LiveCollector(cache=cache)

        r1 = AdapterResult(provider="binance_futures")
        r1.history.append({
            "timestamp": "2026-07-22", "spot_price": 67000.0,
            "aggregate_oi_usd": 4_200_000_000.0, "funding_rate": 0.00018,
            "funding_zscore": 0.5, "provider": "binance_futures",
        })
        collector._persist_price_history([r1])

        r2 = AdapterResult(provider="binance_futures")
        r2.history.append({
            "timestamp": "2026-07-22", "spot_price": 67500.0,
            "aggregate_oi_usd": 4_300_000_000.0, "funding_rate": 0.00020,
            "funding_zscore": 0.6, "provider": "binance_futures",
        })
        r2.history.append({
            "timestamp": "2026-07-23", "spot_price": 68000.0,
            "aggregate_oi_usd": 4_400_000_000.0, "funding_rate": 0.00022,
            "funding_zscore": 0.7, "provider": "binance_futures",
        })
        collector._persist_price_history([r2])

        cached = cache.read_history()
        days = sorted({row.get("timestamp") for row in cached})
        assert days == ["2026-07-22", "2026-07-23"], (
            f"expected 2 unique days after dedup, got {days}"
        )
        row_22 = next(r for r in cached if r.get("timestamp") == "2026-07-22")
        assert row_22.get("spot_price") == 67500.0, (
            f"expected 67500 (latest), got {row_22.get('spot_price')}"
        )


def test_collector_merges_price_history_with_cached() -> None:
    """When upstream returns a partial history, the merge function must
    combine fresh + cached to produce a complete time-series, with
    fresh values winning for overlapping days."""
    from pathlib import Path
    import tempfile

    from app.services.btc_derivatives.sources.cache import LiveSourceCache
    from app.services.btc_derivatives.sources.collector import LiveCollector
    from app.services.btc_derivatives.sources.adapters import AdapterResult

    with tempfile.TemporaryDirectory() as tmp:
        cache = LiveSourceCache(root=Path(tmp))
        collector = LiveCollector(cache=cache)

        old_result = AdapterResult(provider="binance_futures")
        for day in ("2026-07-18", "2026-07-19", "2026-07-20"):
            old_result.history.append({
                "timestamp": day, "spot_price": 66000.0,
                "aggregate_oi_usd": 4_100_000_000.0, "funding_rate": 0.0001,
                "funding_zscore": 0.0, "provider": "binance_futures",
            })
        collector._persist_price_history([old_result])

        new_result = AdapterResult(provider="binance_futures")
        for day in ("2026-07-21", "2026-07-22"):
            new_result.history.append({
                "timestamp": day, "spot_price": 67000.0,
                "aggregate_oi_usd": 4_200_000_000.0, "funding_rate": 0.00018,
                "funding_zscore": 0.5, "provider": "binance_futures",
            })

        merged = collector._merge_price_history(new_result.history)
        merged_days = sorted({row.get("timestamp") for row in merged})
        assert merged_days == [
            "2026-07-18", "2026-07-19", "2026-07-20",
            "2026-07-21", "2026-07-22",
        ], f"expected 5 days merged, got {merged_days}"


def test_collector_persists_price_history_to_archive() -> None:
    """LiveCollector must also push the latest daily row into the
    DerivativesArchive under data_type='daily_metrics' with the same
    series_key, so a cache rebuild can recover the most recent
    snapshot."""
    from pathlib import Path
    import shutil
    import tempfile

    from app.services.btc_derivatives.archive import DerivativesArchive
    from app.services.btc_derivatives.sources.cache import LiveSourceCache
    from app.services.btc_derivatives.sources.collector import LiveCollector
    from app.services.btc_derivatives.sources.adapters import AdapterResult

    tmp = tempfile.mkdtemp()
    try:
        cache = LiveSourceCache(root=Path(tmp))
        archive = DerivativesArchive(root=Path(tmp) / "archive")
        collector = LiveCollector(cache=cache, archive=archive)

        result = AdapterResult(provider="binance_futures")
        for day in ("2026-07-20", "2026-07-21", "2026-07-22"):
            result.history.append({
                "timestamp": day,
                "spot_price": 67000.0,
                "aggregate_oi_usd": 4_200_000_000.0,
                "funding_rate": 0.00018,
                "funding_zscore": 0.5,
                "provider": "binance_futures",
            })
        collector._persist_price_history([result])

        # Read only the daily_metrics archive rows; ignore other writes
        # the collector may have made for key_levels etc.
        archive_rows = archive.read_records(data_type="daily_metrics")
        assert archive_rows, (
            "expected at least one daily_metrics archive row, got 0"
        )
        # The most recent day must be the one persisted.
        latest_day = max(
            str(r.get("timestamp") or "") for r in archive_rows
        )
        assert latest_day == "2026-07-22", (
            f"expected archive to keep the latest day 2026-07-22, got {latest_day}"
        )
        # That row must carry the same series_key + an archive_captured_at stamp.
        latest_row = next(
            r for r in archive_rows
            if str(r.get("timestamp") or "") == latest_day
        )
        assert latest_row.get("series_key") == "binance_futures:BTC", (
            f"archive row missing series_key, got {latest_row}"
        )
        assert latest_row.get("archive_captured_at"), (
            f"archive row missing archive_captured_at stamp, got {latest_row}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
