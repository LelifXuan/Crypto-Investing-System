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
