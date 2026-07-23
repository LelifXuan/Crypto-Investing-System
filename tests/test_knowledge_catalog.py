from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "app" / "static" / "core" / "knowledge.js"
DOM_PATH = ROOT / "app" / "static" / "core" / "dom.js"
KNOWLEDGE_PAGE_PATH = ROOT / "app" / "static" / "pages" / "knowledge.js"


def _node(script: str):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _load_knowledge_sections() -> list[dict]:
    return _node(
        f"""
import {{ knowledgeSections }} from 'file:///{KNOWLEDGE_PATH.as_posix()}';
console.log(JSON.stringify(knowledgeSections));
"""
    )


def test_knowledge_catalog_imports_without_syntax_errors() -> None:
    result = subprocess.run(
        ["node", "--check", str(KNOWLEDGE_PATH)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert _load_knowledge_sections()


def test_non_derivative_terms_have_useful_when_and_example() -> None:
    missing = _node(
        f"""
import {{ knowledgeSections }} from 'file:///{KNOWLEDGE_PATH.as_posix()}';
const missing = [];
for (const section of knowledgeSections) {{
  for (const item of section.items) {{
    if (item.type === 'guide' || item.category === 'btc-derivatives') continue;
    const usefulWhen = Array.isArray(item.useful_when) ? item.useful_when.filter(Boolean) : [];
    if (usefulWhen.length < 3 || !String(item.example || '').trim()) {{
      missing.push({{ id: item.id, usefulWhen: usefulWhen.length, hasExample: Boolean(String(item.example || '').trim()) }});
    }}
  }}
}}
console.log(JSON.stringify(missing));
"""
    )

    assert not missing, f"terms missing useful_when/example: {missing[:20]}"


def test_knowledge_catalog_schema_seed_terms_and_utf8() -> None:
    sections = _load_knowledge_sections()
    all_items = [item for section in sections for item in section["items"]]
    ids = {item["id"] for item in all_items}

    required_ids = {
        "sma",
        "ema",
        "vwap",
        "vegas_channel",
        "kdj",
        "cci",
        "volume_surge_ratio",
        "percent_b",
        "bollinger_bandwidth",
        "adx",
        "index_price",
        "basis_rate",
        "price_deviation",
        "market_structure",
        "support_resistance",
        "volume_profile",
        "entry_trigger",
        "stop_loss",
        "take_profit",
        "risk_reward_ratio",
        "observe_only",
        "wait_confirmation",
        "cpi",
        "nfp",
        "fomc",
        "dxy",
        "us10y",
        "mvrv",
        "onchain_data_availability",
        "cache_state",
        "portable_proxy_detection",
        "macro_seed_cache",
        "stale_while_revalidate",
        "scoring_eligibility",
        "api_healthcheck",
        "source_priority_chain",
        "macro_never_empty_contract",
        "secret_hygiene",
        "cache_freshness_window",
        "signal_to_trade_pipeline",
        "cash_flow_etf",
        "halo_etf",
        "ashare_etf_quote_source",
        "etf_vs_perp_spot",
        "dividend_cashflow",
        "heavy_assets_low_obsolescence",
    }
    assert required_ids <= ids

    required_fields = {
        "id",
        "term",
        "aliases",
        "definition",
        "summary",
        "display_mode",
        "importance",
        "page_refs",
        "related_terms",
        "tags",
    }
    for item in all_items:
        assert required_fields.issubset(item.keys())
        assert item["definition"] or item["summary"]
        serialized = json.dumps(item, ensure_ascii=False)
        for token in ["????", "锟", "閺", "鐢", "鐩稿叧椤甸潰"]:
            assert token not in serialized

    by_id = {item["id"]: item for item in all_items}
    ema_text = json.dumps(by_id["ema"], ensure_ascii=False)
    for phrase in ("多头排列", "空头排列", "均线发散", "均线纠缠"):
        assert phrase in ema_text

    vegas_text = json.dumps(by_id["vegas_channel"], ensure_ascii=False)
    for phrase in ("EMA12 上穿", "EMA12 下穿", "通道金叉", "通道死叉"):
        assert phrase in vegas_text

    vwap_text = json.dumps(by_id["vwap"], ensure_ascii=False)
    for phrase in ("VWAP50", "VWAP100", "1%", "0.5%"):
        assert phrase in vwap_text

    etf_text = json.dumps(by_id["halo_etf"], ensure_ascii=False)
    assert "电信" in etf_text
    assert "军工" in etf_text
    assert "基建" in etf_text


def test_knowledge_alias_lookup_normalizes_common_variants() -> None:
    hits = _node(
        f"""
import {{ findKnowledgeTerm }} from 'file:///{KNOWLEDGE_PATH.as_posix()}';
const hits = [
  findKnowledgeTerm('NATR14')?.id,
  findKnowledgeTerm('NATR 14')?.id,
  findKnowledgeTerm('Mark Price')?.id,
  findKnowledgeTerm('Break of Structure')?.id,
  findKnowledgeTerm('1M')?.id,
  findKnowledgeTerm('CPI')?.id,
  findKnowledgeTerm('US 10Y')?.id,
  findKnowledgeTerm('HALO ETF')?.id,
  findKnowledgeTerm('159201')?.id,
];
console.log(JSON.stringify(hits));
"""
    )
    assert hits == [
        "natr",
        "natr",
        "mark_price",
        "bos_choch",
        "timeframe",
        "cpi",
        "us10y",
        "halo_etf",
        "cash_flow_etf",
    ]


def test_tooltip_is_concise_and_links_to_knowledge() -> None:
    payload = _node(
        f"""
import {{ knowledgeTooltip, knowledgeTooltipText }} from 'file:///{DOM_PATH.as_posix()}';
const texts = [
  knowledgeTooltipText('EMA'),
  knowledgeTooltipText('Vegas'),
  knowledgeTooltipText('Depth 10bps'),
];
console.log(JSON.stringify({{
  texts,
  html: knowledgeTooltip('EMA'),
}}));
"""
    )
    for text in payload["texts"]:
        assert len(text) < 180
    assert "查看百科" in payload["html"]
    assert "/knowledge-page#ema" in payload["html"]


def test_knowledge_page_remounts_when_spa_dom_belongs_to_previous_page() -> None:
    payload = _node(
        f"""
globalThis.window = {{
  location: {{ hash: '' }},
  addEventListener() {{}},
  setTimeout() {{}},
  clearTimeout() {{}},
  requestAnimationFrame(callback) {{ callback(); }},
}};
const elements = new Map();
let rootInnerHTML = '<section class="market-events-page">最近市场事件与新闻</section>';
const root = {{
  get innerHTML() {{ return rootInnerHTML; }},
  set innerHTML(value) {{
    rootInnerHTML = String(value);
    if (rootInnerHTML.includes('id="knowledge-top"')) {{
      elements.set('knowledge-top', {{ id: 'knowledge-top', scrollIntoView() {{}} }});
    }}
  }},
}};
globalThis.document = {{
  getElementById(id) {{
    if (id === 'page-root') return root;
    return elements.get(id) || null;
  }},
  querySelector() {{ return null; }},
  querySelectorAll() {{ return []; }},
}};
const module = await import('file:///{KNOWLEDGE_PAGE_PATH.as_posix()}?case=remount');
await module.renderKnowledge();
root.innerHTML = '<section class="market-events-page">最近市场事件与新闻</section>';
elements.delete('knowledge-top');
await module.renderKnowledge();
console.log(JSON.stringify({{
  hasKnowledgeTop: rootInnerHTML.includes('id="knowledge-top"'),
  hasKnowledgeHero: rootInnerHTML.includes('knowledge-hero'),
  stillMarketEvents: rootInnerHTML.includes('market-events-page'),
}}));
"""
    )

    assert payload["hasKnowledgeTop"] is True
    assert payload["hasKnowledgeHero"] is True
    assert payload["stillMarketEvents"] is False


def test_btc_derivatives_terms_are_available_to_dashboard_tooltips() -> None:
    sections = _load_knowledge_sections()
    terms = {
        item["term"]: item
        for section in sections
        for item in section["items"]
    }

    for label in {"Call Wall", "Put Wall", "Max Pain", "Constant Maturity"}:
        assert label in terms
        assert "btc-derivatives" in terms[label]["page_refs"]
        assert terms[label]["summary"]
        assert terms[label]["risk_note"]


# ---------------------------------------------------------------------------
# Round 2-A: BTC 衍生品核心新概念 (V1.7+ skew_25d / cross_expiry fallback)
# ---------------------------------------------------------------------------


def _btc_derivative_term_ids() -> set[str]:
    sections = _load_knowledge_sections()
    return {
        item["id"]
        for section in sections
        for item in section["items"]
        if "btc-derivatives" in (item.get("page_refs") or [])
    }


def test_btc_derivatives_section_exposes_25d_skew() -> None:
    """The 25-delta skew computed by options_metrics.skew_25d must be
    discoverable from the knowledge base so the 25D Skew chart tooltip and
    the terminal summary sub-module can link to it."""
    ids = _btc_derivative_term_ids()
    assert "skew_25d" in ids, (
        "skew_25d is the headline metric on the BTC derivatives page; the "
        "knowledge base must surface it as a discoverable term"
    )

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["skew_25d"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"], "skew_25d must carry a non-empty summary"
    assert item["definition"], "skew_25d must carry a non-empty definition"
    assert item["risk_note"], "skew_25d is a risk-bearing metric"
    # Cross-link to the greeks that drive it.
    related = set(item.get("related_terms", []))
    assert "delta" in related, "skew_25d must reference the Delta greek"


def test_btc_derivatives_section_exposes_risk_reversal_25d() -> None:
    ids = _btc_derivative_term_ids()
    assert "risk_reversal_25d" in ids, (
        "options_metrics.skew_25d also returns risk_reversal (negated skew); "
        "users comparing bullish / bearish positioning on BTC options need "
        "to find this term"
    )

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["risk_reversal_25d"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    assert "skew_25d" in set(item.get("related_terms", [])), (
        "risk_reversal_25d and skew_25d describe the same data from opposite "
        "sides; the related_terms link must exist in both directions"
    )


def test_btc_derivatives_section_exposes_delta_band() -> None:
    """options_metrics.skew_25d stamps each result with delta_band
    (exact_25d / near_25d / outside_band). Users see this band on the chart
    but have no way to look up what it means."""
    ids = _btc_derivative_term_ids()
    assert "delta_band" in ids

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["delta_band"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    # delta_band must mention the three possible values somewhere in the
    # term body so the user can distinguish them.
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    for variant in ("exact_25d", "near_25d", "outside_band"):
        assert variant in body, (
            f"delta_band term body must list the {variant!r} variant so users "
            f"can decode the chart annotation"
        )


def test_btc_derivatives_section_exposes_cross_expiry_fallback() -> None:
    """When the effective_expiry chain can't produce a 25D call/put, the
    service falls back to a neighbouring standard expiry. The knowledge base
    must surface this so users understand why a 'cross_expiry' label appears
    on the chart."""
    ids = _btc_derivative_term_ids()
    assert "cross_expiry_fallback" in ids

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["cross_expiry_fallback"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    assert "delta-source" in set(item.get("related_terms", [])), (
        "delta-source is the field on the cache point that records whether "
        "the fallback was used; users looking up either should find the other"
    )


def test_btc_derivatives_section_exposes_series_break() -> None:
    """service._break_legacy_rolls sets series_break_reason on cache points
    where cost or skew chains would otherwise be misleading. The knowledge
    base must surface this so users understand the '序列断开' annotation."""
    ids = _btc_derivative_term_ids()
    assert "series_break" in ids

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["series_break"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    # The two known break reasons must be reflected in the body so users
    # can map the chart label to the underlying mechanism.
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    assert "expiry_rollover" in body
    assert "method_change" in body


def test_btc_derivatives_section_exposes_roll_expiry() -> None:
    """constant_maturity mode rolls the selected expiry to the next standard
    expiry once the current one is too close to expiry. Users see this as
    'next_check: next_4h_close' on the trade plan and need a way to look it up."""
    ids = _btc_derivative_term_ids()
    assert "roll_expiry" in ids

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["roll_expiry"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    assert "constant-maturity" in set(item.get("related_terms", [])), (
        "roll_expiry is the mechanism behind Constant Maturity; users should "
        "be able to navigate between the two"
    )


def test_btc_derivatives_section_exposes_iv_term_structure() -> None:
    """implied-volatility mentions 'term structure' in passing; promote it
    to a first-class term so users can search for it directly."""
    ids = _btc_derivative_term_ids()
    assert "iv_term_structure" in ids

    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id["iv_term_structure"]
    assert "btc-derivatives" in item["page_refs"]
    assert item["summary"]
    # Term must mention both contango and backwardation so users can tell
    # them apart from the chart's single-line label.
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    assert "contango" in body
    assert "backwardation" in body
    assert "implied-volatility" in set(item.get("related_terms", [])), (
        "iv_term_structure should be linked to the base IV term"
    )


# ---------------------------------------------------------------------------
# Round 2-derivatives: 12 hard gaps + 7 soft gaps discovered by the recent
# page-vs-catalog audit. Each term below is rendered somewhere on the BTC
# derivatives page (chart legend, KPI card, Maturity Ladder column, status
# badge, hedge form, etc.) but had no discoverable knowledge entry.
# ---------------------------------------------------------------------------


def _require_term(term_id: str) -> dict:
    sections = _load_knowledge_sections()
    by_id = {it["id"]: it for s in sections for it in s["items"]}
    item = by_id.get(term_id)
    assert item is not None, f"term {term_id!r} must exist in the knowledge catalog"
    assert "btc-derivatives" in (item.get("page_refs") or []), (
        f"{term_id!r} must be exposed on the btc-derivatives page"
    )
    assert item.get("summary"), f"{term_id!r} must carry a non-empty summary"
    return item


# --- 12 hard gaps ---------------------------------------------------------


def test_oi_concentration_term_surfaces_in_derivatives_section() -> None:
    """Maturity Ladder renders 'XX% 集中度' under each Call/Put Wall row;
    users need a way to look up what that percentage means."""
    item = _require_term("oi-concentration")
    related = set(item.get("related_terms", []))
    assert "call-wall" in related and "put-wall" in related, (
        "oi-concentration must reference both call-wall and put-wall"
    )


def test_protection_cost_term_covers_call_put_debit() -> None:
    """'Call 保护成本' / 'Put 保护成本' / '借记价差成本' all appear in the
    options_risk_premium_history legend; one unified protection-cost term
    must cover all three flavours."""
    item = _require_term("protection-cost")
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    # call/put/debit are all rendered on the chart; the term must cover all
    # three in its body so the cross-link is discoverable.
    for flavour in ("call", "put", "debit"):
        assert flavour in body, (
            f"protection-cost term must mention '{flavour}' in its body so "
            f"users searching by chart legend word can find it; got: {body}"
        )


def test_debit_spread_cost_term_explains_construction() -> None:
    """Debit spread is the finite-risk alternative to naked call/put
    protection; users need to look up why the cost is lower and the
    protection capped."""
    _require_term("debit-spread-cost")


def test_funding_zscore_term_explains_normalization() -> None:
    """The 'Funding Z' legend on leverage_pressure_timeline is the
    z-score-normalised funding rate, not raw funding. Users see the
    legend but have no way to decode it."""
    item = _require_term("funding-zscore")
    related = set(item.get("related_terms", []))
    assert "funding-rate" in related, (
        "funding-zscore must reference funding-rate so users navigating "
        "between the two find the connection"
    )


def test_put_call_oi_ratio_term_explains_baseline() -> None:
    """options_risk_premium_history plots put/call OI ratio with a
    'Put/Call = 1' baseline annotation; users need to know what >1 and <1
    mean."""
    _require_term("put-call-oi-ratio")


def test_put_call_volume_ratio_term_explains_baseline() -> None:
    _require_term("put-call-volume-ratio")


def test_atm_iv_term_distinguishes_from_25d_skew() -> None:
    """ATM IV is the at-the-money volatility, distinct from 25D Skew
    (which is the wing of the smile). Both appear in term_structure chart
    and Maturity Ladder."""
    item = _require_term("atm-iv")
    related = set(item.get("related_terms", []))
    assert "implied-volatility" in related
    assert "iv-term-structure" in related


def test_annualized_basis_term_explains_period_conversion() -> None:
    """'年化 Basis' on the term_structure chart converts per-period basis
    to annualised rate; users need to know why two basis values aren't
    directly comparable."""
    item = _require_term("annualized-basis")
    related = set(item.get("related_terms", []))
    assert "basis-rate" in related


def test_wall_strength_term_quantifies_magnet() -> None:
    """key_level_strip combines movement + distance_pct + shift_pct into a
    qualitative 'magnet' strength. Users see the composite on the card but
    no single term explains how the three are weighted."""
    item = _require_term("wall-strength")
    related = set(item.get("related_terms", []))
    assert "call-wall" in related and "put-wall" in related


def test_standard_expiry_term_explains_cycle_labels() -> None:
    """'月度交割 / 季度交割 / 四巫日窗口 / ETF调仓窗口' labels appear in
    expiry_context; users need a term that explains why these windows
    matter for option positioning."""
    _require_term("standard-expiry")


def test_maturity_band_term_explains_bucketing() -> None:
    """'期限桶 30D / 60D / 90D' toolbar + '近月 / 中期 / 远月' table
    column both render the same concept; the term must explain the
    bucket definition."""
    _require_term("maturity-band")


def test_protection_cost_regime_term_explains_thresholds() -> None:
    """'保护成本偏高 / 偏低 / 处于常态区间' is rendered as a state badge
    based on history_percentile + change_1d/7d. Users need a term that
    explains the thresholds."""
    _require_term("protection-cost-regime")


# --- 7 soft gaps ----------------------------------------------------------


def test_iv_state_term_explains_band_labels() -> None:
    """'隐含波动率偏高 / 偏低 / 处于常态区间' is rendered on the IV card
    (iv_state). One term covers all four labels (incl. data_insufficient)."""
    _require_term("iv-state")


def test_liquidity_status_term_in_derivatives_section() -> None:
    """Maturity Ladder shows '流动性可用 / 流动性降级' under each row;
    this is the row-level trustworthiness signal. The cross-link to
    depth_slippage_spread (market-microstructure depth) lets users searching
    '流动性' find both concepts and read their differences."""
    item = _require_term("liquidity-status")
    # The body must explain that this is row-level trustworthiness, NOT
    # order-fill liquidity.
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    assert "数字" in body or "信度" in body or "可信" in body, (
        "liquidity-status term body must make clear this is row-level data "
        "trustworthiness, not order-fill liquidity"
    )
    related = set(item.get("related_terms", []))
    # Cross-link to the market-microstructure term so users searching
    # '流动性' land on both and can read the difference.
    assert "depth_slippage_spread" in related, (
        "liquidity-status must cross-link depth_slippage_spread so users "
        "discover both meanings of 'liquidity' from a single search"
    )


def test_hedge_plan_field_term_in_derivatives_section() -> None:
    """renderHedgePlan() outputs '保护区 / 预计成本 / 范围内 / 超预算 /
    未判断' which are user-facing fields. The term must enumerate them."""
    item = _require_term("hedge-plan-field")
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    for required in ("保护区", "预计成本", "预算"):
        assert required in body, (
            f"hedge-plan-field term must mention {required!r}; got: {body}"
        )


def test_strike_surface_term_in_derivatives_section() -> None:
    """strike_surface chart visualises OI + IV across strikes (the smile).
    Users see '行权价表面：OI 与 IV' as the chart title."""
    _require_term("strike-surface")


def test_volatility_smile_term_in_derivatives_section() -> None:
    """The shape of IV across strikes is a smile; 25D Skew is one slice of
    it. The term must explain that relationship so users don't confuse
    the two."""
    item = _require_term("volatility-smile")
    related = set(item.get("related_terms", []))
    assert "skew_25d" in related


def test_iv_percentile_term_in_derivatives_section() -> None:
    """protection_cost_regime.history_percentile and the IV percentiles
    mentioned in implied-volatility's how_to_use are this single concept."""
    _require_term("iv-percentile")


def test_portfolio_type_term_in_derivatives_section() -> None:
    """renderHedgePlanner() picks portfolio_type: short_grid / long_grid /
    spot_only / neutral_grid. Users see the label in the form dropdown."""
    item = _require_term("portfolio-type")
    body = " ".join(
        str(v) for v in (item["summary"], item["definition"], item["how_to_use"])
    ).lower()
    # Spot and grid are the two axes of the picker; both must appear.
    assert "spot" in body
    assert "grid" in body


def test_term_factory_supports_guide_fields() -> None:
    """term() must accept and expose guide-only fields without breaking existing ones."""
    payload = _node(
        f"""
import {{ term }} from 'file:///{KNOWLEDGE_PATH.as_posix()}';
const guide = term('test-guide', 'Test Guide', {{
  type: 'guide',
  purpose: 'A test purpose that is long enough',
  when_to_use: ['first situation', 'second situation'],
  page_walkthrough: ['step one', 'step two'],
  data_lineage: ['src1 -> dst1'],
  caveats: ['caveat one'],
  related_pages: ['ai-strategy'],
}});
console.log(JSON.stringify(guide));
"""
    )
    assert payload["type"] == "guide"
    assert payload["purpose"].startswith("A test")
    assert len(payload["when_to_use"]) == 2
    assert len(payload["page_walkthrough"]) == 2
    assert payload["data_lineage"] == ["src1 -> dst1"]
    assert payload["caveats"] == ["caveat one"]
    assert payload["related_pages"] == ["ai-strategy"]


def test_page_guides_section_exposes_three_first_phase_guides():
    """pageGuidesSection must exist and contain monitoring-overview/ai-strategy/btc-derivatives."""
    sections = _load_knowledge_sections()
    page_guides = next((s for s in sections if s["id"] == "page-guides"), None)
    assert page_guides is not None, "page-guides section not found"
    item_ids = [item["id"] for item in page_guides["items"]]
    for required_id in ("monitoring-overview", "ai-strategy", "btc-derivatives"):
        assert required_id in item_ids, f"missing guide for {required_id}"


def test_page_guides_required_fields_are_populated():
    """Each type='guide' entry must populate all guide-specific fields with non-trivial content."""
    sections = _load_knowledge_sections()
    guides = next(s for s in sections if s["id"] == "page-guides")["items"]
    assert len(guides) >= 3, "expected at least 3 first-phase guides"
    for g in guides:
        assert g.get("type") == "guide", f"{g['id']}: type must be 'guide'"
        assert len(g.get("purpose", "")) >= 10, f"{g['id']}: purpose too short"
        assert len(g.get("when_to_use", [])) >= 1, f"{g['id']}: need ≥1 when_to_use"
        assert len(g.get("page_walkthrough", [])) >= 2, f"{g['id']}: need ≥2 walkthrough steps"


# ---------------------------------------------------------------------------
# Stale-content guards: terms whose summaries reference the old field names
# or pre-V1.7 / pre-V2 concepts must surface modern aliases so users can find
# them under either name. This locks the rename without forcing a full term
# rewrite.
# ---------------------------------------------------------------------------


def test_real_yield_exposes_v2_aliases():
    """V2 renamed TIPS to real_yield_10y in the macro layer; the legacy
    'real_yield' term must surface the new id (and the canonical '10Y TIPS'
    phrasing) as aliases so search still resolves."""
    sections = _load_knowledge_sections()
    items = [item for s in sections for item in s["items"]]
    real_yield = next((it for it in items if it["id"] == "real_yield"), None)
    assert real_yield is not None, "real_yield term must exist"
    aliases = set(a.lower() for a in real_yield.get("aliases", []))
    for required in ("real_yield_10y", "tips_real_yield", "10y tips"):
        assert required in aliases, (
            f"real_yield must list {required!r} as an alias so V2 renames and "
            f"the legacy '10Y TIPS' phrasing both resolve. Got aliases: "
            f"{sorted(aliases)}"
        )


def test_open_interest_terms_cross_reference_each_other():
    """The microstructure 'open_interest' term and the btc-derivatives
    'open-interest' term describe different slices of the same concept. They
    must be cross-referenced in related_terms so users moving between the
    two pages understand they belong to the same family."""
    sections = _load_knowledge_sections()
    items = [item for s in sections for item in s["items"]]
    by_id = {it["id"]: it for it in items}

    assert "open_interest" in by_id
    assert "open-interest" in by_id

    micro_related = set(by_id["open_interest"].get("related_terms", []))
    deriv_related = set(by_id["open-interest"].get("related_terms", []))

    # Cross-references must be present in both directions. The related_terms
    # entries use the OTHER term's id verbatim, so:
    # - micro `open_interest` should list "open-interest" (deriv id)
    # - deriv `open-interest` should list "open_interest" (micro id)
    assert "open-interest" in micro_related, (
        f"open_interest term should reference its derivatives counterpart "
        f"via id 'open-interest'; got related_terms={sorted(micro_related)}"
    )
    assert "open_interest" in deriv_related, (
        f"open-interest term should reference its microstructure counterpart "
        f"via id 'open_interest'; got related_terms={sorted(deriv_related)}"
    )


# ---------------------------------------------------------------------------
# Quality scan guards: certain risk-sensitive terms must surface a
# `risk_note` so users can see the caveats without having to infer them from
# the surrounding prose. The list below was derived from the recent audit
# of the catalog; the same test pins down the gaps so they cannot regress.
# ---------------------------------------------------------------------------

RISK_NOTE_REQUIRED = {
    # derivatives section (highly leveraged / liquidation-sensitive topics)
    "basis_rate": "基差 / 杠杆情绪",
    "mark_price": "强平 / 标记价",
    "price_deviation": "价格偏离 / 执行",
    # risk family
    "position_sizing": "杠杆 / 仓位",
    # structure family
    "pivot_fractal": "结构判断 / noise 误判",
    # onchain family
    "active_addresses": "链上活跃地址 / 口径差异",
    # ashare-etf family
    "dividend_cashflow": "现金流 ETF / 会计口径",
}


def test_risk_sensitive_terms_have_risk_note() -> None:
    sections = _load_knowledge_sections()
    items = [item for s in sections for item in s["items"]]
    by_id = {it["id"]: it for it in items}
    missing = []
    for term_id, topic in RISK_NOTE_REQUIRED.items():
        item = by_id.get(term_id)
        assert item is not None, (
            f"required term {term_id!r} (topic: {topic}) is missing from the "
            f"knowledge catalog entirely"
        )
        risk = item.get("risk_note")
        if not (isinstance(risk, str) and risk.strip()) and not (
            isinstance(risk, list) and any(str(x).strip() for x in risk)
        ):
            missing.append((term_id, topic))
    assert not missing, (
        "the following risk-sensitive terms must surface a risk_note so the "
        "card UI can show the caveat without users having to read every "
        f"section: {missing}"
    )


def test_guide_related_pages_reference_existing_pages():
    """Each guide's related_pages must reference pages known to the SPA."""
    valid_pages = {
        "monitoring-overview", "ai-strategy", "btc-derivatives",
        "market-analysis", "market-structure", "market-events", "macro-calendar",
        "alert-center", "knowledge-base", "ashare-etf", "gold-allocation",
    }
    sections = _load_knowledge_sections()
    guides = next(s for s in sections if s["id"] == "page-guides")["items"]
    bad: list[str] = []
    for g in guides:
        for p in g.get("related_pages", []):
            if p not in valid_pages:
                bad.append(f"{g['id']} → {p}")
    assert not bad, f"guide related_pages reference unknown pages: {bad}"


def test_fed_operations_knowledge_entries_present():
    """4 new entries: iorb_corridor, net_liquidity, fed_bs, srf."""
    sections = _load_knowledge_sections()
    all_ids = [item["id"] for s in sections for item in s["items"]]
    required = {
        "iorb_corridor",
        "net_liquidity",
        "fed_balance_sheet_operations",
        "standing_repo_facility",
    }
    missing = required - set(all_ids)
    assert not missing, f"missing knowledge entries: {missing}"


def test_v175_knowledge_entries_present():
    """2 new V1.7.5 entries: volatility_compression, bayesian_setup_probability."""
    sections = _load_knowledge_sections()
    all_ids = {item["id"] for s in sections for item in s["items"]}
    required = {"volatility_compression", "bayesian_setup_probability"}
    missing = required - all_ids
    assert not missing, f"missing knowledge entries: {missing}"
