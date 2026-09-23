"""Guards for the opportunity-matrix cell vocabulary (2026-09-22).

What went wrong, and what these tests pin:

1. The matrix called a payload with no usable data "等待确认" whenever the cell
   was not promoted. A 13-day-old cached cell therefore read as a market
   conclusion ("nothing to confirm") instead of "this cell has no data".
2. A cell whose payload *did* carry a direction was painted as "—" as soon as
   the strict gate rejected it, while the detail drawer for the same
   instrument × timeframe showed 做空 / 看空. Two surfaces, two stories.
3. The same "no result" situation appeared under two different words
   ("数据构建中" for missing cells, "等待确认" for the rest).
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
        _cell_state_module()
        + f"\nconsole.log(JSON.stringify(cellState({json.dumps(item)})));\n"
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30, check=False
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


def test_stale_payload_is_not_reported_as_a_market_conclusion():
    state = _cell_state(_fresh(cache_state="stale", direction="LONG", direction_label="做多"))

    assert state["kind"] == "pending"
    assert state["label"] == "数据准备中"
    assert state["direction"] == ""
    assert "过期" in state["tooltip"]


def test_missing_and_stale_share_the_same_visible_label():
    labels = {
        state
        for state in (
            _cell_state(_fresh(cache_state="missing"))["label"],
            _cell_state(_fresh(cache_state="warming"))["label"],
            _cell_state(_fresh(cache_state="error"))["label"],
            _cell_state(_fresh(cache_state="stale"))["label"],
        )
    }
    assert labels == {"数据准备中"}, f"data states must share one word, got {labels}"


def test_cells_without_a_payload_stay_closed_but_stale_stays_openable():
    assert _cell_state(_fresh(cache_state="missing"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="warming"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="error"))["clickable"] is False
    assert _cell_state(_fresh(cache_state="stale"))["clickable"] is True


def test_rejected_directional_cell_still_reports_its_direction():
    """The drawer shows 做空 for this cell; the matrix must not say "—"."""
    state = _cell_state(_fresh())

    assert state["kind"] == "candidate"
    assert state["direction"] == "做空"
    assert state["label"] == "等待确认"
    assert state["tone"] == "neutral", "a rejected candidate must not be painted bullish/bearish"
    assert state["clickable"] is True
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
    assert state["label"] == "等待确认"
    assert "多周期无方向" in state["tooltip"]


def test_matrix_drops_raw_gate_codes_from_the_visible_cell():
    source = _matrix_source()
    # Reasons surface as Chinese labels through the tooltip, never as raw codes.
    assert "GATE_REASON_LABELS" in source
    assert "未通过门禁：" in source
