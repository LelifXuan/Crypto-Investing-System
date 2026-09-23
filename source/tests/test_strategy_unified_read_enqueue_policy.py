"""Read-path policy for the unified strategy snapshot (2026-09-22).

`reconcile_cached_strategy` invalidates a cached candidate plan when the live
mark price has crossed its levels. Those levels are *structural* — they come
from the candles, not from the current price — so `build_unified_strategy`
reproduces the same geometry and the guard invalidates it again.

The read path used to enqueue a full rebuild (10-18 s per instrument) on every
one of those reads, and the payload advertised `recompute_status=enqueued`,
which the drawer rendered as "正在重新推演" — a recompute that could never change
the verdict. These guards pin the fixed behaviour: rebuild on cache staleness
only, and describe an invalidated plan as invalidated.
"""

from __future__ import annotations

from pathlib import Path

from app.services.strategy_unified.trade_decision import reconcile_cached_strategy

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = ROOT / "app/api/v1/endpoints/strategy.py"


def _invalidated_plan() -> dict:
    return {
        "unified_state": {"permission": "conditional", "position_cap": "reduced"},
        "trade_decision": {
            "side": "SHORT",
            "status": "WAIT_TRIGGER",
            "permission": "conditional",
            "order_type": "CONDITIONAL_LIMIT",
            "order_status": "WAIT_PRICE",
            "lifecycle_state": "SETUP_DETECTED",
            "invalidation": 2_606.92,
            "entry_zone": [2_531.82, 2_541.97],
        },
        "trade_plans": [
            {"direction": "SHORT", "order_type": "CONDITIONAL_LIMIT", "permission": "conditional"}
        ],
    }


def test_invalidation_reason_does_not_promise_a_recompute():
    guarded, invalidated = reconcile_cached_strategy(
        _invalidated_plan(),
        latest_price=2_749.61,
        price_as_of="2026-09-22T10:00:26+00:00",
        price_source="gateio:futures.contracts",
    )

    assert invalidated is True
    decision = guarded["trade_decision"]
    assert decision["lifecycle_state"] == "SETUP_INVALIDATED"
    assert decision["permission"] == "no_trade"
    for text in (decision["invalidation_reason"], decision["primary_reason"]["message"]):
        assert "正在重新推演" not in text, (
            "the guard cannot know whether a rebuild was queued; promising one "
            "left the detail drawer reading as a stuck loading state"
        )
        assert "旧计划已作废" in text


def test_read_path_enqueues_only_for_cache_staleness():
    source = ENDPOINT.read_text(encoding="utf-8")
    cached_branch = source[
        source.index('payload["prewarm_status"] = "ready"'):
        source.index('response = await precompute_service.enqueue_hint')
    ]

    assert 'if status != "fresh":' in cached_branch, (
        "the cached read path must rebuild only when the cache row itself is stale"
    )
    assert "payload, _ = await _guard_cached_strategy(" in cached_branch, (
        "the live-price guard's invalidation flag must be discarded: a structural "
        "invalidation reproduces the same plan and the same verdict"
    )
    assert "strategy_unified_price_invalidated" not in cached_branch
    assert 'reason="strategy_unified_stale_read"' in cached_branch
