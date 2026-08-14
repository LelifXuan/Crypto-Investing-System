"""Verify chip_structure declares the signed direction-score scale contract.

The T01 audit required chip to make its signed scale explicit so the
snapshot builder can pass ``scale="signed"`` to ``normalize_direction_metrics``
without the legacy auto-detect silently flipping a neutral reading into a
bearish one. This test pins the new payload fields on the live service.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services.chip_structure import ChipStructureService


def test_chip_payload_declares_signed_scale_and_proxy_label() -> None:
    """When candles are present the live payload carries both new fields."""
    repo = SimpleNamespace()
    service = ChipStructureService(repository=repo)  # type: ignore[arg-type]

    candles = [
        {"close": 100.0 + i * 0.5}
        for i in range(40)
    ]

    async def _fake_load(instrument_id: str, timeframe: str) -> list[dict]:
        return candles

    service._load_candles = _fake_load  # type: ignore[method-assign]

    payload = asyncio.run(service.analyze("btc-usdt-perp", "1d"))

    assert payload["direction_score_scale"] == "signed"
    assert payload["evidence_quality"] == "proxy_only"
    assert "证据不足" in payload["evidence_quality_label"]
    assert -100.0 <= payload["direction_score"] <= 100.0


def test_chip_missing_payload_also_declares_scale_and_label() -> None:
    """The missing-data path must also declare the scale + label."""
    repo = SimpleNamespace()
    service = ChipStructureService(repository=repo)  # type: ignore[arg-type]

    async def _empty_load(instrument_id: str, timeframe: str) -> list[dict]:
        return []

    service._load_candles = _empty_load  # type: ignore[method-assign]

    payload = asyncio.run(service.analyze("btc-usdt-perp", "1d"))

    assert payload["direction_score_scale"] == "signed"
    assert payload["evidence_quality"] == "proxy_only"
    assert payload["evidence_quality_label"]
    assert payload["direction_score"] == 0.0
