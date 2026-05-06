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


def test_knowledge_catalog_schema_and_seed_terms() -> None:
    sections = _load_knowledge_sections()
    assert len(sections) >= 4

    all_items = [item for section in sections for item in section["items"]]
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
        assert "常见误区是孤立使用" not in serialized
        assert "非公式性规则：结合系统上下文" not in serialized

    ids = {item["id"] for item in all_items}
    assert {
        "ema",
        "bos_choch",
        "chip_structure",
        "depth_slippage_spread",
        "cpi",
        "nfp",
        "fomc",
        "dxy",
        "us10y",
    } <= ids

    by_id = {item["id"]: item for item in all_items}
    ema_text = json.dumps(by_id["ema"], ensure_ascii=False)
    for phrase in ("多头排列", "空头排列", "均线发散", "均线纠缠"):
        assert phrase in ema_text

    vegas_text = json.dumps(by_id["vegas_channel"], ensure_ascii=False)
    for phrase in ("EMA12 上穿", "EMA12 下穿", "快慢轨金叉", "快慢轨死叉"):
        assert phrase in vegas_text

    depth_text = json.dumps(by_id["depth_slippage_spread"], ensure_ascii=False)
    for phrase in ("10bps 深度", "50/100bps 深度", "spread 扩大", "单边滑点"):
        assert phrase in depth_text

    divergence_text = json.dumps(by_id["divergence"], ensure_ascii=False)
    for phrase in ("收盘价形成新高或新低", "结构破坏", "风险提醒"):
        assert phrase in divergence_text


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
    ]


def test_tooltip_uses_concise_summary_instead_of_full_manual() -> None:
    texts = _node(
        f"""
import {{ knowledgeTooltipText }} from 'file:///{DOM_PATH.as_posix()}';
const texts = [
  knowledgeTooltipText('EMA'),
  knowledgeTooltipText('Vegas'),
  knowledgeTooltipText('Depth 10bps'),
];
console.log(JSON.stringify(texts));
"""
    )
    for text in texts:
        assert len(text) < 170
        assert "查看百科" not in text
        assert "先判断环境再读" not in text
        assert "10bps 深度代表近端流动性" not in text
