"""Gold Workbench V5 response schema — aggregated page payload.

The gold-allocation page (gold_v5.js) consumes a single ``GoldWorkbenchRead``
payload instead of fanning out to V3/market-state/derivatives individually.
Most sub-blocks are intentionally loose ``dict[str, Any]`` so the endpoint
can forward service output without re-declaring every nested field; the
top-level shape is what the frontend contract depends on.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class GoldWorkbenchRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "2.0.0"
    snapshot: dict[str, Any]
    portfolio: dict[str, Any]
    strategic_allocation: dict[str, Any]
    base_dca: dict[str, Any]
    dip_add: dict[str, Any]
    market_scenarios: dict[str, Any]
    technical_summary: dict[str, Any]
    derivatives: dict[str, Any]
    chart_series_or_chart_token: dict[str, Any]
    source_manifest: list[dict[str, Any]]
    refresh_state: str
