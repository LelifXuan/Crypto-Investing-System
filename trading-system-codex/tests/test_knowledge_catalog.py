from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "app" / "static" / "core" / "knowledge.js"
DOM_PATH = ROOT / "app" / "static" / "core" / "dom.js"


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


def test_knowledge_catalog_schema_seed_terms_and_utf8() -> None:
    sections = _load_knowledge_sections()
    all_items = [item for section in sections for item in section["items"]]
    ids = {item["id"] for item in all_items}

    required_ids = {
        "sma",
        "ema",
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
        "swing_high_low",
        "pivot_fractal",
        "hh_hl_lh_ll",
        "support_resistance",
        "retest",
        "liquidity_sweep",
        "range_consolidation",
        "acceptance_rejection",
        "volume_profile",
        "entry_trigger",
        "stop_loss",
        "take_profit",
        "position_sizing",
        "liquidation_distance",
        "invalidation_level",
        "risk_reward_ratio",
        "observe_only",
        "wait_confirmation",
        "cpi",
        "nfp",
        "fomc",
        "dxy",
        "us10y",
        "us2y",
        "ten_two_spread",
        "real_yield",
        "vix",
        "hy_oas",
        "financial_conditions",
        "tga",
        "on_rrp",
        "ism_pmi",
        "unemployment_rate",
        "average_hourly_earnings",
        "mvrv",
        "sth_mvrv",
        "lth_mvrv",
        "exchange_net_position_change",
        "active_addresses",
        "onchain_data_availability",
        "stale_data",
        "cache_state",
        "warmup",
        "lookback",
        "immature_indicator",
        "source_availability",
        "data_freshness",
        "signal_to_trade_pipeline",
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
        assert "????" not in serialized
        assert "�" not in serialized
        assert "鏌" not in serialized
        assert "甯" not in serialized
        assert "相关页面" not in serialized

    by_id = {item["id"]: item for item in all_items}
    ema_text = json.dumps(by_id["ema"], ensure_ascii=False)
    for phrase in ("多头排列", "空头排列", "均线发散", "均线纠缠"):
        assert phrase in ema_text

    vegas_text = json.dumps(by_id["vegas_channel"], ensure_ascii=False)
    for phrase in ("EMA12 上穿", "EMA12 下穿", "通道金叉", "通道死叉"):
        assert phrase in vegas_text

    depth_text = json.dumps(by_id["depth_slippage_spread"], ensure_ascii=False)
    for phrase in ("10bps 深度", "50/100bps 深度", "spread 扩大", "单边滑点"):
        assert phrase in depth_text


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
  findKnowledgeTerm('Funding Z-Score')?.id,
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
        "funding_rate",
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
        assert "先判断环境再说" not in text
    assert "查看百科" in payload["html"]
    assert "/knowledge-page#ema" in payload["html"]
