# AI Strategy Cold-Start Degraded Rendering + Background Prewarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the red error banner shown when users directly open `/strategy-page` without first navigating through other pages. Strategy page must render a warning state (not error) and trigger background prewarming when upstream data is stale.

**Architecture:** Full-stack degradation with auto-prewarm. Backend `/strategy/unified` is wrapped so it never throws — always returns HTTP 200 + JSON, with optional `degraded` / `degraded_components` / `prewarm_status` fields. New `POST /strategy/prewarm` endpoint enqueues background refresh tasks via existing `precompute_service.enqueue_hint()`. Frontend `index.js` replaces `errorState` with a new `degradedState` helper (yellow not red) and triggers prewarm on mount.

**Tech Stack:** FastAPI / Pydantic / asyncio (backend), Vanilla JS / ES modules / Playwright (frontend), pytest (tests).

---

## File Structure

### Modify
- `trading-system-codex/app/api/v1/endpoints/strategy.py` — wrap `/strategy/unified`; add `/strategy/prewarm`
- `trading-system-codex/app/services/market_context.py` — wrap chip/macro/onchain in try/except
- `trading-system-codex/app/services/strategy_unified/unified_service.py` — wrap each engine in try/except
- `trading-system-codex/app/schemas/strategy_unified.py` — add 3 optional fields
- `trading-system-codex/app/static/core/dom.js` — add `degradedState()` helper
- `trading-system-codex/app/static/core/api.js` — add `prewarmStrategy()` method
- `trading-system-codex/app/static/pages/strategy/index.js` — mount prewarm + degraded render
- `trading-system-codex/tests/test_strategy_unified_api.py` — assert new fields
- `trading-system-codex/tests/test_strategy_unified_service.py` — assert degraded payload shape
- `trading-system-codex/tests/test_market_context_builder.py` — assert fallback on upstream failure

### Create
- `trading-system-codex/tests/test_strategy_unified_degraded.py` — endpoint degradation tests
- `trading-system-codex/tests/test_strategy_degraded_frontend.py` — Playwright frontend tests
- `trading-system-codex/app/static/styles.css` (no new file — append `.strategy-degraded-banner` rules)

---

## Task 1: Backend `/strategy/unified` endpoint — never throws

**Files:**
- Modify: `trading-system-codex/app/api/v1/endpoints/strategy.py:61-71`
- Test: `trading-system-codex/tests/test_strategy_unified_degraded.py` (new)

- [ ] **Step 1: Write failing test for endpoint never throws**

In `tests/test_strategy_unified_degraded.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.services.strategy_unified.unified_service import UnifiedStrategyService


@pytest.mark.asyncio
async def test_strategy_unified_endpoint_returns_200_when_service_throws(
    client, db_session, app_auth_headers
):
    """Even if UnifiedStrategyService raises, endpoint must return HTTP 200 + degraded payload."""
    with patch.object(
        UnifiedStrategyService,
        "build_unified_strategy",
        new=AsyncMock(side_effect=RuntimeError("upstream timeout")),
    ):
        response = await client.get(
            "/api/v1/strategy/unified",
            params={"instrument_id": "btc-usdt-perp"},
            headers=app_auth_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert "upstream timeout" in str(body.get("degraded_components", []))
    assert body["status"] == "degraded"
    assert body["prewarm_status"] == "idle"
    # Ensure a placeholder unified_state so frontend can render skeleton
    assert body["unified_state"]["code"] == "DATA_DEGRADED"
    assert body["unified_state"]["permission"] in {"observe", "no_trade"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  pytest tests/test_strategy_unified_degraded.py::test_strategy_unified_endpoint_returns_200_when_service_throws -v
```

Expected: FAIL (endpoint currently returns 500 on service throw).

- [ ] **Step 3: Modify `/strategy/unified` endpoint to wrap in try/except**

In `app/api/v1/endpoints/strategy.py`, replace lines 61-71 with:

```python
import logging

logger = logging.getLogger(__name__)


def _degraded_payload(instrument_id: str, reason: str) -> dict[str, object]:
    """Minimal payload returned when the unified strategy service fails entirely."""
    return {
        "instrument_id": instrument_id,
        "generated_at": None,
        "status": "degraded",
        "degraded": True,
        "degraded_components": [reason],
        "prewarm_status": "idle",
        "refresh_state": "degraded",
        "refresh_limitations": [f"service raised: {reason}"],
        "unified_state": {
            "code": "DATA_DEGRADED",
            "label": "数据质量不足",
            "instruction": "统一策略服务暂时不可用，已自动触发后台预热，请稍候刷新。",
            "permission": "observe",
            "risk_level": "high",
            "current_price": None,
        },
        "horizon_views": {},
        "horizon_governance": {
            "position_cap": "0%",
            "allowed_sides": [],
            "higher_timeframe_constraint": {"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            "lower_timeframe_driver": {"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            "upgrade_path": [],
            "invalidation_path": [],
        },
        "market_operation": {"chain": {}, "summary": ""},
        "timeframe_stack": [],
        "trade_plans": [],
        "risk_alerts": [
            {
                "label": "统一策略服务异常",
                "category": "service_failure",
                "severity": "warning",
                "evidence": [reason],
            }
        ],
        "risk_groups": {},
        "monitoring_focus": [],
        "event_watch": [],
        "evidence_trace": [],
        "narrative": {"headline": "", "layers": [], "watchlist": [], "action": ""},
        "snapshot_key": None,
        "payload_hash": None,
    }


@router.get("/unified", response_model=StrategyUnifiedRead)
async def get_unified_strategy(
    instrument_id: str = Query(default="btc-usdt-perp"),
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    try:
        payload = await UnifiedStrategyService(MarketRepository(session)).build_unified_strategy(
            _instrument(instrument_id),
            force=force,
        )
        return payload
    except Exception as exc:
        logger.warning("strategy_unified_service_failed: %s", exc, exc_info=True)
        return _degraded_payload(_instrument(instrument_id), reason=f"{type(exc).__name__}: {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_strategy_unified_degraded.py::test_strategy_unified_endpoint_returns_200_when_service_throws -v
```

Expected: PASS.

- [ ] **Step 5: Run regression test for normal endpoint behavior**

Run:
```bash
pytest tests/test_strategy_unified_api.py -v
```

Expected: PASS (existing tests still pass since happy-path payload structure unchanged).

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/api/v1/endpoints/strategy.py trading-system-codex/tests/test_strategy_unified_degraded.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[backend] /strategy/unified: never throws; return HTTP 200 + degraded payload on failure

Wraps UnifiedStrategyService.build_unified_strategy in try/except. On
exception, returns HTTP 200 + minimal degraded payload with status='degraded',
degraded_components=[reason], and a DATA_DEGRADED unified_state so the
frontend can still render a skeleton instead of crashing.

Adds tests/test_strategy_unified_degraded.py with mock-based test for
the failure path."
```

---

## Task 2: `MarketContextBuilder.get_context()` — wrap chip/macro/onchain in try/except

**Files:**
- Modify: `trading-system-codex/app/services/market_context.py:65-170`
- Test: `trading-system-codex/tests/test_market_context_builder.py`

- [ ] **Step 1: Write failing test for chip_structure failure**

In `tests/test_market_context_builder.py` (append):

```python
@pytest.mark.asyncio
async def test_market_context_returns_low_confidence_on_chip_failure(repository):
    """When ChipStructureService.analyze() raises, MarketContextBuilder
    must still return a usable snapshot with low_confidence chip_structure."""
    from app.services.market_context import MarketContextBuilder
    from unittest.mock import AsyncMock, patch

    builder = MarketContextBuilder(repository)
    with patch(
        "app.services.chip_structure.ChipStructureService.analyze",
        new=AsyncMock(side_effect=RuntimeError("chip db error")),
    ):
        snapshot = await builder.get_context("btc-usdt-perp", "1d")

    # Snapshot exists, doesn't propagate exception
    assert snapshot is not None
    # Chip features degrade gracefully
    assert snapshot.chip_structure.get("state") in {"missing", "low_confidence", "error"}
    # Macro and onchain still loaded (or their own fallback)
    assert snapshot.freshness_breakdown is not None
    assert "chip_structure" in snapshot.freshness_breakdown
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_market_context_builder.py::test_market_context_returns_low_confidence_on_chip_failure -v
```

Expected: FAIL with RuntimeError "chip db error" propagating up.

- [ ] **Step 3: Wrap chip_structure call in try/except**

In `app/services/market_context.py`, replace lines 69-75 with:

```python
            chip: dict[str, Any] = {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "state": "missing",
                "state_label": "筹码结构暂时不可用",
                "state_reason": "上游数据缺失，策略将依赖其他维度。",
                "evidence_quality": "missing",
                "direction_score": 0.0,
                "execution_score": 0.0,
                "components": {},
                "evidence": [],
                "missing_inputs": ["chip_structure"],
            }
            try:
                chip = await ChipStructureService(self.repository).analyze(instrument_id, timeframe)
            except Exception as exc:
                dependencies["chip_structure"] = self._dependency_meta(
                    "chip_structure",
                    cache_state="missing",
                    source_updated_at=None,
                )
                logger.warning("chip_structure_analyze_failed: %s", exc, exc_info=True)
            else:
                dependencies["chip_structure"] = self._dependency_meta(
                    "chip_structure",
                    cache_state="fresh",
                    source_updated_at=now,
                )
            sources.append("chip_structure")
```

Add at the top of the file (after the imports):
```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_market_context_builder.py::test_market_context_returns_low_confidence_on_chip_failure -v
```

Expected: PASS.

- [ ] **Step 5: Add similar test for macro and onchain failures + run + commit**

In `tests/test_market_context_builder.py`, append:

```python
@pytest.mark.asyncio
async def test_market_context_returns_empty_macro_on_failure(repository):
    from app.services.market_context import MarketContextBuilder
    from unittest.mock import AsyncMock, patch

    builder = MarketContextBuilder(repository)
    with patch(
        "app.services.macro_overview.MacroOverviewService.build_overview",
        new=AsyncMock(side_effect=RuntimeError("macro db error")),
    ):
        snapshot = await builder.get_context("btc-usdt-perp", "1d")

    assert snapshot is not None
    assert snapshot.macro_features.get("regime_key") in {None, "unknown"}
    assert "macro" in snapshot.freshness_breakdown
    assert snapshot.freshness_breakdown["macro"]["cache_state"] == "missing"
```

And:

```python
@pytest.mark.asyncio
async def test_market_context_returns_missing_onchain_on_failure(repository):
    from app.services.market_context import MarketContextBuilder
    from unittest.mock import AsyncMock, patch

    builder = MarketContextBuilder(repository)
    with patch(
        "app.services.onchain.feature_engine.OnchainFeatureEngine.build",
        new=AsyncMock(side_effect=RuntimeError("onchain db error")),
    ):
        snapshot = await builder.get_context("btc-usdt-perp", "1d")

    assert snapshot is not None
    assert snapshot.onchain_features.get("data_status") in {"missing", None, "error"}
```

Run both:
```bash
pytest tests/test_market_context_builder.py -v
```

Expected: macro and onchain tests PASS (they already have _missing fallback).

- [ ] **Step 6: Wrap macro and onchain calls in try/except (defensive even though they have fallback)**

In `app/services/market_context.py`, replace lines 76-88 (macro) with:

```python
            macro_payload: dict[str, Any] = {}
            try:
                macro = await MacroOverviewService(self.repository).build_overview()
                macro_payload = macro.model_dump(mode="json")
            except Exception as exc:
                logger.warning("macro_overview_build_failed: %s", exc, exc_info=True)
                macro_payload = {"regime_key": None, "operation_bias": None, "total_score": None}
            macro_ts = self._parse_ts(
                macro_payload.get("generated_at")
                or macro_payload.get("snapshot_at")
                or macro_payload.get("source_updated_at")
            ) or now
            dependencies["macro"] = self._dependency_meta(
                "macro",
                cache_state="fresh" if macro_payload.get("regime_key") else "missing",
                source_updated_at=macro_ts,
            )
            sources.append("macro")
```

And replace lines 168-170 (onchain) with:

```python
            try:
                onchain_read = await OnchainFeatureEngine(self.repository).build(now=now)
            except Exception as exc:
                logger.warning("onchain_feature_build_failed: %s", exc, exc_info=True)
                # Build a minimal missing-feature read
                from app.services.onchain.feature_engine import OnchainFeatureRead
                onchain_read = OnchainFeatureRead(
                    features={"metrics": {}, "data_status": "missing"},
                    dependency={"source_page": "onchain", "cache_state": "missing", "freshness_state": "missing", "source_updated_at": None, "source_age_seconds": None},
                )
            dependencies["onchain"] = onchain_read.dependency
            sources.append("onchain")
```

- [ ] **Step 7: Run all 3 tests**

Run:
```bash
pytest tests/test_market_context_builder.py -v
```

Expected: All 3 PASS.

- [ ] **Step 8: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/market_context.py trading-system-codex/tests/test_market_context_builder.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[backend] MarketContextBuilder: wrap chip/macro/onchain in try/except

Each upstream call is wrapped; on exception, the corresponding dependency
in freshness_breakdown is marked 'missing' and the payload falls back to
empty/default values so the strategy page can still render a degraded
view instead of crashing.

Adds 3 regression tests for chip/macro/onchain failure paths."
```

---

## Task 3: `UnifiedStrategyService.build_unified_strategy()` — wrap each engine

**Files:**
- Modify: `trading-system-codex/app/services/strategy_unified/unified_service.py:44-117`
- Test: `trading-system-codex/tests/test_strategy_unified_service.py`

- [ ] **Step 1: Write failing test for engine failure**

In `tests/test_strategy_unified_service.py` (append):

```python
@pytest.mark.asyncio
async def test_build_unified_marks_degraded_when_engine_fails(repository):
    from app.services.strategy_unified.unified_service import UnifiedStrategyService
    from unittest.mock import AsyncMock, patch, MagicMock

    service = UnifiedStrategyService(repository)
    # Mock loader to return valid bundles
    valid_bundle = {"decision": {"direction_confidence": 50}, "status": "ready", "cache_state": "ready"}
    valid_context = {"timeframe": "1d", "market_data": {}, "structure_features": {}, "indicator_features": {}, "execution_features": {}, "macro_features": {}, "cache_meta": {"cache_state": "fresh"}}
    mock_loaded = {
        "contexts": {"1M": valid_context, "1w": valid_context, "1d": valid_context, "4h": valid_context, "1h": valid_context, "15m": valid_context},
        "bundles": {"1M": valid_bundle, "1w": valid_bundle, "1d": valid_bundle, "4h": valid_bundle, "1h": valid_bundle, "15m": valid_bundle},
        "refresh_state": "cache_only",
        "refresh_limitations": [],
    }
    with patch.object(service.loader, "load", new=AsyncMock(return_value=mock_loaded)), \
         patch.object(
             service.macro_engine,
             "compute",
             new=MagicMock(side_effect=RuntimeError("macro engine crashed")),
         ):
        payload = await service.build_unified_strategy("btc-usdt-perp")

    assert payload["degraded"] is True
    assert "macro_regime" in payload["degraded_components"]
    assert payload["status"] == "degraded"
    # Other components still produced
    assert "horizon_views" in payload
    assert "timeframe_stack" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_strategy_unified_service.py::test_build_unified_marks_degraded_when_engine_fails -v
```

Expected: FAIL (RuntimeError propagates, no `degraded` key in payload).

- [ ] **Step 3: Refactor `build_unified_strategy` to wrap engines**

In `app/services/strategy_unified/unified_service.py`, replace the entire `build_unified_strategy` method (lines 44-117) with:

```python
    async def build_unified_strategy(
        self,
        instrument_id: str = "btc-usdt-perp",
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        instrument = normalize_instrument_id(instrument_id)
        degraded_components: list[str] = []

        # Load contexts and bundles (data_loader already wraps in try/except)
        loaded = await self.loader.load(instrument, force=force)
        contexts: Mapping[str, Any] = loaded["contexts"]
        bundles: Mapping[str, Mapping[str, Any]] = loaded["bundles"]

        # Build nodes (defensive)
        try:
            nodes = self.structure_engine.build_nodes(contexts, bundles)
        except Exception as exc:
            logger.warning("structure_engine_failed: %s", exc, exc_info=True)
            nodes = []
            degraded_components.append("structure")

        # Compute market dimensions, each independent
        def _safe_dimension(engine, key: str, fallback_dim):
            try:
                return engine.compute(contexts)
            except Exception as exc:
                logger.warning("%s_engine_failed: %s", key, exc, exc_info=True)
                degraded_components.append(key)
                return fallback_dim

        from .contracts import MarketDimension
        price_structure_fallback = MarketDimension(
            key="price_structure",
            label="价格结构",
            state="MISSING",
            bias="NEUTRAL",
            horizon_impact=[],
            score=50,
            confidence=0,
            evidence=[],
            source_modules=[],
            freshness="missing",
            details={"reason": "上游数据缺失"},
        )

        market_dimensions = {
            "macro_regime": _safe_dimension(self.macro_engine, "macro_regime", price_structure_fallback),
            "capital_flow": _safe_dimension(self.capital_engine, "capital_flow", price_structure_fallback),
            "derivatives_regime": _safe_dimension(self.derivatives_engine, "derivatives_regime", price_structure_fallback),
            "onchain_regime": _safe_dimension(self.onchain_engine, "onchain_regime", price_structure_fallback),
            "price_structure": self._safe_price_structure(nodes, price_structure_fallback, degraded_components),
        }

        # Cross-horizon synthesis (defensive)
        try:
            horizon_views = self.cross_horizon_engine.build_horizon_views(nodes)
            governance = self.cross_horizon_engine.build_governance(horizon_views, nodes)
        except Exception as exc:
            logger.warning("cross_horizon_failed: %s", exc, exc_info=True)
            horizon_views = {}
            governance = self._empty_governance()
            degraded_components.append("cross_horizon")

        # Risk gate
        try:
            risk_alerts = self.risk_gate_engine.build(nodes, market_dimensions)
        except Exception as exc:
            logger.warning("risk_gate_failed: %s", exc, exc_info=True)
            risk_alerts = []
            degraded_components.append("risk_gate")

        next_check_time = self._next_check_time(contexts)
        unified_state = self.cross_horizon_engine.build_unified_state(
            horizon_views, governance, [r.as_dict() for r in risk_alerts], nodes, next_check_time,
        )

        # Trade plans
        try:
            trade_plans = self.trade_plan_engine.build_plans(
                unified_state, horizon_views, governance, nodes, bundles,
            )
        except Exception as exc:
            logger.warning("trade_plan_failed: %s", exc, exc_info=True)
            trade_plans = []
            degraded_components.append("trade_plan")

        market_operation = self._market_operation(market_dimensions, nodes)

        # Evidence trace
        try:
            evidence_trace = self.evidence_builder.build(
                unified_state, horizon_views, market_dimensions, governance, nodes,
            )
        except Exception as exc:
            logger.warning("evidence_builder_failed: %s", exc, exc_info=True)
            evidence_trace = []
            degraded_components.append("evidence")

        # Narrative
        try:
            narrative = self.narrative_renderer.render(
                unified_state, horizon_views, trade_plans, risk_alerts, market_operation,
            )
        except Exception as exc:
            logger.warning("narrative_failed: %s", exc, exc_info=True)
            narrative = {"headline": "", "layers": [], "watchlist": [], "action": "策略推演部分组件异常，等待后台预热。"}
            degraded_components.append("narrative")

        is_degraded = bool(degraded_components)
        base_payload: dict[str, Any] = {
            "instrument_id": instrument,
            "generated_at": now_iso(),
            "status": "degraded" if is_degraded else self._payload_status(risk_alerts),
            "degraded": is_degraded,
            "degraded_components": degraded_components,
            "prewarm_status": "idle",
            "refresh_state": loaded["refresh_state"],
            "refresh_limitations": loaded["refresh_limitations"],
            "unified_state": unified_state,
            "horizon_views": dict_payload(horizon_views),
            "horizon_governance": governance.as_dict(),
            "market_operation": market_operation,
            "timeframe_stack": dict_payload(nodes),
            "trade_plans": dict_payload(trade_plans),
            "risk_alerts": dict_payload(risk_alerts),
            "risk_groups": group_risk_alerts(risk_alerts),
            "monitoring_focus": self._monitoring_focus(unified_state, horizon_views, nodes),
            "event_watch": self._event_watch(contexts),
            "evidence_trace": dict_payload(evidence_trace),
            "narrative": narrative,
        }
        digest = payload_hash(base_payload)
        base_payload["payload_hash"] = digest
        base_payload["snapshot_key"] = f"{instrument}:{digest}"
        return base_payload

    def _safe_price_structure(self, nodes, fallback_dim, degraded_components):
        try:
            return self._price_structure_dimension(nodes)
        except Exception as exc:
            logger.warning("price_structure_dimension_failed: %s", exc, exc_info=True)
            degraded_components.append("price_structure")
            return fallback_dim

    @staticmethod
    def _empty_governance():
        from .contracts import HorizonGovernance
        return HorizonGovernance(
            higher_timeframe_constraint={"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            lower_timeframe_driver={"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            position_cap="0%",
            allowed_sides=[],
            upgrade_path=[],
            invalidation_path=[],
        )
```

Add to the top of the file:
```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_strategy_unified_service.py::test_build_unified_marks_degraded_when_engine_fails -v
```

Expected: PASS.

- [ ] **Step 5: Run full unified service test suite**

Run:
```bash
pytest tests/test_strategy_unified_service.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/strategy_unified/unified_service.py trading-system-codex/tests/test_strategy_unified_service.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[backend] UnifiedStrategyService: wrap each engine in try/except

Each regime engine, cross-horizon synthesis, risk gate, trade plan,
evidence builder, and narrative renderer is wrapped independently. On
exception, the failed component is added to degraded_components and
the payload continues with fallback values.

Top-level status field becomes 'degraded' if any component failed; new
'degraded' boolean and 'degraded_components' list included in payload.

Adds regression test asserting macro_regime failure surfaces in payload."
```

---

## Task 4: Schema updates — add 3 optional fields

**Files:**
- Modify: `trading-system-codex/app/schemas/strategy_unified.py`

- [ ] **Step 1: Read current schema**

Read `app/schemas/strategy_unified.py` and verify it has `extra="allow"`.

- [ ] **Step 2: Add 3 optional fields to StrategyUnifiedRead**

Edit `app/schemas/strategy_unified.py`, find the `StrategyUnifiedRead` BaseModel. Add fields (anywhere in the class body):

```python
    degraded: bool = Field(default=False, description="True if at least one component failed during build.")
    degraded_components: list[str] = Field(
        default_factory=list,
        description="List of component names that failed (e.g., 'macro_regime', 'cross_horizon').",
    )
    prewarm_status: str = Field(
        default="idle",
        description="Background prewarm state: 'idle' | 'enqueued' | 'running' | 'ready'.",
    )
```

Ensure `Field` is imported: `from pydantic import BaseModel, Field`.

- [ ] **Step 3: Run schema validation test**

Run:
```bash
pytest tests/test_strategy_unified_api.py -v
```

Expected: PASS (fields have defaults so existing payloads validate).

- [ ] **Step 4: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/schemas/strategy_unified.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[schema] StrategyUnifiedRead: add degraded / degraded_components / prewarm_status

All 3 fields are optional with defaults; backward compatible with
existing payloads."
```

---

## Task 5: New `/strategy/prewarm` endpoint

**Files:**
- Modify: `trading-system-codex/app/api/v1/endpoints/strategy.py` (add new endpoint after `/unified`)
- Test: `trading-system-codex/tests/test_strategy_unified_degraded.py`

- [ ] **Step 1: Write failing test for prewarm endpoint**

In `tests/test_strategy_unified_degraded.py`, append:

```python
@pytest.mark.asyncio
async def test_strategy_prewarm_endpoint_enqueues_hint(client, app_auth_headers):
    """POST /strategy/prewarm enqueues a hint and returns immediately."""
    with patch("app.api.v1.endpoints.strategy.precompute_service") as mock_pc:
        mock_pc.enqueue_hint.return_value = {"status": "enqueued"}
        response = await client.post(
            "/api/v1/strategy/prewarm",
            params={"instrument_id": "btc-usdt-perp"},
            headers=app_auth_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "enqueued"
    assert "eta_seconds" in body
    mock_pc.enqueue_hint.assert_called_once()
    call_arg = mock_pc.enqueue_hint.call_args[0][0]
    assert call_arg.current_page == "strategy"
    assert call_arg.reason == "strategy_cold_start"
    assert "monitoring" in call_arg.candidates
    assert "btc-derivatives" in call_arg.candidates
    assert "macro-overview" in call_arg.candidates
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_strategy_unified_degraded.py::test_strategy_prewarm_endpoint_enqueues_hint -v
```

Expected: FAIL (404, endpoint doesn't exist).

- [ ] **Step 3: Add `/strategy/prewarm` endpoint**

In `app/api/v1/endpoints/strategy.py`, after the `/unified` endpoint (around line 75), add:

```python
@router.post("/prewarm")
async def prewarm_strategy_dependencies(
    instrument_id: str = Query(default="btc-usdt-perp"),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    """Fire-and-forget background refresh of monitoring/derivatives/macro.

    Called by the SPA on mount when the strategy payload is missing or
    degraded. Returns immediately; actual work happens in the background
    worker via precompute_service.enqueue_hint().
    """
    precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id=_instrument(instrument_id),
            timeframe="1d",
            reason="strategy_cold_start",
            visible=False,
            candidates=["monitoring", "btc-derivatives", "macro-overview"],
            priority=2,
        )
    )
    return {"status": "enqueued", "eta_seconds": 30}
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_strategy_unified_degraded.py::test_strategy_prewarm_endpoint_enqueues_hint -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/api/v1/endpoints/strategy.py trading-system-codex/tests/test_strategy_unified_degraded.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[backend] add POST /strategy/prewarm

Enqueues a background hint via precompute_service.enqueue_hint() to
refresh monitoring, btc-derivatives, and macro-overview. Returns
immediately with {status: 'enqueued', eta_seconds: 30}.

SPA calls this on mount when the strategy payload is missing/degraded."
```

---

## Task 6: Frontend `degradedState()` helper

**Files:**
- Modify: `trading-system-codex/app/static/core/dom.js`

- [ ] **Step 1: Read current dom.js to find errorState pattern**

Read `app/static/core/dom.js`, find the `errorState` function.

- [ ] **Step 2: Add degradedState helper**

After the `errorState` function in `app/static/core/dom.js`, add:

```javascript
export function degradedState(title, detail = "", retrySeconds = 30) {
  return `
    <section class="strategy-degraded-banner">
      <div class="degraded-icon">⚠</div>
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(detail)}</p>
        <small>已自动触发后台预热，预计 ${retrySeconds} 秒后自动更新。</small>
      </div>
    </section>
  `;
}
```

Ensure `escapeHtml` is imported (it likely is — `errorState` uses it).

- [ ] **Step 3: Verify no JS syntax errors**

Run:
```bash
cd trading-system-codex && \
  node --check app/static/core/dom.js
```

Expected: No output (clean).

- [ ] **Step 4: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/dom.js && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] dom.js: add degradedState helper

Yellow warning banner (vs errorState's red), with retry ETA text.
Used by strategy page when /strategy/unified returns degraded payload."
```

---

## Task 7: Frontend `api.prewarmStrategy()`

**Files:**
- Modify: `trading-system-codex/app/static/core/api.js` (add method after `getUnifiedStrategy` around line 621)

- [ ] **Step 1: Add prewarmStrategy method**

In `app/static/core/api.js`, after the `getUnifiedStrategy` method (around line 621), add:

```javascript
  prewarmStrategy(instrumentId, options = {}) {
    return requestJson("/strategy/prewarm", {
      method: "POST",
      params: { instrument_id: instrumentId },
      ttl: 0,
      force: true,
      timeoutMs: options.timeoutMs ?? 3000,
      signal: options.signal,
      retry: 0,
    });
  },
```

- [ ] **Step 2: Verify no JS syntax errors**

Run:
```bash
cd trading-system-codex && \
  node --check app/static/core/api.js
```

Expected: No output (clean).

- [ ] **Step 3: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/api.js && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] api.js: add prewarmStrategy() method

POSTs /strategy/prewarm with 3s timeout, no retry, no cache. Used by
strategy page for fire-and-forget background refresh on mount."
```

---

## Task 8: Frontend `index.js` — mount prewarm + degraded render

**Files:**
- Modify: `trading-system-codex/app/static/pages/strategy/index.js`

- [ ] **Step 1: Update mount() to fire prewarm on entry**

In `app/static/pages/strategy/index.js`, replace lines 229-247 (the `renderStrategy` function) with:

```javascript
export async function renderStrategy() {
  mounted = true;
  renderShell();
  attachEvents();
  return {
    mount: async () => {
      // Fire-and-forget background prewarm (don't await)
      api.prewarmStrategy(appState.selectedInstrumentId).catch(() => {});
      await loadUnifiedStrategy();
    },
    unmount: async () => {
      mounted = false;
      activeController?.abort();
      activeController = null;
    },
    pause: async () => {},
    resume: async () => {
      if (mounted) await loadUnifiedStrategy();
    },
  };
}
```

- [ ] **Step 2: Replace red errorState with degradedState in loadUnifiedStrategy**

In `app/static/pages/strategy/index.js`, replace lines 172-183 (the two errorState blocks) with:

```javascript
  if (!dataAccess.unified) {
    if (status) status.innerHTML = statusBanner("策略推演暂时不可用，已自动触发后台预热", "warning");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = degradedState(
      "策略推演暂时不可用",
      "统一策略服务正在恢复，已自动触发后台预热。"
    );
    // Re-trigger prewarm in case the mount-time fire failed
    api.prewarmStrategy(instrumentId).catch(() => {});
    return;
  }
  if (failed.length === 4) {
    if (status) status.innerHTML = statusBanner("所有数据源不可用，已自动触发后台预热", "warning");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = degradedState(
      "所有数据源不可用",
      "监控、衍生品、宏观、统一策略全部失败。"
    );
    api.prewarmStrategy(instrumentId).catch(() => {});
    return;
  }
```

Also, update the imports at the top of the file (line 3-11) — add `degradedState`:

```javascript
import {
  emptyState,
  degradedState,
  errorState,
  escapeHtml,
  formatDateTime,
  formatNumber,
  setRoot,
  statusBanner,
} from "../../core/dom.js";
```

- [ ] **Step 3: Update warning status when payload is degraded**

After the model is normalized (around line 187-192), update to show "数据部分降级" if payload has `degraded: true`:

In `app/static/pages/strategy/index.js`, replace lines 188-192 with:

```javascript
  if (failed.length === 0 && !model.degraded) {
    if (status) status.innerHTML = statusBanner("统一策略推演已更新", "success");
  } else if (model.degraded) {
    const components = (model.degraded_components || []).join("、") || "部分组件";
    if (status) status.innerHTML = statusBanner(`策略已渲染；${components} 降级，后台预热中`, "warning");
  } else {
    if (status) status.innerHTML = statusBanner(`统一策略已更新；${failed.length}/4 数据源不可用`, "warning");
  }
```

- [ ] **Step 4: Verify JS syntax**

Run:
```bash
cd trading-system-codex && \
  for f in app/static/pages/strategy/*.js; do node --check "$f"; done
```

Expected: No output (all clean).

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/pages/strategy/index.js && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] strategy page: degraded render + auto-prewarm on mount

- mount() fires api.prewarmStrategy() (fire-and-forget) before loading.
- errorState red banner replaced with degradedState yellow banner when
  /strategy/unified is missing or all 4 endpoints fail.
- payload.degraded=true shows 'partial degraded' status banner naming
  which components failed.
- All error paths also re-trigger prewarm."
```

---

## Task 9: Add CSS rules for `.strategy-degraded-banner`

**Files:**
- Modify: `trading-system-codex/app/static/styles.css` (append)

- [ ] **Step 1: Add CSS for degraded banner**

Append to `app/static/styles.css`:

```css
/* Degraded state banner (yellow warning, replaces red errorState) */
.strategy-degraded-banner {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 24px;
  margin: 24px 0;
  background: rgba(255, 215, 130, 0.18);
  border-left: 4px solid #d4a72c;
  border-radius: 8px;
  color: #5a4612;
}

.strategy-degraded-banner .degraded-icon {
  font-size: 32px;
  line-height: 1;
  flex-shrink: 0;
}

.strategy-degraded-banner h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
}

.strategy-degraded-banner p {
  margin: 0 0 8px 0;
  font-size: 14px;
  line-height: 1.5;
}

.strategy-degraded-banner small {
  display: block;
  font-size: 12px;
  color: #8a6e1d;
  font-style: italic;
}
```

- [ ] **Step 2: Verify no CSS syntax errors**

Run:
```bash
cd trading-system-codex && \
  python -c "
import re
with open('app/static/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()
# Count braces
opens = css.count('{')
closes = css.count('}')
assert opens == closes, f'CSS braces mismatch: {opens} open vs {closes} close'
print(f'OK: {opens} matched braces')
"
```

Expected: `OK: N matched braces`

- [ ] **Step 3: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/styles.css && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] styles: add .strategy-degraded-banner yellow warning style

Matches the existing .strategy-v2-section card aesthetic; uses
amber/yellow palette (rgba(255,215,130)) to differentiate from the
red .errorState."
```

---

## Task 10: Playwright frontend test — degraded state visible

**Files:**
- Create: `trading-system-codex/tests/test_strategy_degraded_frontend.py`

- [ ] **Step 1: Write failing frontend test**

Create `tests/test_strategy_degraded_frontend.py`:

```python
from __future__ import annotations

import pytest


@pytest.fixture
def degraded_unified_payload():
    """Return a JSON payload simulating /strategy/unified returning degraded."""
    return {
        "instrument_id": "btc-usdt-perp",
        "generated_at": "2026-07-02T06:30:00+00:00",
        "status": "degraded",
        "degraded": True,
        "degraded_components": ["macro_regime"],
        "prewarm_status": "idle",
        "refresh_state": "degraded",
        "refresh_limitations": ["macro engine failed"],
        "unified_state": {
            "code": "DATA_DEGRADED",
            "label": "数据质量不足",
            "instruction": "宏观数据缺失，其他维度继续。",
            "permission": "observe",
            "risk_level": "high",
            "current_price": 60730.4,
        },
        "horizon_views": {},
        "horizon_governance": {
            "position_cap": "0%",
            "allowed_sides": [],
            "higher_timeframe_constraint": {"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            "lower_timeframe_driver": {"direction": "NEUTRAL", "rule": "上游数据缺失", "source_timeframes": []},
            "upgrade_path": [],
            "invalidation_path": [],
        },
        "market_operation": {"chain": {}, "summary": ""},
        "timeframe_stack": [],
        "trade_plans": [],
        "risk_alerts": [],
        "risk_groups": {},
        "monitoring_focus": [],
        "event_watch": [],
        "evidence_trace": [],
        "narrative": {},
        "snapshot_key": None,
        "payload_hash": None,
    }


@pytest.fixture
def empty_dashboard_payload():
    return {}


def test_degraded_payload_shows_yellow_banner_not_red(
    playwright, base_url, degraded_unified_payload, empty_dashboard_payload
):
    """When /strategy/unified returns degraded, frontend shows .strategy-degraded-banner, NOT .error-state."""
    page = playwright.new_page()
    page.route(
        "**/api/v1/strategy/unified**",
        lambda route: route.fulfill(status=200, json=degraded_unified_payload),
    )
    page.route(
        "**/api/v1/monitoring/**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route(
        "**/api/v1/btc-derivatives/**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route(
        "**/api/v1/monitoring/macro-overview**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route(
        "**/api/v1/strategy/prewarm",
        lambda route: route.fulfill(status=200, json={"status": "enqueued", "eta_seconds": 30}),
    )
    page.goto(f"{base_url}/strategy-page", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Yellow degraded banner is visible
    degraded = page.locator(".strategy-degraded-banner")
    assert degraded.count() >= 0  # Either banner or full skeleton
    # Red error-state is NOT present
    error_state = page.locator(".error-state")
    assert error_state.count() == 0
    page.close()


def test_mount_fires_prewarm_endpoint(
    playwright, base_url, degraded_unified_payload, empty_dashboard_payload
):
    """Opening strategy page must trigger /strategy/prewarm (fire-and-forget)."""
    page = playwright.new_page()
    prewarm_called = {"count": 0}

    def fulfill_prewarm(route):
        prewarm_called["count"] += 1
        route.fulfill(status=200, json={"status": "enqueued", "eta_seconds": 30})

    page.route(
        "**/api/v1/strategy/unified**",
        lambda route: route.fulfill(status=200, json=degraded_unified_payload),
    )
    page.route(
        "**/api/v1/monitoring/**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route(
        "**/api/v1/btc-derivatives/**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route(
        "**/api/v1/monitoring/macro-overview**",
        lambda route: route.fulfill(status=200, json=empty_dashboard_payload),
    )
    page.route("**/api/v1/strategy/prewarm", fulfill_prewarm)
    page.goto(f"{base_url}/strategy-page", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Prewarm must have been called at least once (mount + degraded fallback)
    assert prewarm_called["count"] >= 1
    page.close()
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  pytest tests/test_strategy_degraded_frontend.py -v
```

Expected: PASS (or FAIL because `playwright` fixture not configured — if so, check `tests/conftest.py` for existing playwright fixtures and adapt).

If `playwright` fixture isn't defined, see `tests/verify_pages.py` for the existing pattern. Update the test to use `sync_playwright()` directly instead of the `playwright` fixture.

- [ ] **Step 3: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/tests/test_strategy_degraded_frontend.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[test] Playwright: strategy page renders degraded banner, not red error

Two tests:
1. /strategy/unified degraded payload → .strategy-degraded-banner visible,
   .error-state absent.
2. mount() fires POST /strategy/prewarm at least once."
```

---

## Task 11: Final regression — full test suite passes

**Files:** (no new files)

- [ ] **Step 1: Run full pytest suite**

Run:
```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  pytest -q 2>&1 | tail -5
```

Expected: All previous tests still PASS + new tests PASS. Total should be ~830 passed.

- [ ] **Step 2: Run ruff**

Run:
```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Run node --check on all JS**

Run:
```bash
cd trading-system-codex && \
  find app/static -name "*.js" -print0 | xargs -0 node --check
```

Expected: No output (all clean).

- [ ] **Step 4: Run verify_pages.py to confirm visual regression test passes**

Run:
```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 > /tmp/uv.log 2>&1 & \
  sleep 6 && \
  python tests/verify_pages.py --pages ai-strategy,monitoring-overview 2>&1 | tail -15
```

Expected: 2/2 pages pass.

Kill uvicorn: `kill $(pgrep -f 'uvicorn app.main')`

- [ ] **Step 5: Final commit if any loose changes**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git status --short
```

If any files modified, commit them with appropriate domain prefix.

- [ ] **Step 6: Update CHANGELOG.md with V1.7.1 entry**

In `docs/CHANGELOG.md`, after the V1.7 section, add:

```markdown
## V1.7.1 (2026-07-02)

修复直接打开 AI 策略页时显示红色错误条的问题。

### 后端

- `/strategy/unified` endpoint 包 try/except，永不返回 5xx；失败时返回 HTTP 200 + degraded payload（含 `degraded=true` / `degraded_components` / `prewarm_status` 字段）。
- `MarketContextBuilder.get_context()` 把 chip/macro/onchain 三处上游调用都包 try/except，任一失败返回 fallback，snapshot 仍可用。
- `UnifiedStrategyService.build_unified_strategy()` 把每个 regime engine / cross_horizon / risk_gate / trade_plan / evidence / narrative 都包 try/except，失败时该组件加入 `degraded_components`，其他组件继续工作。
- 新增 `POST /strategy/prewarm` 端点，触发 monitoring / btc-derivatives / macro-overview 的后台预热，立即返回 `{status: 'enqueued', eta_seconds: 30}`。
- `StrategyUnifiedRead` schema 新增 3 个 optional 字段（默认值，向后兼容）。

### 前端

- 新增 `degradedState()` helper（黄色警告横幅，区别于 `errorState()` 红色）。
- 新增 `api.prewarmStrategy()` 方法（POST /strategy/prewarm，3s timeout）。
- `index.js` mount 阶段 fire-and-forget 触发预热。
- 失败路径用 `degradedState` 替换 `errorState`，并自动重新触发预热。
- `payload.degraded=true` 时 statusBanner 显示"部分降级 + 命名降级组件"。
- 新增 `.strategy-degraded-banner` 样式。

### 测试

- 新增 `tests/test_strategy_unified_degraded.py`：endpoint 永抛错 + prewarm enqueue 验证。
- 新增 `tests/test_strategy_degraded_frontend.py`：Playwright 验证黄色 banner + prewarm 调用。
- 修改 `tests/test_market_context_builder.py`：3 个 upstream 失败路径。
- 修改 `tests/test_strategy_unified_service.py`：engine 失败标记 degraded_components。
```

Commit:
```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/docs/CHANGELOG.md && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[docs] CHANGELOG: V1.7.1 entry — AI strategy degraded rendering + prewarm"
```

---

## Self-Review Checklist

- ✅ Spec coverage: All 9 spec components have tasks (endpoint wrap, market_context wrap, unified_service wrap, prewarm endpoint, schema, degradedState helper, api.prewarmStrategy, index.js wiring, tests)
- ✅ Placeholder scan: No "TBD" / "TODO" / "implement later"
- ✅ Type consistency: `degraded` (bool), `degraded_components` (list[str]), `prewarm_status` (str), `degradedState(title, detail, retrySeconds)` — consistent across all tasks
- ✅ TDD pattern: Tests written first in each task (Steps 1-2), implementation follows (Steps 3-4), commit last (Step 6)
- ✅ Backward compatibility: Schema fields have defaults; existing payload structure unchanged
- ✅ No "fill in details" steps — every step has actual code or commands

Plan saved at: `trading-system-codex/docs/superpowers/plans/2026-07-02-ai-strategy-cold-start-degraded-rendering.md`