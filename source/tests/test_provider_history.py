"""Unit tests for ``FredMacroProvider.fetch_history`` and
``BlsMacroProvider.fetch_history``.

These tests mock the network-bound private methods so the providers
themselves can be exercised without a live FRED / BLS connection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services.macro.providers.base import MacroFetchPoint
from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.fred import FredMacroProvider

UTC = timezone.utc


def _ts(year: int, month: int, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fred_fetch_history_returns_ascending_lookback(monkeypatch) -> None:
    provider = FredMacroProvider()

    async def fake_official_history(source_key, api_key, lookback_points):
        assert source_key == "CPIAUCSL"
        assert lookback_points == 14
        return [
            MacroFetchPoint(observation_ts=_ts(2025, 5), value=Decimal("320.0"), status="ok"),
            MacroFetchPoint(observation_ts=_ts(2025, 6), value=Decimal("321.0"), status="ok"),
            MacroFetchPoint(observation_ts=_ts(2026, 5), value=Decimal("332.407"), status="ok"),
        ]

    monkeypatch.setattr(provider, "_fetch_official_history", fake_official_history)
    monkeypatch.setattr(provider.secrets, "get", lambda *_args, **_kwargs: "fake-key")

    history = await provider.fetch_history("CPIAUCSL", lookback_points=14)
    assert len(history) == 3
    assert [p.value for p in history] == [Decimal("320.0"), Decimal("321.0"), Decimal("332.407")]
    assert history[0].observation_ts == _ts(2025, 5)
    assert history[-1].observation_ts == _ts(2026, 5)


@pytest.mark.asyncio
async def test_fred_fetch_history_falls_back_to_public_when_no_key(monkeypatch) -> None:
    provider = FredMacroProvider()

    async def fake_public_history(source_key, lookback_points):
        assert source_key == "PCEPI"
        return [
            MacroFetchPoint(observation_ts=_ts(2026, 4), value=Decimal("130.9"), status="ok"),
        ]

    monkeypatch.setattr(provider, "_fetch_public_history", fake_public_history)
    monkeypatch.setattr(provider.secrets, "get", lambda *_args, **_kwargs: None)

    history = await provider.fetch_history("PCEPI", lookback_points=14)
    assert len(history) == 1
    assert history[0].value == Decimal("130.9")


@pytest.mark.asyncio
async def test_fred_fetch_history_propagates_missing_status(monkeypatch) -> None:
    provider = FredMacroProvider()

    async def fake_official_history(source_key, api_key, lookback_points):
        return [
            MacroFetchPoint(observation_ts=_ts(2026, 3), value=Decimal("330"), status="ok"),
            MacroFetchPoint(observation_ts=_ts(2026, 4), value=None, status="missing"),
        ]

    monkeypatch.setattr(provider, "_fetch_official_history", fake_official_history)
    monkeypatch.setattr(provider.secrets, "get", lambda *_args, **_kwargs: "fake-key")

    history = await provider.fetch_history("CPIAUCSL", lookback_points=14)
    assert history[1].status == "missing"
    assert history[1].value is None


@pytest.mark.asyncio
async def test_fred_fetch_history_official_failure_falls_back_to_public(monkeypatch) -> None:
    provider = FredMacroProvider()

    async def fake_official_history(*args, **kwargs):
        raise ValueError("network down")

    async def fake_public_history(source_key, lookback_points):
        return [
            MacroFetchPoint(observation_ts=_ts(2026, 4), value=Decimal("332"), status="ok"),
        ]

    monkeypatch.setattr(provider, "_fetch_official_history", fake_official_history)
    monkeypatch.setattr(provider, "_fetch_public_history", fake_public_history)
    monkeypatch.setattr(provider.secrets, "get", lambda *_args, **_kwargs: "fake-key")

    history = await provider.fetch_history("CPIAUCSL", lookback_points=14)
    assert len(history) == 1
    assert history[0].value == Decimal("332")


@pytest.mark.asyncio
async def test_bls_fetch_history_returns_ascending_lookback(monkeypatch) -> None:
    provider = BlsMacroProvider()

    async def fake_series_json(series_id, startyear, endyear):
        return {
            "Results": {
                "series": [
                    {
                        "data": [
                            {"year": "2026", "period": "M03", "value": "335.1"},
                            {"year": "2026", "period": "M04", "value": "335.423"},
                        ]
                    }
                ]
            }
        }, 0, False

    monkeypatch.setattr(provider, "_fetch_series_json", fake_series_json)

    history = await provider.fetch_history("CUUR0000SA0L1E", lookback_points=14)
    assert len(history) == 2
    assert history[0].observation_ts == _ts(2026, 3)
    assert history[1].observation_ts == _ts(2026, 4)
    assert history[1].value == Decimal("335.423")


@pytest.mark.asyncio
async def test_bls_fetch_history_handles_empty_value(monkeypatch) -> None:
    provider = BlsMacroProvider()

    async def fake_series_json(series_id, startyear, endyear):
        return {
            "Results": {
                "series": [
                    {
                        "data": [
                            {"year": "2026", "period": "M03", "value": "335.1"},
                            {"year": "2026", "period": "M04", "value": ""},
                        ]
                    }
                ]
            }
        }, 0, False

    monkeypatch.setattr(provider, "_fetch_series_json", fake_series_json)

    history = await provider.fetch_history("CUUR0000SA0L1E", lookback_points=14)
    assert history[1].value is None
    assert history[1].status == "missing"


@pytest.mark.asyncio
async def test_bls_fetch_history_truncates_to_lookback(monkeypatch) -> None:
    provider = BlsMacroProvider()

    async def fake_series_json(series_id, startyear, endyear):
        return {
            "Results": {
                "series": [
                    {
                        "data": [
                            {"year": "2026", "period": f"M{m:02d}", "value": str(300 + m)}
                            for m in range(1, 13)
                        ]
                    }
                ]
            }
        }, 0, False

    monkeypatch.setattr(provider, "_fetch_series_json", fake_series_json)

    history = await provider.fetch_history("CUUR0000SA0", lookback_points=4)
    assert len(history) == 4
    expected = [Decimal("309"), Decimal("310"), Decimal("311"), Decimal("312")]
    assert [p.value for p in history] == expected
