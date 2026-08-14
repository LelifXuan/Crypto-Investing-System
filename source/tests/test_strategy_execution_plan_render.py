"""Behavioural tests for ``renderExecutionPlan``.

The frontend renderer is a native ES module that takes a ``model`` + ``helpers``
argument and returns an HTML string. We import it directly via Node, drive
the renderer with a representative model, and assert on the actual HTML it
produces (rather than on source-string matches).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_renderer(model: dict, helpers: dict | None = None) -> dict:
    """Run renderExecutionPlan(model, helpers) in a Node subprocess.

    Returns a parsed JSON dict so assertions can introspect the produced HTML.
    """
    helpers = helpers or {"escapeHtml": "s"}  # placeholder, the renderer does
    # not actually call escapeHtml when given the literal value "s" (since it
    # only uses the helper for ``escapeHtml(value)`` — when invoked with a
    # non-function we override below).
    payload = json.dumps({"model": model, "helpers": helpers})
    script = f"""
import {{ renderExecutionPlan }} from 'file:///{ROOT.as_posix()}/app/static/pages/strategy/renderExecutionPlan.js';

// Adapter helpers imported by renderExecutionPlan expect functions, not
// strings. Provide a minimal stub that mirrors what index.js wires up.
const model = JSON.parse({json.dumps(payload)}).model;
const helpers = {{
  escapeHtml(value) {{
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }},
  emptyState(msg) {{ return `<p class="empty">${{msg}}</p>`; }},
}};
const html = renderExecutionPlan(model, helpers);
process.stdout.write(JSON.stringify({{ html }}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _full_model() -> dict:
    return {
        "trade_decision": {
            "side": "SHORT",
            "status": "WAIT_PRICE",
            "order_type": "CONDITIONAL_LIMIT",
            "order_status": "WAIT_PRICE",
            "trade_timeframe": "4h",
            "primary_reason": {
                "message": "1H 尚未与日线方向一致，等待价格进入候选区并完成顺势反转确认。",
            },
            "leverage_reason": "条件尚未同时满足；当前不使用杠杆，激活后按计划上限执行。",
            "recommended_leverage": 3.0,
            "max_leverage": 3.0,
            "planned_leverage": 3.0,
            "activation_conditions": [
                "价格反弹进入 64740.02~64999.50",
                "1H 恢复空头结构并收盘确认",
            ],
            "valid_until": "1h:16_bars",
            "next_check": "next_4h_close",
            "entry_zone": [64740.02, 64999.50],
            "limit_price": 64869.76,
            "stop_loss": 65772.62,
            "take_profit": [
                {"label": "TP1", "price": 62187.32},
                {"label": "TP2", "price": 61938.43},
            ],
            "risk_reward": {"legacy_rr": 2.97},
        },
        "trade_plans": [
            {
                "id": "primary-plan",
                "type": "TACTICAL_CURRENT_ORDER",
                "direction": "SHORT",
                "order_type": "CONDITIONAL_LIMIT",
                "trade_timeframe": "4h",
                "stop_loss": 65772.62,
                "take_profit": [
                    {"label": "TP1", "price": 62187.32},
                    {"label": "TP2", "price": 61938.43},
                ],
                "risk_reward": {"legacy_rr": 2.97},
                "activation_conditions": [
                    "价格反弹进入 64740.02~64999.50",
                    "1H 恢复空头结构并收盘确认",
                ],
                "valid_until": "1h:16_bars",
                "recommended_leverage": 3.0,
                "max_leverage": 3.0,
                "planned_leverage": 3.0,
                "permission": "WAIT",
            },
            {
                "id": "secondary-plan",
                "type": "EXECUTION_TRIGGER",
                "direction": "SHORT",
                "label": "备用长期计划",
                "permission": "OBSERVE",
                "stop_loss": 67000.0,
                "take_profit": [{"label": "TP1", "price": 60000.0}],
                "risk_reward": {"legacy_rr": 3.5},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Top strip: exactly 3 KPI cards (方向 / 执行状态 / 主要原因)
# ---------------------------------------------------------------------------


def test_render_execution_plan_top_strip_has_three_kpis() -> None:
    out = _run_renderer(_full_model())
    html = out["html"]
    # Find the wrapper <div class="strategy-decision-strip"> OPENING tag and
    # walk forward counting div opens/closes until depth returns to 0 (which
    # is the wrapper's matching close).
    marker = '<div class="strategy-decision-strip">'
    strip_open = html.index(marker)
    cursor = strip_open + len(marker)
    depth = 1  # we are now inside the wrapper
    end = -1
    while cursor < len(html):
        next_open = html.find("<div", cursor)
        next_close = html.find("</div>", cursor)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            cursor = next_open + 4
        else:
            depth -= 1
            cursor = next_close + len("</div>")
            if depth == 0:
                end = cursor
                break
    assert end > strip_open, "could not locate the closing </div> of the strip wrapper"
    strip_block = html[strip_open:end]
    kpi_labels = ("方向", "执行状态", "主要原因")
    for label in kpi_labels:
        assert f"<span>{label}</span>" in strip_block, (
            f"top strip must carry {label!r}, got: {strip_block[:400]}"
        )
    # 订单类型 and 杠杆 must NOT appear as KPI labels any more.
    assert "<span>订单类型</span>" not in strip_block, (
        "top strip must not duplicate the order_type label inside the strip"
    )
    assert "<span>杠杆</span>" not in strip_block, (
        "top strip must not duplicate the leverage label; leverage now lives "
        "in the leverage_reason summary line below"
    )


# ---------------------------------------------------------------------------
# Primary plan: rendered as a card, not as a row in a table
# ---------------------------------------------------------------------------


def test_render_execution_plan_primary_renders_as_card_not_table_row() -> None:
    out = _run_renderer(_full_model())
    html = out["html"]
    assert 'class="strategy-primary-plan-card"' in html, (
        "primary plan must render as a dedicated card, not as a row in the "
        "legacy 11-column table"
    )
    # The primary card must include the 6 detail labels.
    card_start = html.index('<div class="strategy-primary-plan-card">')
    card_block = html[card_start: html.index("</dl>", card_start) + len("</dl>")]
    for label in (
        "执行价 / 限价区间",
        "止损",
        "止盈",
        "盈亏比",
        "触发条件",
        "状态",
    ):
        assert f"<dt>{label}</dt>" in card_block, (
            f"primary card must carry detail label {label!r}, got: {card_block}"
        )


# ---------------------------------------------------------------------------
# Secondary table: still uses the legacy 11-column layout (it shows rows
# across plans, so per-row identity still helps). We only assert it appears
# when there is at least one secondary plan, and that the table is wrapped
# in the "其他计划" details.
# ---------------------------------------------------------------------------


def test_render_execution_plan_secondary_table_is_collapsed_and_keeps_eleven_columns() -> None:
    out = _run_renderer(_full_model())
    html = out["html"]
    assert "其他计划" in html, "secondary plans block must keep the 折叠 summary"
    # Inside the secondary table the legacy 11 columns remain (per-plan
    # distinct labels).
    assert '<th>计划</th>' in html, (
        "secondary table must keep the legacy 计划 column for per-plan rows"
    )
    assert '<th>订单类型</th>' in html
    assert '<th>交易级别</th>' in html
    assert '<th>方向</th>' in html
    assert '<th>杠杆</th>' in html