from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import monitoring_dashboard
from app.services.monitoring_dashboard import MonitoringDashboardService


class FakeAnalysisBundleService:
    def __init__(self, repository) -> None:
        self.repository = repository

    async def get_bundle(self, instrument_id, timeframe, view_window):
        return SimpleNamespace(
            cache_state="fresh",
            candles=[
                SimpleNamespace(
                    ts_open=datetime(2026, 5, 14, tzinfo=UTC),
                    close=100,
                )
            ],
            core_indicator_series={
                "ema_20": [None, 95],
                "rsi_14": [None, 61],
                "macd_hist": [None, 2],
                "atr_14": [None, 4],
                "natr_14": [None, 1.2],
            },
            secondary_indicator_series={
                "adx_14": [None, 28],
                "plus_di": [None, 21],
                "minus_di": [None, 12],
                "obv": [None, 1000],
                "obv_slope": [None, 0.2],
                "obv_change_5": [None, 120],
                "kdj_j": [None, 50],
                "cci_20": [None, 80],
                "volume": [None, 10],
            },
        )

    async def refresh_bundle(self, instrument_id, timeframe, view_window):
        raise AssertionError("fresh analysis bundle should not refresh")


@pytest.mark.asyncio
async def test_monitoring_builds_technical_observations_from_analysis_bundle(monkeypatch) -> None:
    monkeypatch.setattr(monitoring_dashboard, "AnalysisBundleService", FakeAnalysisBundleService)
    service = MonitoringDashboardService(repository=object())

    items = await service._technical_observations_from_analysis_bundle(
        "btc-usdt-perp",
        "1h",
        datetime(2026, 5, 14, tzinfo=UTC),
    )

    by_key = {item["indicator_key"]: item for item in items}
    assert by_key["ema_20"]["signal_state"] == "bullish"
    assert by_key["rsi_14"]["signal_state"] == "strong"
    assert by_key["macd_hist"]["signal_state"] == "positive_hist"
    assert by_key["adx_14"]["signal_state"] == "strong_trend"
    assert by_key["ema_20"]["source_provider"] == "analysis_bundle"


def test_monitoring_source_status_is_structured_and_has_no_glassnode() -> None:
    service = MonitoringDashboardService(repository=object())

    payload = service._normalize_source_status(
        {
            "gateio": "online",
            "market_events": {"status": "no_data"},
            "glassnode": {"status": "not_configured"},
        }
    )

    assert payload["gateio"]["label"] == "Gate.io"
    assert payload["gateio"]["status"] == "online"
    assert payload["gateio"]["message"]
    assert "glassnode" not in payload
    assert payload["fred"]["status"] == "updating"
    assert payload["market_events"]["message"]
    assert payload["ashare_etf"]["label"] == "A股ETF"


def test_monitoring_frontend_has_source_status_and_no_mojibake() -> None:
    source = Path("app/static/pages/monitoring.js")
    content = source.read_text(encoding="utf-8")

    assert "信源状态" in content
    assert "source-status-root" in content
    assert "Glassnode" not in content
    for token in ["闁", "閳", "锟", "閸", "鐎", "閺", "鍋", "瀹", "鏆"]:
        assert token not in content
