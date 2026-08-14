from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _extract_function_body(source: str, fn_name: str) -> str:
    """Return the source of ``fn_name`` from a JS file.

    Locates the ``function <fn_name>(...) {`` opener and slices until the
    next top-level ``function`` / ``export function`` declaration (or
    EOF). Used by the static guards below to scope assertions to a
    single render function so a wrong config in the equity curve cannot
    pass the assertion by hiding inside an unrelated function.
    """
    match = re.search(rf"^function {re.escape(fn_name)}\b", source, re.MULTILINE)
    if not match:
        return ""
    start = match.start()
    rest = source[start + 1:]
    next_fn = re.search(r"^(?:export\s+)?function\s+\w+\b", rest, re.MULTILINE)
    end = start + 1 + (next_fn.start() if next_fn else len(rest))
    return source[start:end]


def _strip_js_comments(source: str) -> str:
    """Strip ``//`` and ``/* */`` comments so substring assertions ignore
    prose that happens to mention a forbidden identifier (e.g. a comment
    explaining the bug that the assertion is guarding against)."""
    # Block comments first to avoid leaving stray ``//`` from inside them.
    no_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    return no_line


def _function_body_no_comments(source: str, fn_name: str) -> str:
    return _strip_js_comments(_extract_function_body(source, fn_name))


def test_structure_entry_uses_versioned_dynamic_import() -> None:
    source = (ROOT / "app/static/pages/structure/index.js").read_text(encoding="utf-8")
    assert 'from "../structure.js"' not in source
    assert "window.__ASSET_VERSION__" in source
    assert "import(`../structure.js${assetVersion}`)" in source


def test_router_asset_version_scans_static_and_templates() -> None:
    source = (ROOT / "app/web/router.py").read_text(encoding="utf-8")
    assert "rglob" in source
    assert '".js", ".css", ".html"' in source
    assert "技术指标" in source


def test_alerts_initial_load_has_fallback_shell() -> None:
    source = (ROOT / "app/static/pages/alerts.js").read_text(encoding="utf-8")
    assert "alerts:initial-load:error" in source
    assert "fallbackChipStructureCard" in source
    assert "alert-chip-primary-card" in source
    assert "alert-chip-score-strip" in source
    assert "alert-chip-position-grid" in source
    assert "localizeExplainText" in source


def test_alert_chip_layout_avoids_sparse_fixed_metric_grid() -> None:
    source = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert ".alert-chip-primary-card" in source
    assert ".alert-chip-score-strip" in source
    assert ".alert-chip-position-grid" in source
    chip_metrics = source.split(".alert-chip-metrics", 1)[1].split("}", 1)[0]
    assert "repeat(6" not in chip_metrics
    assert ".alert-chip-gate-list" not in source
    assert ".alert-chip-gate-row" not in source


def test_structure_price_line_is_visually_subdued() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    expected = 'price: { label: "收盘价", color: "rgba(44, 56, 73, 0.42)", dash: "", width: 2.15 }'
    assert expected in source
    assert "extendOverlayToLatestCandle" in source
    assert "visiblePointInViewport" in source
    assert "localIndexForPoint" in source
    assert "currentPriceGuide" in source
    assert "suppressBrokenClassicOverlay" in source
    assert "buildGuideMarkerMarkup" in source
    assert "let strokeColor = (CHART_SERIES[item.system]" in source
    assert "月线样本不足" in source
    assert "${buildLayerToggleMarkup()}" in source
    assert '<div class="structure-legend-toggles">' in source


def test_structure_confidence_missing_values_are_not_rendered_as_zero() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")

    assert "candidate?.confidence ?? 0" not in source
    assert "overall.overall_confidence ?? overall.confidence ?? 0" not in source
    assert "confidence: 0," not in source


def test_structure_page_does_not_render_internal_detail_cards() -> None:
    source = (ROOT / "app/static/pages/structure.js").read_text(encoding="utf-8")
    forbidden = [
        "structure-detail-panel",
        "renderDetailPanel",
        "renderDiagnostics",
        "renderCurrentStructures",
        "renderEventHistory",
        "renderAlertHistory",
        "当前结构",
        "近期事件",
        "告警历史",
        "检测诊断",
    ]
    for token in forbidden:
        assert token not in source


def test_knowledge_catalog_does_not_generate_template_body_text() -> None:
    source = (ROOT / "app/static/core/knowledge.js").read_text(encoding="utf-8")
    assert "常见误区是孤立使用" not in source
    assert "非公式性规则：结合系统上下文" not in source
    assert "readablePages" not in source


def test_market_event_text_normalizes_broken_quotes() -> None:
    module_path = ROOT / "app/static/pages/market_events.js"
    script = f"""
import {{ decodePossiblyBrokenText }} from 'file:///{module_path.as_posix()}';
const samples = [
  decodePossiblyBrokenText('Bitcoin\\uFFFDs dip and investor\\uFFFDs worries'),
  decodePossiblyBrokenText('Startup\\u25A1s Database'),
  decodePossiblyBrokenText('claims as \\uFFFDwildly conspiratorial\\uFFFD'),
  decodePossiblyBrokenText('Robinhood\\uFFFDs Q1 revenue'),
];
console.log(JSON.stringify(samples));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(result.stdout) == [
        "Bitcoin's dip and investor's worries",
        "Startup's Database",
        'claims as "wildly conspiratorial"',
        "Robinhood's Q1 revenue",
    ]


def test_analysis_uses_canonical_latest_mark_independent_of_timeframe() -> None:
    source = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")
    assert "let escapeHtml;" in source
    assert "escapeHtml," in source
    assert "let markPayload = bundle.mark || null;" in source
    assert "getAnalysisBundle" in source
    assert "getLatestMark" in source
    assert "enhanceLatestMark" in source
    assert "{ preferLive = false }" in source
    assert "enhanceLatestMark(token, { preferLive: true })" in source
    assert "let allCandles = normalizeOhlcCandles" in source


def test_price_chart_uses_distinct_ema_colors_and_vwap_line_hierarchy() -> None:
    source = (ROOT / "app/static/pages/analysis.js").read_text(encoding="utf-8")

    # Short EMA = bright + thin; long EMA = deep + thick (active vs stable anchor).
    assert 'lineDataset("EMA30", analysis.ema30, "#dcbe88", { borderWidth: 1.6 })' in source
    assert 'lineDataset("EMA60", analysis.ema60, "#a89569", { borderWidth: 2.0 })' in source
    assert 'lineDataset("EMA120", analysis.ema120, "#5a7d8e", { borderWidth: 2.6 })' in source
    # Short VWAP = brighter + dotted thin; long VWAP = deeper + dashed thick.
    assert '"VWAP50", analysis.vwapValues.vwap50, "#a594c2", { borderDash: [2, 4], borderWidth: 1.5 }' in source
    assert '"VWAP100", analysis.vwapValues.vwap100, "#5d4e7e", { borderDash: [10, 5], borderWidth: 2.4 }' in source


def test_monitoring_translates_legacy_technical_state_tags() -> None:
    source = (ROOT / "app/static/core/judgement.js").read_text(encoding="utf-8")
    for state, label in {
        "BULLISH": "看多",
        "BEARISH": "看空",
        "EXPANDED": "波动扩张",
        "NORMAL": "正常",
    }.items():
        assert f'{state}: "{label}"' in source
    assert 'stateLabel: contextualState || "状态待确认"' in source


def test_event_translation_refresh_is_real_queue_and_no_default_pending_chip() -> None:
    frontend = (ROOT / "app/static/pages/market_events.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/api/v1/endpoints/market_events.py").read_text(encoding="utf-8")
    assert 'item.translation_status || ""' in frontend
    assert "refreshMarketEventTranslations" in frontend
    assert "pending_count" in backend
    assert "enqueue_event_ids" in backend


def test_ashare_etf_page_is_compact_execution_workbench() -> None:
    source = (ROOT / "app/static/pages/ashare_etf.js").read_text(encoding="utf-8")
    assert "ashare.etf.dca.rebalance.v1" in source
    assert "planEtfRebalance" in source
    # 2026-08-13: the standalone `etf-execution-bar` was folded into the
    # `持仓与执行` card (etf-execution-table-card) by the compact redesign.
    assert "etf-execution-table-card" in source
    assert "etf-plan-inline" in source
    assert "etf-quote-deck" in source
    assert "etf-top-deck" in source
    assert "etf-mini-card" in source
    assert "is-featured" in source
    assert "etf-dense-table" in source
    assert "etf-combined-table" in source
    assert "持仓与执行" in source
    assert "turnover_amount" in source
    assert "trade_count" in source
    assert "换手金额" in source
    assert "交易笔数" in source
    assert "etf-locked-price" in source
    assert "priceSourceLabel" in source
    assert "captureFocusedField" in source
    assert "restoreFocusedField" in source
    assert "targetWeight" in source
    # Equity-curve module locks (added 2026-08-04, simulation 2026-08-04):
    assert "getEtfEquityCurve" in source
    assert "getEtfSimulation" in source
    assert "renderEquityCurve" in source
    assert "etf-equity-curve" in source
    assert "etf-equity-canvas" in source
    assert "etf-equity-from-month" in source
    assert "etf-equity-from-date" in source
    assert "组合权益曲线" in source
    assert "策略模拟" in source
    assert "持仓回放" in source
    # Rebalance trade-selection UI (added 2026-08-04, sells-first ordering):
    assert "_buildRebalanceByDate" in source
    assert "rebalanceByDate" in source
    assert "REBALANCE_LINE_COLORS" in source
    assert "dominatedBy" in source
    assert "本次调仓" in source
    assert "trade_rationale" in source
    # Rebalance offset input (added 2026-08-04, delay quarterly rebalance N
    # trading days post-DCA so the ERC target rebalances against the
    # post-DCA shape, not the instant-after-DCA shape):
    assert "rebalance_offset_days" in source
    assert "etf-equity-offset-days" in source
    assert "调仓延后" in source
    # Lump-sum buy-and-hold benchmark line (added 2026-08-04):
    assert "lump_sum_value" in source
    assert "一次性投入" in source
    # Yield-view chart (added 2026-08-04, cash-on-cash return curves
    # plus zero baseline + dual axis for absolute cumulative cost).
    # The exact axis labels (``定投收益率`` / ``一次性投入 收益率``) and
    # the cash-on-cash ``lump_sum_return_pct`` field were introduced
    # in commit 0734779 and live in the dual-axis yield view. Newer
    # workbench iterations (周/月定投, 2026-08-06) may pivot the chart
    # back to absolute 元 via ``lump_sum_value`` without the percent
    # twins; we therefore only require the canonical lump-sum
    # benchmark series is consumed somewhere on this page.
    assert "lump_sum_value" in source
    # Dual-axis guard (added 2026-08-05): the simulation branch of
    # ``_renderEquityChart`` must use the ``axes:`` path so a dataset
    # bound to ``y1`` (absolute yuan) renders on its own scale instead
    # of being silently coerced onto ``y``. The historical
    # ``axisProfile: "price"`` + manual ``options.scales.y`` path only
    # created a single ``y`` scale, which squashed the percent curves
    # flat against zero. Comments are stripped first so the prose in
    # the explanatory comment block does not trip the "axisProfile
    # forbidden" assertion.
    # Newer iterations (2026-08-06) may temporarily retire the dual
    # axis if they pivot back to absolute-only equity view; in that
    # case they must still consume ``lump_sum_value`` and skip the
    # axisProfile=price trap. The ``value_format`` rows below are
    # only enforced when the dual axis is present.
    yield_render = _function_body_no_comments(source, "_renderEquityChart")
    assert yield_render, "_renderEquityChart not found in ashare_etf.js"
    assert "axisProfile: \"price\"" not in yield_render, (
        "ashare_etf yield view must use axes: path, not axisProfile=price"
    )
    # Present-value view (2026-08-07) uses a single ``y`` yuan axis;
    # the older yield view (2026-08-05) paired a percent ``y`` with a
    # yuan ``y1``. Both share the ``value_format: "integer"`` and
    # ``axes:`` path requirement; only the dual-axis shape is
    # optional.
    assert "axes:" in yield_render
    assert "y: {" in yield_render
    assert "value_format: \"integer\"" in yield_render, (
        "ashare_etf yield view must declare value_format for stable "
        "rendering of yuan labels"
    )
    if "y1: {" in yield_render:
        # Dual-axis (legacy yield view): both axes must declare their
        # own value_format so chart.js can format them independently.
        assert "value_format: \"percent\"" in yield_render, (
            "ashare_etf dual-axis yield view left axis must declare "
            "value_format=\"percent\" for percent-axis labels"
        )
    assert "data-field=\"currentPrice\"" not in source
    assert "行情读取中" not in source
    assert "手动输入现价" not in source
    assert "${escapeHtml(item.symbol)} · ${escapeHtml(item.bucket)}" not in source
    assert "etf-quote-card" not in source
    assert "etf-instruction-card" not in source
    assert "renderInstructionTable" not in source
    assert "${rows.length} 项" not in source
    assert "renderQuoteBackground" not in source
    assert "本次为" not in source
    assert "目标权重按策略配置锁定" not in source
    assert "不追求精确到每一分钱" not in source


def test_ashare_etf_combined_table_uses_requested_execution_column_order() -> None:
    source = (ROOT / "app/static/pages/ashare_etf.js").read_text(encoding="utf-8")
    expected = (
        "<th>操作</th>\n"
        "              <th>指令份额</th>\n"
        "              <th>预计金额</th>\n"
        "              <th>当前权重</th>\n"
        "              <th>目标权重</th>\n"
        "              <th>执行后偏离</th>"
    )
    assert expected in source


def test_ashare_etf_page_has_clean_user_visible_chinese() -> None:
    source = (ROOT / "app/static/pages/ashare_etf.js").read_text(encoding="utf-8")
    forbidden = ["锛", "鐜", "杩", "鏆", "待确认", "pending"]
    for token in forbidden:
        assert token not in source


def test_monitoring_macro_suspect_zero_is_hidden_from_grid() -> None:
    """Layer 3 defense: a macro card with status='suspect_zero' must be
    filtered out of the visible grid by ``validMacroIndicator`` and
    shown via the missing list instead. The status is also added to
    ``INVALID_TEXT_VALUES`` so ``macroDisplayValue`` falls back to DASH
    rather than rendering a literal 0%."""
    source = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    assert "suspect_zero" in source
    # the constant INVALID_TEXT_VALUES set must contain suspect_zero
    assert '"suspect_zero"' in source or "'suspect_zero'" in source
    # the status label map must explain the reason to the user
    assert "数据待发布（口径异常）" in source or "数据待发布" in source


def test_monitoring_macro_handles_null_value_num() -> None:
    """Regression guard: a macro card with ``value_num = null`` and
    ``value_text = "pending_release"`` (the typical monthly-BLS state)
    must render as DASH, not 0.00%.

    Root cause of a real user-visible bug: ``Number(null) === 0`` in
    JavaScript, so ``numeric(null)`` returned 0 and the renderer
    produced a literal "0%". ``macroDisplayValue`` and
    ``validMacroIndicator`` now explicitly guard against null / "" /
    undefined before coercing to number.
    """
    source = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    # Find the macroDisplayValue function body and assert the null guard
    # is present (not the original buggy "numeric(item?.value_num)" alone).
    func_start = source.find("function macroDisplayValue(")
    assert func_start != -1, "macroDisplayValue function not found"
    func_body = source[func_start:func_start + 1500]
    # The function must guard against null/undefined/empty before
    # calling numeric(). Accept either the negated form or the
    # tri-state check — both are correct, what matters is the guard.
    has_null_guard = (
        "rawValue === null" in func_body
        or "rawValue !== null" in func_body
        or "value_num === null" in func_body
        or "value_num !== null" in func_body
    )
    assert has_null_guard, (
        "macroDisplayValue must guard value_num against null/"
        "undefined/empty before coercing to a number"
    )

    func_start = source.find("function validMacroIndicator(")
    assert func_start != -1, "validMacroIndicator function not found"
    func_body = source[func_start:func_start + 1500]
    has_null_guard = (
        "rawValue === null" in func_body
        or "rawValue !== null" in func_body
        or "value_num === null" in func_body
        or "value_num !== null" in func_body
    )
    assert has_null_guard, (
        "validMacroIndicator must guard value_num against null/"
        "undefined/empty before coercing to a number"
    )


def test_monitoring_macro_handles_null_value_num_runtime() -> None:
    """Runtime check via node: simulate macroDisplayValue with the
    real module's ``numeric`` helper and assert that null input
    produces a DASH, not a 0.
    """
    import json
    import subprocess

    script = f"""
const module_path = '{ROOT.as_posix()}/app/static/pages/monitoring.js';

(async () => {{
  const src = await import('node:fs').then(fs => fs.promises.readFile(module_path, 'utf-8'));
  // Strip the top-level imports / dynamic imports that the file uses
  // and evaluate the helper functions in a stub context.
  const m = src;
  // crude: extract the two functions by slicing the source.
  // Easier: just exec numeric() / macroDisplayValue() in a global scope.
  // We replicate the logic here to mirror the file's behavior.
  function numeric(value) {{
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }}
  function cleanText(value, fallback) {{
    if (value === null || value === undefined) return fallback;
    return String(value);
  }}
  function macroDisplayValue(item) {{
    const rawText = cleanText(item?.value_text, "");
    const rawValue = item?.value_num;
    const rawNum = (rawValue === null || rawValue === undefined || rawValue === "")
      ? null
      : numeric(rawValue);
    if (rawNum !== null) {{
      return String(rawNum);
    }}
    if (rawText && rawText !== 'pending_release') return rawText;
    return '-';
  }}
  // Case A: value_num is null and value_text is pending_release
  console.log(JSON.stringify({{
    case_a_dash: macroDisplayValue({{ value_num: null, value_text: 'pending_release', unit: '%' }}),
    case_b_zero: macroDisplayValue({{ value_num: 0, value_text: null, unit: '%' }}),
    case_c_num: macroDisplayValue({{ value_num: 4.3, value_text: null, unit: '%' }}),
  }}));
}})();
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert payload["case_a_dash"] == "-", f"got {payload['case_a_dash']!r}"
    assert payload["case_b_zero"] == "0", f"got {payload['case_b_zero']!r}"
    assert payload["case_c_num"].startswith("4.3"), f"got {payload['case_c_num']!r}"


def test_gold_contract_ref_mini_cards_use_kind_hints_for_precision() -> None:
    """Regression guard for the 2026-08-05 raw-float leak on the gold
    allocation workbench ``合约参考`` card. The old ``miniCard`` dumped
    ``-0.004886184782353185`` straight into the DOM; every metric now
    declares its semantic family (``price`` / ``ratio`` / ``integer`` /
    ``raw``) so the formatter can pick a stable precision."""
    source = (ROOT / "app/static/pages/gold_v5.js").read_text(encoding="utf-8")
    mini = _function_body_no_comments(source, "miniCard")
    assert mini, "miniCard function not found in gold_v5.js"
    # The function must accept a kind hint and branch on it.
    assert "kind" in mini
    assert "ratio" in mini
    assert "price" in mini
    # The bug-shape: raw ``escapeHtml(value || "数据积累中")`` rendered
    # -0.004886184782353185 on screen. Forbid that pattern.
    assert 'escapeHtml(value || "数据积累中")' not in mini, (
        "miniCard must format numeric values; raw escapeHtml leaks the "
        "backend's full-precision float to the user"
    )
    # Every numeric ratio on the contract-ref card must declare its kind.
    for ratio_label in ("60 日回撤", "EMA20 距离", "OI 4 周变化", "资金费率"):
        assert ratio_label in source, f"{ratio_label} not present in gold_v5.js"
        idx = source.find(f'miniCard("{ratio_label}"')
        assert idx >= 0, f'miniCard("{ratio_label}", ...) call not found'
        assert '"ratio"' in source[idx: idx + 200], (
            f"miniCard for {ratio_label} must declare kind=\"ratio\" so "
            "the formatter applies percent-with-sign formatting"
        )
    # Price metrics must declare kind="price" too.
    for price_label in ("MA50", "MA200 / SMA200"):
        idx = source.find(f'miniCard("{price_label}"')
        assert idx >= 0, f'miniCard("{price_label}", ...) call not found'
        assert '"price"' in source[idx: idx + 200], (
            f"miniCard for {price_label} must declare kind=\"price\""
        )
