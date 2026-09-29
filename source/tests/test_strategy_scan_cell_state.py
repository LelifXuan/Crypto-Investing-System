"""Guards for the opportunity-matrix cell vocabulary (2026-09-22, stale-serving 2026-09-23).

What went wrong, and what these tests pin:

1. The matrix called a payload with no usable data "等待确认" whenever the cell
   was not promoted. A 13-day-old cached cell therefore read as a market
   conclusion ("nothing to confirm") instead of "this cell has no data".
2. A cell whose payload *did* carry a direction was painted as "—" as soon as
   the strict gate rejected it, while the detail drawer for the same
   instrument × timeframe showed 做空 / 看空. Two surfaces, two stories.
3. The same "no result" situation appeared under two different words
   ("数据构建中" for missing cells, "等待确认" for the rest).
4. (2026-09-23 stale-serving) A stale cell hid its last good direction behind
   "数据准备中". Per AGENTS.md §九.1 a stale snapshot with last-known-good
   must render the old conclusion first: stale-directional cells now show
   the direction with its directional tone + "数据更新中"; the dashed
   stale border (not a bleached tone) tells it apart from a fresh signal.
5. (2026-09-23 directional tone) An explicit direction always wears its
   bottom color — candidate, stale and qualified share bullish/bearish;
   only directionless cells (idle/pending) stay neutral. Promotion is told
   by the small label ("等待确认"/"数据更新中" vs none) and the dashed
   border, never by bleaching the signal color.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROOT_MATRIX = "app/static/pages/strategy/renderScanMatrix.js"


def _matrix_source() -> str:
    return (ROOT / ROOT_MATRIX).read_text(encoding="utf-8")


def _cell_state_module() -> str:
    """The helper slice of renderScanMatrix.js, runnable by node.

    Everything from the state tables down to ``cellState`` is self-contained —
    it imports nothing — so it can be extracted verbatim and executed.
    """
    source = _matrix_source()
    start = source.index("const DATA_PENDING_STATES")
    end = source.index("const DIRECTION_ICON_PATH")
    return source[start:end].replace("export function cellState", "function cellState")


def _cell_state(item) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not available")
    script = (
        _cell_state_module() + f"\nconsole.log(JSON.stringify(cellState({json.dumps(item)})));\n"
    )
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"node failed: {result.stderr}"
    return json.loads(result.stdout.strip())


def _fresh(**overrides) -> dict:
    base = {
        "instrument_id": "eth-usdt-perp",
        "instrument_code": "ETH",
        "timeframe": "1d",
        "direction": "SHORT",
        "direction_label": "做空",
        "cache_state": "fresh",
        "qualified": False,
        "qualification_reasons": ["risk_reward_below_gate"],
    }
    base.update(overrides)
    return base


def test_stale_directional_cell_is_not_a_current_opportunity():
    """Stale-serving (2026-09-23, directional tone): a stale cell with a
    direction shows it with its directional tone + update label — the
    dashed stale border tells it apart from a fresh signal."""
    state = _cell_state(_fresh(cache_state="stale", direction="LONG", direction_label="做多"))

    assert state["kind"] == "stale"
    assert state["label"] == "数据更新中"
    assert state["direction"] == ""
    assert state["tone"] == "neutral"
    assert state["clickable"] is False
    assert "更新" in state["tooltip"]


def test_stale_directionless_cell_stays_pending():
    """A stale cell with no direction has nothing to serve — pending."""
    state = _cell_state(_fresh(cache_state="stale", direction="WAIT", direction_label="等待"))

    assert state["kind"] == "stale"
    assert state["label"] == "数据更新中"
    assert state["direction"] == ""


def test_missing_warming_error_share_the_same_visible_label():
    labels = {
        state
        for state in (
            _cell_state(_fresh(cache_state="missing"))["label"],
            _cell_state(_fresh(cache_state="warming"))["label"],
            _cell_state(_fresh(cache_state="error"))["label"],
        )
    }
    assert labels == {"数据准备中"}, f"data states must share one word, got {labels}"


def test_cells_without_current_permission_stay_closed():
    assert _cell_state(_fresh(cache_state="missing"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="warming"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="error"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="stale"))["clickable"] is False
    assert (
        _cell_state(_fresh(cache_state="stale", direction="WAIT", direction_label="等待"))[
            "clickable"
        ]
        is False
    )


def test_rejected_directional_cell_is_not_listed_as_an_opportunity():
    state = _cell_state(_fresh())

    assert state["kind"] == "idle"
    assert state["direction"] == ""
    assert state["label"] == "无机会"
    assert state["tone"] == "neutral"
    assert state["clickable"] is False
    assert "盈亏比不足" in state["tooltip"]


def test_promoted_cell_paints_only_the_direction():
    state = _cell_state(_fresh(qualified=True, qualification_reasons=[]))

    assert state["kind"] == "qualified"
    assert state["direction"] == "做空"
    assert state["tone"] == "bearish"
    assert state["label"] == ""


def test_directionless_fresh_cell_is_the_only_wait_state():
    state = _cell_state(
        _fresh(direction="WAIT", direction_label="等待", qualification_reasons=["no_direction"])
    )

    assert state["kind"] == "idle"
    assert state["direction"] == ""
    assert state["label"] == "无机会"
    assert "多周期无方向" in state["tooltip"]


def test_matrix_drops_raw_gate_codes_from_the_visible_cell():
    source = _matrix_source()
    # Reasons surface as Chinese labels through the tooltip, never as raw codes.
    assert "GATE_REASON_LABELS" in source
    assert "本周期未形成完整交易计划：" in source


def _scan_item(**overrides):
    from app.services.strategy_unified.opportunity_scanner import (
        _extract_scan_item,
    )

    payload = {
        "status": "ready",
        "degraded_components": [],
        "timeframe_stack": [
            {
                # NOTE: the cell under test is 1d (not 1w) on purpose — the
                # removed fallback only fired for the trade_timeframe and
                # direction_timeframes (["1d", "4h"]), so a 1w cell never
                # borrowed anything and cannot guard the regression.
                "timeframe": "1d",
                "direction": "SHORT",
                "confidence": 94.1,
                # Invalid SHORT geometry: support/resistance ABOVE current —
                # no valid risk or reward can be built from this cell.
                "current_price": 86519.8,
                "key_support": 89548.78,
                "key_resistance": 89907.69,
                "invalidation": 99932.44,
                "long_score": 42.0,
                "short_score": 60.4,
                "freshness": "fresh",
                "verdict_label": "CONTEXT_ALIGNED_SHORT",
                "evidence": ["偏空观察"],
            }
        ],
        "signal_coverage": [],
        "evidence_trace": [],
        "trade_decision": {
            "side": "SHORT",
            "trade_timeframe": "4h",
            "direction_timeframes": ["1d", "4h"],
            "position_cap": "standard",
            "risk_reward": {"value": 2.17},
        },
        "direction_resolution": {},
    }
    return _extract_scan_item(payload, "btc-usdt-perp", "BTC", "1d", **overrides)


def test_timeframe_cell_never_borrows_decision_level_rr():
    """The 1d cell must not display the 4h trade plan's 2.17: its own
    geometry is invalid (support above price for a SHORT), so RR is 0
    and the gate rejects it — instead of showing a passing number that
    the drawer cannot reproduce for this timeframe."""
    item = _scan_item()
    assert item.risk_reward == 0.0
    assert "risk_reward_below_gate" in item.qualification_reasons
    assert item.qualified is False


def test_ranked_summary_skips_plan_validation_line():
    """The ranked summary must not say "策略价位无效": node evidence[0]
    is the bundle validator's verdict on the raw per-timeframe plan, not
    the unified trade plan the drawer shows. Skip it, use the next line."""
    from app.services.strategy_unified.opportunity_scanner import (
        _extract_scan_item,
    )

    payload = {
        "status": "ready",
        "degraded_components": [],
        "timeframe_stack": [
            {
                "timeframe": "1d",
                "direction": "SHORT",
                "confidence": 100.0,
                "current_price": 125.0,
                "key_support": 116.55,
                "key_resistance": 126.04,
                "invalidation": 129.61,
                "long_score": 37.0,
                "short_score": 62.0,
                "freshness": "fresh",
                "verdict_label": "CONTEXT_ALIGNED_SHORT",
                "evidence": [
                    "当前策略状态为“策略价位无效”，策略倾向为“偏空”。",
                    "多头分 37.14，空头分 62.25，中性分 41.43。",
                ],
            }
        ],
        "signal_coverage": [],
        "evidence_trace": [],
        "trade_decision": {
            "side": "SHORT",
            "trade_timeframe": "4h",
            "direction_timeframes": ["1d", "4h"],
            "position_cap": "standard",
            "risk_reward": {"value": 2.2},
            "primary_reason": {"message": "1H 尚未与日线方向一致，等待触发。"},
        },
        "direction_resolution": {},
    }
    item = _extract_scan_item(payload, "okb-usdt-perp", "OKB", "1d")
    assert "策略价位无效" not in item.summary
    assert item.summary.startswith("CONTEXT_ALIGNED_SHORT")
    assert "多头分" in item.summary


def test_cell_execution_levels_belong_to_selected_execution_period():
    """Only a qualified 4H cell can expose the matching 4H plan levels."""
    from app.services.strategy_unified.opportunity_scanner import (
        _cell_execution_levels,
    )

    payload = {
        "status": "ready",
        "degraded_components": [],
        "timeframe_stack": [
            {
                "timeframe": "4h",
                "direction": "SHORT",
                "confidence": 100.0,
                "current_price": 97.4,
                "key_support": 90.3,
                "key_resistance": 97.7,
                "invalidation": 100.5,
                "long_score": 33.0,
                "short_score": 60.0,
                "freshness": "fresh",
                "verdict_label": "CONTEXT_ALIGNED_SHORT",
                "evidence": ["偏空观察"],
            }
        ],
        "signal_coverage": [],
        "evidence_trace": [],
        "horizon_views": {"tactical": {"direction": "SHORT"}},
        "trade_decision": {
            "side": "SHORT",
            "trade_timeframe": "4h",
            "direction_timeframes": ["1d", "4h"],
            "position_cap": "standard",
            "permission": "allow",
            "risk_reward": {"value": 2.2},
            "primary_reason": {"message": "等待触发"},
        },
        "direction_resolution": {},
        "trade_plans": [
            {
                "plan_type": "STRATEGIC_RISK_REDUCTION",
                "direction": "SHORT",
                "entry_zone": [98.12],
                "stop_loss": 98.12,
                "take_profit": [],
            },
            {
                "plan_type": "TACTICAL_SHORT",
                "direction": "SHORT",
                "entry_zone": [97.34, 97.73],
                "stop_loss": 100.54,
                "take_profit": [
                    {"label": "TP1", "price": 90.3},
                    {"label": "TP2", "price": 76.64},
                ],
            },
        ],
    }
    assert _cell_execution_levels(payload, "SHORT", "4h") == ([97.34, 97.73], 100.54, 90.3)
    assert _cell_execution_levels(payload, "SHORT", "1d") == ([], None, None)
    assert _cell_execution_levels(payload, "WAIT", "4h") == ([], None, None)
    assert _cell_execution_levels({"trade_plans": []}, "SHORT", "4h") == ([], None, None)
    from app.services.strategy_unified.opportunity_scanner import _extract_scan_item_legacy

    item = _extract_scan_item_legacy(payload, "hype-usdt-perp", "HYPE", "4h")
    assert item.qualified
    assert item.entry_zone == [97.34, 97.73]
    assert item.stop_loss == 100.54
    assert item.take_profit_1 == 90.3
