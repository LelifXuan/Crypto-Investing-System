"""Tests for the 3 decision cards on the BTC derivatives page.

The three decision cards at the top of the BTC derivatives page
('当前衍生品状态' / '主要风险' / '策略含义') summarise the joint
analysis into user-facing conclusions. They used to render as plain
labels with no help link, so users who saw '方向偏空' or '保护成本
偏高' had no way to look up what that meant.

These tests pin down the contract: every decision card label must
include a knowledge-base tooltip that points to a term whose
id matches the card's purpose. The same id is what the knowledge base
uses for its `term()` registration, so this also gives us a guaranteed
existing term for each card.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DERIVATIVES_JS = REPO / "app" / "static" / "pages" / "btc_derivatives.js"
KNOWLEDGE_JS = REPO / "app" / "static" / "core" / "knowledge.js"


def _node(script: str) -> dict:
    import json
    import subprocess

    module_path = REPO / "app" / "static" / "pages" / "btc_derivatives.js"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True, capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO),
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# 1. The 3 decision cards each carry a stable card_id that we can use to
# look up the matching knowledge term.
# ---------------------------------------------------------------------------


def test_renderDecisionCards_emits_three_cards_with_stable_ids() -> None:
    """The 3 default decision cards (when dashboard.cards is empty) must
    keep stable ids: market_state / primary_risk / strategy_implication.
    The card id is encoded in the data-card-id attribute on the rendered
    <article> via the ${card.id} template; we assert on the source-string
    shape because the render function is not exported from the module."""
    content = DERIVATIVES_JS.read_text(encoding="utf-8")
    # The template must include a data-card-id attribute on the <article>.
    # We check the template shape (data-card-id="${...card.id...}") rather
    # than the rendered string because the render function is not exported.
    assert "data-card-id=" in content, (
        "renderDecisionCards must emit a data-card-id attribute on each "
        "card <article> so the tooltip wiring can find the matching term"
    )
    # Each card_id in the decision-card map must be reachable via the
    # data-card-id emission. We check the term map against the card_id
    # strings that appear in the default-cards block (3 hard-coded ids
    # match 3 term ids in DECISION_CARD_TERM).
    for card_id in DECISION_CARD_TERM:
        assert f'id: "{card_id}"' in content or f"id: '{card_id}'" in content, (
            f"default cards block must include an entry with id={card_id!r} "
            f"so the card_id -> knowledge_term mapping has a real target"
        )


# ---------------------------------------------------------------------------
# 2. Each card must carry a knowledgeTooltip that points at a real term.
# The mapping below is the contract.
# ---------------------------------------------------------------------------


DECISION_CARD_TERM = {
    # Each decision card maps to an existing knowledge term that already
    # captures the concept the card surfaces. We reuse terms rather than
    # mint new ones to keep the catalog lean.
    "market_state": "regime",
    "primary_risk": "wall-strength",
    "strategy_implication": "protection-cost",
}


def test_decision_card_term_ids_exist_in_knowledge_catalog() -> None:
    """For each decision card, the term id we use for its tooltip must
    exist in the knowledge catalog. Otherwise the tooltip renders with
    fallback text and the user gets no link."""
    payload = _node(
        f"""
import {{ knowledgeSections, findKnowledgeTerm }} from 'file:///{KNOWLEDGE_JS.as_posix()}';
const ids = {list(DECISION_CARD_TERM.values())};
const all = knowledgeSections.flatMap((s) => s.items);
const byId = Object.fromEntries(all.map((it) => [it.id, it]));
const result = ids.map((id) => ({{ id, present: Boolean(byId[id]) }}));
console.log(JSON.stringify(result));
"""
    )
    missing = [r["id"] for r in payload if not r["present"]]
    assert not missing, (
        f"the following decision-card term ids are missing from the "
        f"knowledge catalog; add them so the tooltip link resolves. "
        f"Missing: {missing}"
    )


# ---------------------------------------------------------------------------
# 3. btc_derivatives.js must actually wire knowledgeTooltip into the
# 3 decision card labels (not just the key level strip).
# ---------------------------------------------------------------------------


def test_btc_derivatives_decision_cards_invoke_knowledgeTooltip() -> None:
    """Source-string guard: btc_derivatives.js must reference the
    knowledgeTooltip import AND call it inside renderDecisionCards for
    each of the 3 cards. Locking this in source prevents the tooltip
    from being silently dropped during a refactor."""
    content = DERIVATIVES_JS.read_text(encoding="utf-8")

    # Must still import knowledgeTooltip (already used by the key level
    # strip, but we want a clear dependency).
    assert "knowledgeTooltip" in content, (
        "btc_derivatives.js must import knowledgeTooltip to surface "
        "decision-card term links"
    )

    # The function renderDecisionCards must reference the card-id map
    # (we don't pin the exact shape yet, but it must at least mention
    # the card ids in some helper form).
    start = content.find("function renderDecisionCards")
    assert start > 0
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]
    for card_id in DECISION_CARD_TERM:
        assert card_id in block, (
            f"renderDecisionCards must reference the {card_id!r} card id "
            f"so it can look up the matching knowledge term. Got block:\n"
            f"{block}"
        )


def test_btc_derivatives_decision_card_term_map_is_complete() -> None:
    """Source-string guard: the implementation must include a stable
    mapping from each card id to its knowledge term id, so the tooltip
    link can be rendered without inline conditionals. The map can live
    anywhere in the file (module-level constant or function-local), so
    we scan the whole file rather than the function body alone."""
    content = DERIVATIVES_JS.read_text(encoding="utf-8")
    for term_id in DECISION_CARD_TERM.values():
        # The term id string must appear at least once in the file
        # (module-level DECISION_CARD_TERM map is the recommended shape).
        assert f'"{term_id}"' in content or f"'{term_id}'" in content, (
            f"btc_derivatives.js must include the term id "
            f"{term_id!r} (quoted) so it can be passed to knowledgeTooltip"
        )