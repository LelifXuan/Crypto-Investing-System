from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import monitoring_dashboard
from app.services.monitoring_dashboard import MonitoringDashboardService

BAD_TEXT_TOKENS = ("????", "\ufffd", "\u951f", "\u934b", "\u7039", "\u93c6")


class FakeAnalysisBundleService:
    def __init__(self, repository) -> None:
        self.repository = repository

    async def get_bundle(self, instrument_id, timeframe, view_window):
        return SimpleNamespace(
            cache_state="fresh",
            candles=[
                SimpleNamespace(
                    ts_open=datetime(2026, 5, 13, tzinfo=UTC),
                    close=105,
                ),
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
                "vwap_50": [None, 98],
                "vwap_100": [None, 96],
                "vwap_spread_pct": [None, 2.1],
                "vwap_slope_10": [None, 0.4],
                "kdj_j": [None, 50],
                "cci_20": [None, 80],
                "volume": [None, 10],
            },
        )

    async def refresh_bundle(self, instrument_id, timeframe, view_window):
        raise AssertionError("fresh analysis bundle should not refresh")


class DailyOldAnalysisBundleService(FakeAnalysisBundleService):
    async def get_bundle(self, instrument_id, timeframe, view_window):
        payload = await super().get_bundle(instrument_id, timeframe, view_window)
        payload.candles = [
            SimpleNamespace(ts_open=datetime(2026, 5, 25, tzinfo=UTC), close=105),
            SimpleNamespace(ts_open=datetime(2026, 5, 26, 0, tzinfo=UTC), close=100),
        ]
        return payload


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
    assert by_key["rsi_14"]["signal_state"] == "bullish"
    assert by_key["macd_hist"]["signal_state"] == "positive_hist"
    assert by_key["adx_14"]["signal_state"] == "strong_trend"
    assert by_key["vwap_50"]["signal_state"] == "bullish"
    assert by_key["vwap_spread_pct"]["signal_state"] == "bullish"
    assert by_key["ema_20"]["source_provider"] == "analysis_bundle"
    assert by_key["ema_20"]["value_json"]["previous_close"] == 105
    assert by_key["ema_20"]["value_json"]["close_change_pct"] == pytest.approx(
        (100 - 105) / 105 * 100
    )


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


def test_monitoring_frontend_layout_and_copy_are_clean() -> None:
    source = Path("app/static/pages/monitoring.js")
    content = source.read_text(encoding="utf-8")

    assert "monitoring-surface" in content
    assert "信源状态" in content
    assert "monitoring-source-list" in content
    assert "renderSourcePanel(data)" in content
    assert "monitoring-topbar" in content
    assert "monitoring-snapshot-grid" in content
    assert "renderTerminalSummary(data)" in content
    assert "terminal-summary-card" in content
    # The legacy left/right stacks are gone; the macro panel and terminal
    # summary now share a single full-width snapshot grid.
    assert "monitoring-left-stack" not in content
    assert "monitoring-right-stack" not in content
    assert "monitoring-snapshot-grid-full" in content
    assert "全局市场摘要" in content
    assert "全局摘要暂不可用" in content
    assert "macroTitle(item)" in content
    assert "item?.label" in content
    assert "未获取指标" in content
    assert "INVALID_TEXT_VALUES" in content
    assert "validMacroIndicator(item)" in content
    assert "!item?.is_scored && !hasIndicatorValue" not in content
    assert "Glassnode" not in content
    assert "observationValue(item)" not in content
    assert "[object Object]" not in content
    assert "参与评分" not in content
    assert "macro-indicator-grid" in content
    for token in BAD_TEXT_TOKENS:
        assert token not in content


def test_monitoring_technical_observations_use_timeframe_aware_freshness() -> None:
    now = datetime(2026, 5, 27, 12, tzinfo=UTC)
    daily = {
        "indicator_key": "ema_20",
        "timeframe": "1d",
        "observation_ts": datetime(2026, 5, 26, 0, tzinfo=UTC).isoformat(),
    }
    hourly_stale = {
        "indicator_key": "rsi_14",
        "timeframe": "1h",
        "observation_ts": datetime(2026, 5, 27, 8, 30, tzinfo=UTC).isoformat(),
    }
    missing_ts = {"indicator_key": "macd_hist", "timeframe": "1d"}

    result = MonitoringDashboardService._fresh_technical_observations(
        [daily, hourly_stale, missing_ts],
        now,
    )

    assert result == [daily, missing_ts]


def test_monitoring_frontend_trusts_backend_technical_observations() -> None:
    content = Path("app/static/pages/monitoring.js").read_text(encoding="utf-8")

    assert "TECH_OBSERVATION_MAX_AGE_MS" not in content
    assert "isFreshTechnicalObservation" not in content
    assert ".filter(isFreshTechnicalObservation)" not in content


def test_monitoring_frontend_uses_full_width_macro_then_terminal_layout() -> None:
    """The monitoring surface now stacks the macro panel and the terminal
    summary full-width (no left/right columns), and the standalone technical
    panel is gone — technical evidence is folded into the terminal summary as
    '证据：…' annotations on the trend / momentum / volatility sub-modules."""
    content = Path("app/static/pages/monitoring.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")

    render_block = content.split("function renderDashboard", 1)[1].split(
        "const MONITORING_SECTION_IDS",
        1,
    )[0]
    shell_block = content.split("root.innerHTML = `", 1)[1].split("`;", 1)[0]

    # The full-width grid class must be present in both blocks.
    assert "monitoring-snapshot-grid-full" in render_block, (
        "renderDashboard must switch to the full-width snapshot grid "
        "(no left/right stacks)"
    )
    assert "monitoring-snapshot-grid-full" in shell_block, (
        "the diff shell template must also use the full-width snapshot grid"
    )

    # The left/right stack containers are gone.
    assert "monitoring-left-stack" not in render_block
    assert "monitoring-right-stack" not in render_block
    assert "monitoring-left-stack" not in shell_block
    assert "monitoring-right-stack" not in shell_block

    # Macro + terminal summary still wired into the surface. The render
    # block calls the helpers directly; the diff shell references the
    # container ids.
    assert "renderMacroPanel(data, macro)" in render_block, (
        "renderDashboard must still call renderMacroPanel"
    )
    assert "renderTerminalSummary(data)" in render_block, (
        "renderDashboard must still call renderTerminalSummary"
    )
    assert "monitoring-terminal-summary" in shell_block, (
        "the diff shell template must still expose the terminal-summary "
        "container id so applyMonitoringDiff can swap its innerHTML"
    )

    # The standalone technical panel must NOT be wired any more.
    assert "renderTechnicalPanel(data)" not in content, (
        "renderTechnicalPanel must no longer be invoked from the page"
    )
    assert "monitoring-technical-panel" not in content, (
        "the dedicated technical panel section id must be gone"
    )

    assert '"terminal terminal"' not in css
    assert '"macro technical"' not in css
    assert "monitoring-technical-stack" not in css


def test_monitoring_dashboard_api_defaults_to_btc_daily() -> None:
    content = Path("app/api/v1/endpoints/monitoring.py").read_text(encoding="utf-8")

    assert 'instrument_id: str = Query(default="btc-usdt-perp")' in content
    assert 'timeframe: str = Query(default="1d")' in content
    dashboard_block = content.split("async def get_monitoring_dashboard", 1)[1].split(
        "@router.post",
        1,
    )[0]
    assert "allow_refresh=True" in dashboard_block


@pytest.mark.asyncio
async def test_monitoring_dashboard_get_backfills_missing_technical_observations(monkeypatch) -> None:
    from app.services.cache_registry import monitoring_dashboard_cache_key

    now = datetime.now(UTC)
    cache = SimpleNamespace(
        payload_json={
            "macro_overview": {
                "total_score": 68,
                "score_band": "温和偏暖",
                "growth_score": 70,
                "inflation_score": 60,
                "policy_score": 65,
                "liquidity_score": 72,
                "regime_summary": "宏观环境温和偏暖。",
                "regime_label_cn": "温和偏暖",
                "regime_key": "mild_warm",
            },
            "technical_observations": [],
        },
        snapshot_at=now,
        data_ts=now,
        source_updated_at=now,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        source_version="test",
        cost_ms=8,
        cache_state="fresh",
        status="ready",
    )

    class Repo:
        async def get_page_snapshot_cache(self, cache_key: str):
            if cache_key == monitoring_dashboard_cache_key("btc-usdt-perp", "1d"):
                return cache
            return None

        async def get_computed_dataset_cache(self, cache_key: str):
            return None

    service = MonitoringDashboardService(repository=Repo())  # type: ignore[arg-type]

    async def backfill(*_args, **_kwargs):
        return [
            {
                "observation_id": "analysis-bundle:btc-usdt-perp:1d:ema_20",
                "indicator_key": "ema_20",
                "category": "technical",
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "observation_ts": now.isoformat(),
                "value_num": 100,
                "value_json": {},
                "source_provider": "analysis_bundle",
                "is_preliminary": False,
                "quality_score": 95,
            }
        ]

    async def full_refresh(*_args, **_kwargs):
        raise AssertionError("displayable dashboard cache must not run full refresh")

    monkeypatch.setattr(service, "_technical_observations_from_analysis_bundle", backfill)
    monkeypatch.setattr(service, "refresh_bundle", full_refresh)

    result = await service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)

    assert result.refreshed is True
    assert result.technical_indicator_count == 1
    assert result.technical_observations[0].indicator_key == "ema_20"


@pytest.mark.asyncio
async def test_monitoring_dashboard_get_keeps_snapshot_when_technical_backfill_fails(
    monkeypatch,
) -> None:
    from app.services.cache_registry import monitoring_dashboard_cache_key

    now = datetime(2026, 5, 27, 12, tzinfo=UTC)
    cache = SimpleNamespace(
        payload_json={
            "macro_overview": {
                "total_score": 68,
                "score_band": "温和偏暖",
                "growth_score": 70,
                "inflation_score": 60,
                "policy_score": 65,
                "liquidity_score": 72,
                "regime_summary": "宏观环境温和偏暖。",
                "regime_label_cn": "温和偏暖",
                "regime_key": "mild_warm",
            },
            "technical_observations": [],
        },
        snapshot_at=now,
        data_ts=now,
        source_updated_at=now,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        source_version="test",
        cost_ms=8,
        cache_state="fresh",
        status="ready",
    )

    class Repo:
        async def get_page_snapshot_cache(self, cache_key: str):
            if cache_key == monitoring_dashboard_cache_key("btc-usdt-perp", "1d"):
                return cache
            return None

        async def get_computed_dataset_cache(self, cache_key: str):
            return None

    service = MonitoringDashboardService(repository=Repo())  # type: ignore[arg-type]

    async def boom(*_args, **_kwargs):
        raise RuntimeError("analysis unavailable")

    async def full_refresh(*_args, **_kwargs):
        raise AssertionError("technical-only miss must not run full dashboard refresh")

    monkeypatch.setattr(service, "_technical_observations_from_analysis_bundle", boom)
    monkeypatch.setattr(service, "refresh_bundle", full_refresh)

    result = await service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)

    assert result.refreshed is False
    assert result.refresh_enqueued is True
    assert result.technical_indicator_count == 0


@pytest.mark.asyncio
async def test_monitoring_daily_analysis_bundle_allows_36h_candle(monkeypatch) -> None:
    monkeypatch.setattr(
        monitoring_dashboard,
        "AnalysisBundleService",
        DailyOldAnalysisBundleService,
    )
    service = MonitoringDashboardService(repository=object())

    items = await service._technical_observations_from_analysis_bundle(
        "btc-usdt-perp",
        "1d",
        datetime(2026, 5, 27, 12, tzinfo=UTC),
    )

    assert items
    assert {item["indicator_key"] for item in items} >= {"ema_20", "rsi_14"}
