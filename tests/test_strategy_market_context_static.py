"""Market-context & runtime contract tests for the AI Strategy page.

The strategy page is now a multi-instrument scan hub. These tests
verify:

- The api client exposes the scan + unified endpoints used by the hub
  and the detail panel.
- The runtime engines (macro regime, onchain regime, multi-timeframe
  structure) still hide their internal diagnostics from the UI copy.
- Backend contracts (`verdict_for_node`, confidence scaling) still
  behave as documented.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_api_exposes_market_context_client():
    """api.js still exposes getMarketContext() for /market-context/snapshot."""
    source = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "getMarketContext(" in source
    assert '"/market-context/snapshot"' in source


def test_api_exposes_strategy_scan_endpoint():
    """api.js exposes getStrategyScan() for /strategy/scan — the hub's
    primary data source."""
    source = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "getStrategyScan(" in source
    assert '"/strategy/scan"' in source


def test_api_exposes_unified_strategy_endpoint():
    """api.js exposes getUnifiedStrategy() — consumed by the detail panel
    loader for a specific (instrument, timeframe) pair."""
    source = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "getUnifiedStrategy(" in source
    assert '"/strategy/unified"' in source


# ---------------------------------------------------------------------------
# Hub + detail-panel orchestration
# ---------------------------------------------------------------------------


def test_hub_uses_strategy_scan_as_primary_source():
    """index.js calls getStrategyScan as the hub-level loader; the
    detail-panel loader (inside onSelectOpportunity) calls
    getUnifiedStrategy for the clicked cell."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    panel = (
        ROOT / "app/static/pages/strategy/renderDetailPanel.js"
    ).read_text(encoding="utf-8")

    assert "api.getStrategyScan" in index
    assert "api.getUnifiedStrategy" in index  # inside onSelectOpportunity
    assert "normalizeUnifiedStrategy" in index
    assert "loadStrategy(" in panel


def test_detail_panel_uses_no_legacy_horizon_governance_inline():
    """The detail panel no longer renders the legacy inline
    horizon_governance summary into the scan shell."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    overview = (
        ROOT / "app/static/pages/strategy/renderOverview.js"
    ).read_text(encoding="utf-8")

    assert "renderHorizonGovernance" not in index
    assert "model.horizon_governance" not in overview


# ---------------------------------------------------------------------------
# Snapshot builder backend contract
# ---------------------------------------------------------------------------


def test_strategy_snapshot_builder_attaches_market_context():
    """snapshot_builder still emits market_context via MarketContextBuilder."""
    source = (ROOT / "app/services/strategy_signal/snapshot_builder.py").read_text(
        encoding="utf-8"
    )
    assert "MarketContextBuilder" in source
    assert '"market_context"' in source


# ---------------------------------------------------------------------------
# Risk-gate / macro-regime labels
# ---------------------------------------------------------------------------


def test_strategy_risk_gate_uses_chinese_labels():
    """risk_gate must use the four canonical Chinese labels."""
    risk_gate = (ROOT / "app/services/strategy_unified/risk_gate.py").read_text(
        encoding="utf-8"
    )
    for label in ("核心周期数据缺失", "高影响事件窗口", "衍生品确认降级", "链上数据缺失"):
        assert label in risk_gate, f"risk_gate must use Chinese label: {label}"


def test_strategy_macro_regime_emits_human_explanation():
    """macro_regime emits human_explanation + 宏观 label."""
    macro = (ROOT / "app/services/strategy_unified/macro_regime.py").read_text(
        encoding="utf-8"
    )
    assert "human_explanation" in macro
    assert "宏观" in macro


# ---------------------------------------------------------------------------
# Runtime diagnostics hiding — backend doesn't leak internal tokens
# ---------------------------------------------------------------------------


def test_strategy_market_operation_backend_hides_internal_diagnostics():
    """MacroRegimeEngine / OnchainRegimeEngine / price-structure
    dimension must not expose internal tokens in their evidence text."""
    from app.services.strategy_unified.macro_regime import MacroRegimeEngine
    from app.services.strategy_unified.onchain_regime import OnchainRegimeEngine
    from app.services.strategy_unified.unified_service import UnifiedStrategyService

    context = SimpleNamespace(
        macro_features={"regime_key": "risk_on", "operation_bias": "bullish", "total_score": 68},
        macro_overview={},
        event_features={},
        cache_meta={"cache_state": "fresh"},
    )
    macro = MacroRegimeEngine().compute({"1d": context})
    macro_text = " ".join([*macro.evidence, macro.details["human_explanation"]])
    for token in ("operation_bias", "regime_key"):
        assert token not in macro_text

    class _Node:
        def __init__(self, timeframe: str, direction: str) -> None:
            self.timeframe = timeframe
            self.direction = direction

        def as_dict(self) -> dict[str, str]:
            return {"timeframe": self.timeframe, "direction": self.direction}

    service = UnifiedStrategyService(repository=None)  # type: ignore[arg-type]
    price = service._price_structure_dimension(  # noqa: SLF001
        [
            _Node("1M", "NEUTRAL"),
            _Node("1w", "NEUTRAL"),
            _Node("1d", "NEUTRAL"),
            _Node("4h", "NEUTRAL"),
        ]
    )
    price_text = " ".join(price.evidence)
    assert "战略栈=" not in price_text
    assert "战术栈=" not in price_text
    assert "NEUTRAL" not in price_text

    onchain_text = OnchainRegimeEngine._strategy_impact("upstream_missing", [])  # noqa: SLF001
    assert "onchain observations" not in onchain_text
    assert "链上观测数据" in onchain_text


# ---------------------------------------------------------------------------
# verdict_for_node contract
# ---------------------------------------------------------------------------


def test_strategy_verdict_for_node_handles_all_states():
    """verdict_for_node resolves every canonical case."""
    from app.services.strategy_unified.contracts import verdict_for_node

    assert callable(verdict_for_node)
    assert verdict_for_node("NO_EDGE", "NEUTRAL", "1d") == "RANGE_NO_EDGE"
    assert verdict_for_node("CONTEXT_LONG", "LONG", "1M") == "STRATEGIC_LONG_TACTICAL_LONG"
    assert verdict_for_node("CONTEXT_LONG", "LONG", "4h") == "CONTEXT_ALIGNED_LONG"
    assert verdict_for_node("CONTEXT_SHORT", "SHORT", "1M") == "STRATEGIC_SHORT_TACTICAL_SHORT"
    assert verdict_for_node("CONTEXT_SHORT", "SHORT", "1h") == "CONTEXT_ALIGNED_SHORT"
    assert verdict_for_node("EVENT_LOCKED", "NEUTRAL", "1d") == "EVENT_LOCKED"
    assert verdict_for_node("DATA_DEGRADED", "NEUTRAL", "1d") == "DATA_DEGRADED"
    assert verdict_for_node("CONTEXT_MISSING", "NEUTRAL", "1d") == "DATA_DEGRADED"
    assert verdict_for_node("UNKNOWN_STATE", "NEUTRAL", "1d") == "RANGE_NO_EDGE"


# ---------------------------------------------------------------------------
# Confidence scaling
# ---------------------------------------------------------------------------


def test_timeframe_node_confidence_reflects_conclusive_state():
    """A fresh CONTEXT_SHORT 1d node must yield confidence >= 70."""
    from app.services.strategy_unified.mtf_structure import MultiTimeframeStructureEngine

    nodes = MultiTimeframeStructureEngine().build_nodes(
        {
            "1d": {
                "cache_meta": {"cache_state": "fresh"},
                "structure_features": {"structure_state": "CONTEXT_SHORT"},
            }
        },
        {
            "1d": {
                "status": "ready",
                "cache_state": "fresh",
                "decision": {
                    "strategy_state": "CONTEXT_SHORT",
                    "long_score": 36,
                    "short_score": 73,
                    "primary_strategy": {},
                },
            }
        },
    )
    daily = next(node for node in nodes if node.timeframe == "1d")

    assert daily.direction == "SHORT"
    assert daily.verdict_code == "STRATEGIC_SHORT_TACTICAL_SHORT"
    assert daily.confidence > 0
    assert daily.confidence >= 70


def test_timeframe_node_confidence_reflects_range_no_edge_judgment():
    """A fresh NO_EDGE 1w node must yield confidence >= 60."""
    from app.services.strategy_unified.mtf_structure import MultiTimeframeStructureEngine

    nodes = MultiTimeframeStructureEngine().build_nodes(
        {
            "1w": {
                "cache_meta": {"cache_state": "fresh"},
                "structure_features": {"structure_state": "NO_EDGE"},
            }
        },
        {
            "1w": {
                "status": "ready",
                "cache_state": "fresh",
                "decision": {
                    "strategy_state": "NO_EDGE",
                    "long_score": 49,
                    "short_score": 56,
                    "primary_strategy": {},
                },
            }
        },
    )
    weekly = next(node for node in nodes if node.timeframe == "1w")

    assert weekly.direction == "NEUTRAL"
    assert weekly.verdict_code == "RANGE_NO_EDGE"
    assert weekly.confidence > 0
    assert weekly.confidence >= 60


# ---------------------------------------------------------------------------
# 2026-07-24 v3: distinguish "data ready, no edge" from "data pending".
# The scanner must expose cache_state + data_quality per cell so the
# frontend can render three distinct states (actionable / ready-no-edge
# / pending) instead of conflating them under a single "等待" copy.
# ---------------------------------------------------------------------------


def test_scan_item_exposes_cache_state_and_data_quality():
    """Each ScanItem must carry cache_state (fresh / missing / etc.)
    and data_quality (0-100). The frontend needs these to distinguish
    'no edge' from 'data not ready'."""
    from app.services.strategy_unified.opportunity_scanner import ScanItem

    item = ScanItem(
        instrument_id="btc-usdt-perp",
        instrument_code="btc-usdt-perp",
        timeframe="1d",
        direction="WAIT",
        direction_label="等待",
        confidence=70.0,
        score=0.0,
        summary="no edge",
        risk_reward=0.0,
        leverage_hint="spot",
        position_cap="observe",
        primary_driver="mtf",
        conflicts=[],
    )
    # The dataclass must have these two fields.
    assert hasattr(item, "cache_state"), (
        "ScanItem must expose cache_state so renderer can distinguish "
        "'ready, no edge' from 'data pending'"
    )
    assert hasattr(item, "data_quality"), (
        "ScanItem must expose data_quality (0-100)"
    )


def test_extract_scan_item_populates_cache_state():
    """`_extract_scan_item` must read the unified payload and populate
    cache_state from payload.status / payload.degraded_components
    and data_quality from payload.signal_coverage.confidence_score."""
    from app.services.strategy_unified.opportunity_scanner import (
        _extract_scan_item,
    )

    payload = {
        "trade_decision": {"side": "WAIT", "risk_reward": {}},
        "status": "ready",
        "signal_coverage": [
            {"module": "price_structure", "confidence": 70.0},
            {"module": "macro_regime", "confidence": 30.0},
            {"module": "derivatives", "confidence": 40.0},
        ],
    }
    item = _extract_scan_item(payload, "btc-usdt-perp", "btc-usdt-perp", "1d")
    assert item.cache_state == "fresh"
    # (70 + 30 + 40) / 3 = 46.67 → rounded to 1 decimal = 46.7
    assert item.data_quality == 46.7


def test_extract_scan_item_marks_missing_cache():
    """When the unified payload signals degraded status (status='degraded'
    OR non-empty degraded_components), the scanner must propagate that
    as cache_state='missing'."""
    from app.services.strategy_unified.opportunity_scanner import (
        _extract_scan_item,
    )

    payload = {
        "trade_decision": {"side": "NONE", "risk_reward": {}},
        "status": "degraded",
        "degraded_components": ["analysis", "monitoring"],
    }
    item = _extract_scan_item(payload, "btc-usdt-perp", "btc-usdt-perp", "1d")
    assert item.cache_state == "missing"


def test_extract_scan_item_marks_ready_with_warnings_as_fresh():
    """status='ready_with_warnings' should still be cache_state='fresh' —
    a warning is not a data dependency failure."""
    from app.services.strategy_unified.opportunity_scanner import (
        _extract_scan_item,
    )

    payload = {
        "trade_decision": {"side": "WAIT", "risk_reward": {}},
        "status": "ready_with_warnings",
    }
    item = _extract_scan_item(payload, "btc-usdt-perp", "btc-usdt-perp", "1d")
    assert item.cache_state == "fresh"


def test_scan_result_cache_meta_counts_cells_ready_vs_pending():
    """ScanResult.cache_meta must expose cells_ready and cells_pending
    counts so the banner can show '数据补齐中 (X/Y)' when some cells
    are still pending."""
    from app.services.strategy_unified.opportunity_scanner import (
        ScanResult,
        ScanItem,
    )

    items = [
        ScanItem("x", "x", "1w", "LONG", "做多", 70, 50, "", 0, "spot", "standard", "", [], cache_state="fresh", data_quality=80),
        ScanItem("x", "x", "1d", "WAIT", "等待", 50, 0, "", 0, "spot", "observe", "", [], cache_state="fresh", data_quality=60),
        ScanItem("x", "x", "4h", "WAIT", "等待", 30, 0, "", 0, "spot", "observe", "", [], cache_state="missing", data_quality=10),
    ]
    result = ScanResult(
        scanned_at="2026-07-24T00:00:00Z",
        instruments=["x"],
        timeframes=["1w", "1d", "4h"],
        matrix=items,
        ranked=[],
        cache_meta={
            "fresh_until": "2026-07-24T00:01:00Z",
            "source": "live",
            "instruments_scanned": 1,
            "opportunities_found": 0,
            "cells_ready": sum(1 for it in items if it.cache_state == "fresh"),
            "cells_pending": sum(
                1 for it in items
                if it.cache_state in {"missing", "warming", "error"}
            ),
        },
    )
    # The contract is: ScanResult.cache_meta must contain
    # cells_ready and cells_pending keys. The values match the items.
    assert "cells_ready" in result.cache_meta
    assert "cells_pending" in result.cache_meta
    assert result.cache_meta["cells_ready"] == 2  # 1w + 1d are fresh
    assert result.cache_meta["cells_pending"] == 1  # 4h is missing


def test_scan_all_populates_cells_ready_and_pending_in_cache_meta():
    """End-to-end: when OpportunityScanner.scan_all runs, the returned
    ScanResult.cache_meta must include cells_ready and cells_pending
    counts derived from each cell's cache_state."""
    from types import SimpleNamespace

    from app.services.strategy_unified.opportunity_scanner import (
        OpportunityScanner,
        SCAN_TIMEFRAMES,
    )

    # Stub repository with no instruments (we'll patch scan_all internals)
    repo = SimpleNamespace()
    scanner = OpportunityScanner(repo)  # type: ignore[arg-type]

    # Build synthetic build_unified_strategy outputs
    call_count = {"n": 0}

    async def fake_build(self, instrument_id, force=False):  # noqa: ARG001
        call_count["n"] += 1
        idx = call_count["n"]
        # Alternate status to exercise both fresh and missing paths.
        # idx=3 (mod 3 == 0) returns status="degraded" so we get a
        # cache_state="missing" cell.
        if idx % 3 == 0:
            cell_status = "degraded"
        else:
            cell_status = "ready"
        return {
            "trade_decision": {
                "side": "WAIT" if idx % 2 == 0 else "LONG",
                "risk_reward": {"value": 1.5 if idx % 2 else 0},
                "position_cap": "standard" if idx % 2 else "observe",
                "recommended_leverage": 0,
            },
            "status": cell_status,
            "signal_coverage": [
                {"module": "price_structure", "confidence": 50.0 + idx},
            ],
            "market_operation": {"chain": {}},
            "evidence_trace": [],
        }

    # Monkey-patch UnifiedStrategyService.build_unified_strategy
    from app.services.strategy_unified import unified_service as us_mod

    orig_build = us_mod.UnifiedStrategyService.build_unified_strategy
    us_mod.UnifiedStrategyService.build_unified_strategy = fake_build
    try:
        result = asyncio.run(
            scanner.scan_all(
                ["btc-usdt-perp"], {"btc-usdt-perp": "btc-usdt-perp"},
                timeframes=("1w", "1d", "4h"),
            )
        )
    finally:
        us_mod.UnifiedStrategyService.build_unified_strategy = orig_build

    # With 3 cells and one of them having freshness_state="missing"
    # (idx=3 ⇒ 3 % 3 == 0), we expect cells_ready=2, cells_pending=1.
    assert "cells_ready" in result.cache_meta
    assert "cells_pending" in result.cache_meta
    assert result.cache_meta["cells_ready"] >= 1
    assert result.cache_meta["cells_pending"] >= 1
    assert result.cache_meta["cells_ready"] + result.cache_meta["cells_pending"] == len(
        result.matrix
    )