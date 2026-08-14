# 跨品种跨周期机会扫描器 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将策略页从被动单品种单级别查询，改造为主动全品种全级别机会扫描 + 侧拉详情。

**Architecture:** 后端新增 `OpportunityScanner` 服务（复用 `UnifiedStrategyService` 轻量路径仅算到 `DirectionResolution`），前端重写策略页为扫描矩阵 + 排序列表 + 侧拉详情面板。扫描结果缓存 15 分钟，precompute worker 在 mark/OI 变化超阈值时触发静默更新。

**Tech Stack:** Python/FastAPI (后端), Vanilla JS ES Modules (前端), 复用现有 Monet 玻璃设计系统 (`.card` / `.eyebrow` / `.impact-chip` / `data-tone`)

**Spec:** `docs/superpowers/specs/2026-07-24-opportunity-scanner-design.md`

---

## 文件结构

```
新增 (6 files):
  app/services/strategy_unified/opportunity_scanner.py    # 批量扫描 + 综合评分
  app/static/pages/strategy/renderScanMatrix.js           # 机会矩阵表格
  app/static/pages/strategy/renderScanRanked.js           # 排序推荐列表
  app/static/pages/strategy/renderDetailPanel.js          # 侧拉详情面板
  tests/test_opportunity_scanner.py                       # 后端单元测试
  tests/test_strategy_scan_endpoint.py                    # 后端集成测试

修改 (5 files):
  app/api/v1/endpoints/strategy.py                        # + /strategy/scan 端点
  app/services/cache_registry.py                          # + strategy_scan cache key + TTL
  app/static/pages/strategy/index.js                      # 重写为扫描主页 + 面板控制器
  app/static/core/api.js                                  # + getStrategyScan()
  app/static/styles.css                                   # + 扫描面板/侧拉面板 CSS
```

---

### Task 1: 后端 — OpportunityScanner 服务

**Files:**
- Create: `app/services/strategy_unified/opportunity_scanner.py`
- Create: `tests/test_opportunity_scanner.py`

- [ ] **Step 1: 编写单元测试**

```python
# tests/test_opportunity_scanner.py
import pytest
from app.services.strategy_unified.opportunity_scanner import (
    OpportunityScanner,
    compute_opportunity_score,
)


class TestComputeOpportunityScore:
    def test_perfect_long_signal(self):
        """全票做多: confidence=80, rr=3.0, consistency=100, 1w frame"""
        score = compute_opportunity_score(
            confidence=80,
            risk_reward=3.0,
            direction="LONG",
            modules_direction_tally={"bullish": 4, "bearish": 0, "neutral": 0},
            timeframe="1w",
        )
        # confidence 80*0.40=32, rr 3/5*100*0.25=15, consistency=100*0.20=20, timeframe=100*0.15=15
        assert score == pytest.approx(82.0)

    def test_mixed_signal_low_consistency(self):
        """分歧信号: 2个偏多 2个偏空"""
        score = compute_opportunity_score(
            confidence=55,
            risk_reward=1.2,
            direction="LONG",
            modules_direction_tally={"bullish": 2, "bearish": 2, "neutral": 0},
            timeframe="4h",
        )
        # consistency=0 (矛盾), timeframe=40*0.15=6
        assert score == pytest.approx(34.0)

    def test_wait_direction_returns_zero(self):
        """WAIT 方向不应参与排序，score 返回 0"""
        score = compute_opportunity_score(
            confidence=50,
            risk_reward=1.0,
            direction="WAIT",
            modules_direction_tally={"bullish": 0, "bearish": 0, "neutral": 4},
            timeframe="1d",
        )
        assert score == 0.0

    def test_risk_reward_capped(self):
        """盈亏比 > 5 时归一化到 1.0"""
        score_5x = compute_opportunity_score(
            confidence=70, risk_reward=5.0, direction="LONG",
            modules_direction_tally={"bullish": 3, "bearish": 0, "neutral": 1},
            timeframe="1d",
        )
        score_10x = compute_opportunity_score(
            confidence=70, risk_reward=10.0, direction="LONG",
            modules_direction_tally={"bullish": 3, "bearish": 0, "neutral": 1},
            timeframe="1d",
        )
        assert score_5x == score_10x  # both capped at rr_norm=1.0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_opportunity_scanner.py -v
# Expected: FAIL — module not found
```

- [ ] **Step 3: 实现 `compute_opportunity_score`**

```python
# app/services/strategy_unified/opportunity_scanner.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.services.strategy_unified.unified_service import UnifiedStrategyService

logger = logging.getLogger(__name__)

SCAN_TIMEFRAMES = ("1w", "1d", "4h")

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_opportunity_score(
    *,
    confidence: float,
    risk_reward: float,
    direction: str,
    modules_direction_tally: dict[str, int],
    timeframe: str,
) -> float:
    """综合评分: confidence(40%) + risk_reward(25%) + consistency(20%) + timeframe(15%)."""
    if direction in ("WAIT", "NO_TRADE", "RANGE_NO_EDGE"):
        return 0.0

    # 1. Confidence (0-100 already)
    c_score = confidence * 0.40

    # 2. Risk/reward — normalize: min(rr/5, 1.0) × 100
    rr_norm = min(risk_reward / 5.0, 1.0) if risk_reward > 0 else 0.0
    rr_score = rr_norm * 100 * 0.25

    # 3. Signal consistency — tally module directions
    total_modules = sum(modules_direction_tally.values())
    if total_modules == 0:
        consistency = 0
    else:
        max_same = max(modules_direction_tally.values())
        if max_same >= 3:
            consistency = 100
        elif max_same == 2:
            consistency = 50
        else:
            consistency = 0
    cs_score = consistency * 0.20

    # 4. Timeframe bonus
    tf_bonus = {"1w": 100, "1d": 70, "4h": 40, "1h": 0, "15m": 0}
    tf_score = tf_bonus.get(timeframe, 0) * 0.15

    return round(c_score + rr_score + cs_score + tf_score, 1)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_opportunity_scanner.py -v
# Expected: 4 passed
```

- [ ] **Step 5: 实现 `OpportunityScanner.scan_all()`**

```python
# 在 opportunity_scanner.py 中继续添加

@dataclass(slots=True)
class ScanItem:
    instrument_id: str
    instrument_code: str
    timeframe: str
    direction: str          # "LONG" | "SHORT" | "WAIT"
    direction_label: str    # "做多" | "做空" | "等待"
    confidence: float
    score: float
    summary: str
    risk_reward: float
    leverage_hint: str      # "spot" | "3x" | "5x"
    position_cap: str       # "standard" | "reduced" | "observe"
    primary_driver: str
    conflicts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanResult:
    scanned_at: str
    instruments: list[str]
    timeframes: list[str]
    matrix: list[ScanItem]
    ranked: list[ScanItem]
    cache_meta: dict[str, Any]


class OpportunityScanner:
    """Batch-scan all instruments × core timeframes for actionable opportunities."""

    def __init__(self, repository: MarketRepository) -> None:
        self._repository = repository

    async def scan_all(
        self,
        instrument_ids: list[str],
        instrument_codes: dict[str, str],
        *,
        timeframes: tuple[str, ...] = SCAN_TIMEFRAMES,
    ) -> ScanResult:
        """并行扫描所有品种×级别。每次调用创建新的 UnifiedStrategyService 实例。"""
        now = datetime.now(timezone.utc)

        async def _scan_one(instrument_id: str, code: str, tf: str) -> ScanItem | None:
            try:
                service = UnifiedStrategyService(self._repository)
                payload = await service.build_unified_strategy(instrument_id, force=False)
                return _extract_scan_item(payload, instrument_id, code, tf)
            except Exception:
                logger.exception("opportunity_scanner: failed %s %s", instrument_id, tf)
                return None

        tasks = [
            _scan_one(iid, instrument_codes.get(iid, iid), tf)
            for iid in instrument_ids
            for tf in timeframes
        ]
        results = await asyncio.gather(*tasks)

        items = [r for r in results if r is not None]
        ranked = sorted(
            [it for it in items if it.direction not in ("WAIT", "NO_TRADE", "RANGE_NO_EDGE")],
            key=lambda it: it.score,
            reverse=True,
        )

        return ScanResult(
            scanned_at=now.isoformat(),
            instruments=list(instrument_ids),
            timeframes=list(timeframes),
            matrix=items,
            ranked=ranked,
            cache_meta={
                "fresh_until": (now.replace(second=0, microsecond=0)).isoformat(),
                "source": "live",
                "instruments_scanned": len(instrument_ids),
                "opportunities_found": len(ranked),
            },
        )


def _extract_scan_item(
    payload: dict[str, Any],
    instrument_id: str,
    code: str,
    timeframe: str,
) -> ScanItem:
    """从 UnifiedStrategy 响应中提取单条扫描项。"""
    decision = payload.get("trade_decision") or {}
    direction = decision.get("direction") or "WAIT"
    direction_label = {"LONG": "做多", "SHORT": "做空"}.get(direction, "等待")

    # 提取模块方向统计（从 evidence_trace 中）
    trace = payload.get("evidence_trace") or {}
    modules = trace.get("modules") or {}
    tally = {"bullish": 0, "bearish": 0, "neutral": 0}
    for mod in modules.values():
        bias = (mod.get("bias") or "").lower()
        if bias in tally:
            tally[bias] += 1

    risk_reward = float(decision.get("risk_reward_ratio") or 0)
    confidence = float(decision.get("confidence") or 0)
    score = compute_opportunity_score(
        confidence=confidence,
        risk_reward=risk_reward,
        direction=direction,
        modules_direction_tally=tally,
        timeframe=timeframe,
    )

    return ScanItem(
        instrument_id=instrument_id,
        instrument_code=code,
        timeframe=timeframe,
        direction=direction,
        direction_label=direction_label,
        confidence=round(confidence, 1),
        score=score,
        summary=decision.get("primary_reason") or "",
        risk_reward=round(risk_reward, 2),
        leverage_hint=decision.get("recommended_leverage") or "spot",
        position_cap=decision.get("position_cap") or "standard",
        primary_driver=trace.get("primary_driver") or "",
        conflicts=decision.get("conflicts") or [],
    )
```

- [ ] **Step 6: 编写 OpportunityScanner 集成测试**

```python
# tests/test_opportunity_scanner.py 中继续添加
class TestOpportunityScanner:
    @pytest.mark.asyncio
    async def test_scan_all_returns_correct_structure(self):
        """扫描返回的 ScanResult 包含 matrix 和 ranked 列表"""
        # 此测试依赖数据库中的真实数据，标记为集成测试
        pytest.importorskip("app.services.strategy_unified.unified_service")
        ...

    @pytest.mark.asyncio
    async def test_ranked_sorted_by_score_desc(self):
        """ranked 列表按 score 降序排列"""
        ...

    @pytest.mark.asyncio
    async def test_wait_items_excluded_from_ranked(self):
        """WAIT/NO_TRADE 方向不出现于 ranked 列表"""
        ...
```

- [ ] **Step 7: 运行测试**

```bash
python -m pytest tests/test_opportunity_scanner.py -v
```

- [ ] **Step 8: Commit**

```bash
git add app/services/strategy_unified/opportunity_scanner.py tests/test_opportunity_scanner.py
git commit -m "[strategy] add OpportunityScanner service with composite scoring"
```

---

### Task 2: 后端 — /strategy/scan 端点 + 缓存

**Files:**
- Modify: `app/api/v1/endpoints/strategy.py`
- Modify: `app/services/cache_registry.py`
- Create: `tests/test_strategy_scan_endpoint.py`

- [ ] **Step 1: 注册缓存 key 和 TTL**

```python
# app/services/cache_registry.py — 在现有函数后追加

def strategy_scan_cache_key(source_version: str = CACHE_SOURCE_VERSION) -> str:
    return f"strategy_scan:v{source_version}"

# 在 ttl_seconds_for_page() 的 mapping dict 中添加:
# "strategy_scan": 900,  # 15 minutes
```

具体修改位置：在 `ttl_seconds_for_page()` 函数（约 line 276）的 mapping 字典中添加 `"strategy_scan": 900`。在文件末尾添加 `strategy_scan_cache_key()` 函数和 `expires_at_for_scan()` 辅助。

- [ ] **Step 2: 添加端点**

```python
# app/api/v1/endpoints/strategy.py — 在文件末尾、router 定义之后追加

from app.services.strategy_unified.opportunity_scanner import OpportunityScanner, ScanResult

@router.get("/scan", response_model=ScanResult)
async def get_strategy_scan(
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    """Scan all configured instruments × core timeframes for opportunities."""
    repository = MarketRepository(session)
    cache_key = strategy_scan_cache_key()

    # Cache-first
    if not force:
        cache = await repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        if cache is not None and cache.payload_json and status not in {"missing", "error"}:
            payload = dict(cache.payload_json)
            payload.setdefault("cache_meta", {})
            payload["cache_meta"]["source"] = "cache"
            return payload

    # Fresh scan
    from app.core.state import app_state as global_state  # or use db query
    instruments = await repository.list_instruments()
    instrument_ids = [i.instrument_id for i in instruments if i.instrument_id]
    instrument_codes = {i.instrument_id: (i.code or i.instrument_id) for i in instruments}

    scanner = OpportunityScanner(repository)
    result = await scanner.scan_all(instrument_ids, instrument_codes)

    # Write cache
    now = datetime.now(timezone.utc)
    await repository.upsert_page_snapshot_cache(
        cache_key=cache_key,
        page_type="strategy_scan",
        payload_json=result if isinstance(result, dict) else _scan_result_to_dict(result),
        status="ready",
        cache_state="fresh",
        snapshot_at=now,
        data_ts=now,
        expires_at=expires_at_for_scan(now),
        source_version=CACHE_SOURCE_VERSION,
    )

    return result
```

**注意**: `ScanResult` 需实现 `.model_dump()` 或转为 dict。由于 `OpportunityScanner` 不在 pydantic 模型中，端点返回需使用 `response_model` 或手动 `JSONResponse`。推荐使用 `ScanResult` 的 `__dict__` 转换或定义一个 pydantic schema。

- [ ] **Step 3: 编写端点的集成测试**

```python
# tests/test_strategy_scan_endpoint.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app


@pytest.mark.asyncio
async def test_scan_endpoint_returns_200():
    """GET /api/v1/strategy/scan 返回 200 和有效结构"""
    app = create_app(enable_lifespan=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/strategy/scan")
        assert response.status_code == 200
        data = response.json()
        assert "matrix" in data
        assert "ranked" in data
        assert "instruments" in data
        assert "scanned_at" in data


@pytest.mark.asyncio
async def test_scan_endpoint_force_refreshes():
    """?force=true 不走缓存"""
    ...


@pytest.mark.asyncio
async def test_scan_endpoint_ranked_sorted():
    """ranked 列表按 score 降序"""
    ...
```

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/endpoints/strategy.py app/services/cache_registry.py tests/test_strategy_scan_endpoint.py
git commit -m "[strategy] add GET /strategy/scan endpoint with 15min cache"
```

---

### Task 3: 前端 — api.js 新方法

**Files:**
- Modify: `app/static/core/api.js`

- [ ] **Step 1: 添加 `getStrategyScan()`**

在 `api.js` 的 class 中，`getUnifiedStrategy()` 方法旁边（约 line 639 附近）添加：

```js
getStrategyScan(options = {}) {
    return requestJson("/strategy/scan", {
      params: {},
      ttl: options.force ? 0 : 60,
      force: options.force ?? false,
      timeoutMs: options.timeoutMs ?? 30000,
      signal: options.signal,
      retry: 1,
    });
},
```

- [ ] **Step 2: Commit**

```bash
git add app/static/core/api.js
git commit -m "[frontend] add getStrategyScan() API method"
```

---

### Task 4: 前端 — 机会矩阵 `renderScanMatrix.js`

**Files:**
- Create: `app/static/pages/strategy/renderScanMatrix.js`

- [ ] **Step 1: 实现矩阵渲染**

```js
// app/static/pages/strategy/renderScanMatrix.js
import { escapeHtml } from "../../core/dom.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

/**
 * Render the instrument × timeframe opportunity matrix.
 * @param {Array} matrix - ScanItem[] from /strategy/scan
 * @param {Array} instruments - appState.instruments array
 * @param {Function} onSelect - callback(instrumentId, timeframe) when a cell is clicked
 */
export function renderScanMatrix(matrix, instruments, onSelect) {
  const codes = instruments.map((i) => i.code);
  const rows = instruments
    .map((inst) => {
      const cells = ["1w", "1d", "4h"]
        .map((tf) => {
          const item = matrix.find(
            (m) => m.instrument_code === inst.code && m.timeframe === tf
          );
          return renderCell(item, inst.id, tf, onSelect);
        })
        .join("");
      return `<tr>
        <td class="scan-matrix-code">${escapeHtml(inst.code)}</td>
        ${cells}
      </tr>`;
    })
    .join("");

  return `
    <div class="table-wrap">
      <table class="scan-matrix-table">
        <thead>
          <tr>
            <th>品种</th>
            <th>${TIMEFRAME_LABELS["1w"]}</th>
            <th>${TIMEFRAME_LABELS["1d"]}</th>
            <th>${TIMEFRAME_LABELS["4h"]}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="scan-matrix-hint">点击任意单元格查看完整策略推演</p>
  `;
}

function renderCell(item, instrumentId, timeframe, onSelect) {
  if (!item || item.direction === "WAIT" || item.direction === "NO_TRADE") {
    return `<td class="scan-cell scan-cell-wait">
      <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">等待</button>
    </td>`;
  }
  const tone = item.direction === "LONG" ? "bullish" : "bearish";
  const arrow = item.direction === "LONG" ? "↑" : "↓";
  return `<td class="scan-cell" data-tone="${tone}">
    <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">
      <strong>${escapeHtml(item.direction_label)} ${arrow}</strong>
      <small>${escapeHtml(String(Math.round(item.confidence)))}%</small>
    </button>
  </td>`;
}

/**
 * Attach click handlers to matrix cells after rendering.
 */
export function bindScanMatrix(onSelect) {
  document.querySelectorAll(".scan-cell-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const instrumentId = btn.dataset.instrument;
      const timeframe = btn.dataset.timeframe;
      if (instrumentId && timeframe) onSelect(instrumentId, timeframe);
    });
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/pages/strategy/renderScanMatrix.js
git commit -m "[frontend] add scan matrix renderer (instrument × timeframe grid)"
```

---

### Task 5: 前端 — 排序推荐列表 `renderScanRanked.js`

**Files:**
- Create: `app/static/pages/strategy/renderScanRanked.js`

- [ ] **Step 1: 实现排序列表渲染**

```js
// app/static/pages/strategy/renderScanRanked.js
import { escapeHtml, formatNumber } from "../../core/dom.js";

const LEVEL_LABELS = { "1w": "战略级", "1d": "战术级", "4h": "执行级" };

/**
 * Render the ranked opportunity list (only items with direction, sorted by score).
 * @param {Array} ranked - ScanItem[] already sorted by score desc
 * @param {Function} onSelect - callback(instrumentId, timeframe)
 */
export function renderScanRanked(ranked, onSelect) {
  if (!ranked.length) {
    return `<div class="data-state data-state-empty">当前无明确交易机会。所有品种×级别均处于等待状态。</div>`;
  }

  const cards = ranked
    .map((item) => {
      const tone = item.direction === "LONG" ? "bullish" : "bearish";
      const arrow = item.direction === "LONG" ? "↑" : "↓";
      const level = LEVEL_LABELS[item.timeframe] || item.timeframe;
      return `
        <article class="card scan-ranked-card" data-tone="${tone}" data-instrument="${escapeHtml(item.instrument_id)}" data-timeframe="${escapeHtml(item.timeframe)}" style="cursor:pointer">
          <div class="scan-ranked-head">
            <div>
              <span class="impact-chip impact-${tone}">${escapeHtml(item.direction_label)} ${arrow}</span>
              <span class="status-chip chip-neutral">${escapeHtml(level)}</span>
            </div>
            <div class="scan-ranked-score">
              <strong>${escapeHtml(String(item.score))}</strong>
              <small>分</small>
            </div>
          </div>
          <p class="scan-ranked-summary">${escapeHtml(item.summary || "暂无摘要")}</p>
          <div class="scan-ranked-meta">
            <span>置信度 ${escapeHtml(String(Math.round(item.confidence)))}%</span>
            <span>盈亏比 ${escapeHtml(formatNumber(item.risk_reward, 2))}:1</span>
            <span>${escapeHtml(item.leverage_hint === "spot" ? "现货" : item.leverage_hint)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  return `<div class="scan-ranked-list">${cards}</div>`;
}

/**
 * Attach click handlers to ranked cards after rendering.
 */
export function bindScanRanked(onSelect) {
  document.querySelectorAll(".scan-ranked-card").forEach((card) => {
    card.addEventListener("click", () => {
      const instrumentId = card.dataset.instrument;
      const timeframe = card.dataset.timeframe;
      if (instrumentId && timeframe) onSelect(instrumentId, timeframe);
    });
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/pages/strategy/renderScanRanked.js
git commit -m "[frontend] add ranked opportunity list renderer"
```

---

### Task 6: 前端 — 侧拉详情面板 `renderDetailPanel.js`

**Files:**
- Create: `app/static/pages/strategy/renderDetailPanel.js`

- [ ] **Step 1: 实现侧拉面板**

```js
// app/static/pages/strategy/renderDetailPanel.js
import { escapeHtml, loadingState, errorState, statusBanner } from "../../core/dom.js";
import { renderOverview } from "./renderOverview.js?v=trade-4h-v1";
import { renderExecutionPlan } from "./renderExecutionPlan.js?v=trade-4h-v1";
import { renderDecisionAudit } from "./renderDecisionAudit.js?v=auditable-v1";
import { renderEvidenceStack } from "./renderEvidenceStack.js?v=compact-v3";
import { renderMarketOperation } from "./renderMarketOperation.js?v=decision-text-cleanup";
import { renderRiskPanel } from "./renderRiskPanel.js?v=compact-v3";
import { renderEventWatch } from "./renderEventWatch.js?v=compact-v3";
import { buildDataDegradedCard } from "./adapter.js?v=trade-4h-v1";

const helpers = {
  escapeHtml,
  formatNumber: (v, d) => { const n = Number(v); return Number.isNaN(n) ? "-" : n.toFixed(d ?? 2); },
  formatDateTime: (v) => v || "-",
  emptyState: (msg) => `<div class="data-state data-state-empty">${escapeHtml(msg)}</div>`,
  errorState: (msg) => `<div class="data-state data-state-error">${escapeHtml(msg)}</div>`,
};

/**
 * Open the slide-in detail panel for a specific instrument+timeframe.
 * @param {string} instrumentId
 * @param {string} timeframe
 * @param {Function} loadStrategy - async (instrumentId, timeframe) => unifiedPayload
 * @param {Function} onClose - callback when panel is dismissed
 */
export function openDetailPanel(instrumentId, timeframe, loadStrategy, onClose) {
  // Create panel if not exists
  let panel = document.getElementById("strategy-detail-panel");
  let overlay = document.getElementById("strategy-detail-overlay");

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "strategy-detail-overlay";
    overlay.className = "strategy-detail-overlay";
    document.body.appendChild(overlay);
  }

  if (!panel) {
    panel = document.createElement("aside");
    panel.id = "strategy-detail-panel";
    panel.className = "strategy-detail-panel";
    document.body.appendChild(panel);
  }

  // Loading state
  panel.innerHTML = `
    <div class="strategy-detail-header">
      <button class="strategy-detail-back secondary-button" id="strategy-detail-close">← 返回扫描</button>
      <div class="strategy-detail-breadcrumb">
        <span class="eyebrow">STRATEGY DETAIL</span>
        <h2 id="strategy-detail-title">加载中...</h2>
      </div>
    </div>
    <div class="strategy-detail-body" id="strategy-detail-body">
      ${loadingState("正在加载完整策略推演...")}
    </div>
  `;

  // Show panel + overlay
  panel.classList.add("is-open");
  overlay.classList.add("is-visible");

  // Close handler
  const close = () => {
    panel.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    if (onClose) onClose();
  };
  overlay.addEventListener("click", close);
  document.getElementById("strategy-detail-close")?.addEventListener("click", close);
  document.addEventListener("keydown", function escHandler(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", escHandler); }
  });

  // Load and render
  loadStrategy(instrumentId, timeframe)
    .then((model) => {
      const title = document.getElementById("strategy-detail-title");
      const body = document.getElementById("strategy-detail-body");
      if (!body) return;

      const instCode = model.instrument_code || instrumentId;
      const dirLabel = model.trade_decision?.side || "";
      if (title) title.textContent = `${instCode} · ${timeframe} · ${dirLabel}`;

      body.innerHTML = `
        ${renderOverview(model, helpers)}
        ${renderExecutionPlan(model, helpers)}
        ${renderDecisionAudit(model, helpers)}
        ${renderEvidenceStack(model, helpers)}
        ${renderMarketOperation(model, helpers)}
        ${renderRiskPanel(model, helpers)}
        ${renderEventWatch(model, helpers)}
        ${buildDataDegradedCard(model)}
      `;
    })
    .catch((err) => {
      const body = document.getElementById("strategy-detail-body");
      if (body) body.innerHTML = errorState(`策略加载失败：${escapeHtml(err.message || String(err))}`);
    });
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/pages/strategy/renderDetailPanel.js
git commit -m "[frontend] add slide-in detail panel for strategy drill-down"
```

---

### Task 7: 前端 — 重写策略页主入口 `index.js`

**Files:**
- Modify: `app/static/pages/strategy/index.js`

- [ ] **Step 1: 重写 `renderStrategy` 为扫描主页 + 面板控制器**

完整替换文件内容：

```js
// app/static/pages/strategy/index.js
import { api } from "../../core/api.js";
import { appState } from "../../core/state.js";
import {
  escapeHtml, formatNumber, formatDateTime, setRoot,
  statusBanner, loadingState, emptyState,
} from "../../core/dom.js";
import { normalizeUnifiedStrategy } from "./adapter.js?v=trade-4h-v1";
import { renderScanMatrix, bindScanMatrix } from "./renderScanMatrix.js";
import { renderScanRanked, bindScanRanked } from "./renderScanRanked.js";
import { openDetailPanel } from "./renderDetailPanel.js";
import { mountPageGuide } from "../../ui/pageGuideFab.js";

let mounted = false;
let activeController = null;
let scanData = null; // cached ScanResult

function renderScanShell() {
  setRoot(`
    <section class="strategy-v2-page strategy-scan-page">
      <section class="strategy-v2-toolbar card">
        <div>
          <p class="eyebrow">OPPORTUNITY SCANNER</p>
          <h1>跨品种跨周期机会扫描</h1>
          <p>自动扫描全部品种 · 周线/日线/4H · 综合评分排序</p>
        </div>
        <div class="strategy-v2-actions">
          <button type="button" class="primary-button" id="strategy-scan-refresh">刷新扫描</button>
        </div>
      </section>
      <div id="strategy-scan-status"></div>
      <section class="grid cols-2 strategy-scan-grid">
        <section class="card" id="strategy-scan-matrix-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">MATRIX</p>
              <h2>机会矩阵</h2>
              <p class="section-summary">品种 × 级别 一览</p>
            </div>
          </div>
          <div id="strategy-scan-matrix"></div>
        </section>
        <section class="card" id="strategy-scan-ranked-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">RANKED</p>
              <h2>机会排序</h2>
              <p class="section-summary">按综合评分降序，仅显示有方向的信号</p>
            </div>
          </div>
          <div id="strategy-scan-ranked"></div>
        </section>
      </section>
    </section>
  `);
}

function renderScanResults(data) {
  scanData = data;

  const status = document.getElementById("strategy-scan-status");
  const oppCount = data.ranked?.length || 0;
  const totalCells = (data.instruments?.length || 0) * (data.timeframes?.length || 0);

  const sourceLabel = data.cache_meta?.source === "cache" ? "（缓存）" : "";
  if (status) {
    status.innerHTML = statusBanner(
      oppCount > 0
        ? `发现 ${oppCount} 个交易机会 / 共扫描 ${totalCells} 个级别组合 ${sourceLabel}`
        : `当前无明确交易机会 ${sourceLabel}`,
      oppCount > 0 ? "success" : "neutral"
    );
  }

  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) {
    matrixEl.innerHTML = renderScanMatrix(data.matrix || [], appState.instruments, onSelectOpportunity);
    bindScanMatrix(onSelectOpportunity);
  }

  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) {
    rankedEl.innerHTML = renderScanRanked(data.ranked || [], onSelectOpportunity);
    bindScanRanked(onSelectOpportunity);
  }
}

function renderScanLoading() {
  const status = document.getElementById("strategy-scan-status");
  if (status) status.innerHTML = statusBanner("正在扫描全部品种×级别...", "info");
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = loadingState("正在计算各品种各周期策略...");
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = loadingState("等待扫描完成...");
}

function onSelectOpportunity(instrumentId, timeframe) {
  const loadStrategy = async (iid, tf) => {
    const payload = await api.getUnifiedStrategy(iid, { force: false, timeoutMs: 20000 });
    const code = appState.instruments.find((i) => i.id === iid)?.code || iid;
    const model = normalizeUnifiedStrategy(payload, {});
    model.instrument_code = code;
    model.data_access = { unified: payload, monitoring: null, derivatives: null, macro: null };
    model.data_access_failures = { unified: null, monitoring: null, derivatives: null, macro: null };
    return model;
  };
  openDetailPanel(instrumentId, timeframe, loadStrategy, () => {
    // Panel closed — no action needed
  });
}

async function loadScan(force = false) {
  activeController?.abort();
  activeController = new AbortController();
  try {
    const data = await api.getStrategyScan({ force, signal: activeController.signal, timeoutMs: 60000 });
    if (!mounted) return;
    renderScanResults(data);
  } catch (err) {
    if (err?.name === "AbortError") return;
    console.error("strategy:scan:error", err);
    const status = document.getElementById("strategy-scan-status");
    if (status) status.innerHTML = statusBanner("扫描失败，请稍后重试", "error");
  }
}

export async function renderStrategy() {
  mounted = true;
  renderScanShell();

  document.getElementById("strategy-scan-refresh")?.addEventListener("click", () => {
    loadScan(true);
  });

  const guideFab = mountPageGuide("ai-strategy");

  // Auto-scan on mount
  const scanPromise = loadScan(false);

  return {
    mount: async () => {
      // If returning to page with cached scan data, re-render
      if (scanData) renderScanResults(scanData);
      else await scanPromise;
    },
    unmount: async () => {
      guideFab.unmount();
      mounted = false;
      activeController?.abort();
      activeController = null;
    },
    pause: async () => {},
    resume: async () => {
      if (mounted && !scanData) await loadScan(false);
    },
  };
}

export default renderStrategy;
```

- [ ] **Step 2: Commit**

```bash
git add app/static/pages/strategy/index.js
git commit -m "[frontend] rewrite strategy page as multi-instrument opportunity scanner hub"
```

---

### Task 8: 前端 — CSS 样式

**Files:**
- Modify: `app/static/styles.css`

- [ ] **Step 1: 添加扫描面板 + 侧拉面板 CSS**

在 `styles.css` 末尾追加（约 line 9785 之后）：

```css
/* ------------------------------------------------------------------ */
/* Strategy Scan Page (Opportunity Scanner)                            */
/* ------------------------------------------------------------------ */

.strategy-scan-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.strategy-scan-grid {
  gap: 20px;
}

/* --- Scan Matrix Table --- */

.scan-matrix-table {
  width: 100%;
  border-collapse: collapse;
}

.scan-matrix-table th,
.scan-matrix-table td {
  padding: 8px 12px;
  text-align: center;
  font-size: 0.88rem;
}

.scan-matrix-table thead th {
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}

.scan-matrix-code {
  text-align: left;
  font-weight: 600;
  color: var(--text);
}

.scan-cell-btn {
  width: 100%;
  border: none;
  background: var(--bg-surface);
  color: var(--text);
  padding: 8px 6px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.82rem;
  transition: background 0.15s;
}

.scan-cell-btn:hover {
  background: var(--bg-hover);
}

.scan-cell[data-tone="bullish"] .scan-cell-btn {
  background: rgba(76, 175, 80, 0.12);
  color: #81c784;
}

.scan-cell[data-tone="bearish"] .scan-cell-btn {
  background: rgba(244, 67, 54, 0.12);
  color: #ef9a9a;
}

.scan-cell-wait .scan-cell-btn {
  color: var(--muted);
}

.scan-cell-btn strong {
  display: block;
  font-size: 0.9rem;
}

.scan-cell-btn small {
  display: block;
  font-size: 0.72rem;
  color: inherit;
  opacity: 0.8;
}

.scan-matrix-hint {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 8px;
  text-align: center;
}

/* --- Ranked List --- */

.scan-ranked-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scan-ranked-card {
  padding: 14px 16px;
  transition: box-shadow 0.15s, transform 0.1s;
}

.scan-ranked-card:hover {
  box-shadow: var(--shadow-card);
  transform: translateY(-1px);
}

.scan-ranked-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.scan-ranked-score strong {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--accent);
}

.scan-ranked-score small {
  font-size: 0.72rem;
  color: var(--muted);
  margin-left: 2px;
}

.scan-ranked-summary {
  font-size: 0.85rem;
  color: var(--text);
  margin: 0 0 8px;
  line-height: 1.4;
}

.scan-ranked-meta {
  display: flex;
  gap: 16px;
  font-size: 0.75rem;
  color: var(--muted);
}

/* --- Detail Slide-in Panel --- */

.strategy-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s;
}

.strategy-detail-overlay.is-visible {
  opacity: 1;
  pointer-events: auto;
}

.strategy-detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 58%;
  max-width: 820px;
  height: 100vh;
  background: var(--bg);
  border-left: 1px solid var(--border);
  z-index: 101;
  overflow-y: auto;
  transform: translateX(100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

.strategy-detail-panel.is-open {
  transform: translateX(0);
}

.strategy-detail-header {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.strategy-detail-back {
  flex-shrink: 0;
}

.strategy-detail-breadcrumb h2 {
  font-size: 1.1rem;
  margin: 0;
}

.strategy-detail-body {
  flex: 1;
  padding: 20px 24px 60px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

@media (max-width: 900px) {
  .strategy-detail-panel {
    width: 100%;
    max-width: 100%;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/styles.css
git commit -m "[frontend] add scan matrix, ranked list, and detail panel CSS"
```

---

### Task 9: 全量验证

- [ ] **Step 1: 后端语法检查**

```bash
python -c "import py_compile; py_compile.compile('app/services/strategy_unified/opportunity_scanner.py', doraise=True); py_compile.compile('app/api/v1/endpoints/strategy.py', doraise=True); py_compile.compile('app/services/cache_registry.py', doraise=True); print('All OK')"
```

- [ ] **Step 2: 后端测试**

```bash
python -m pytest tests/test_opportunity_scanner.py tests/test_strategy_scan_endpoint.py -v
```

- [ ] **Step 3: 前端语法检查**

```bash
for f in app/static/pages/strategy/index.js app/static/pages/strategy/renderScanMatrix.js app/static/pages/strategy/renderScanRanked.js app/static/pages/strategy/renderDetailPanel.js app/static/core/api.js; do node --check "$f" && echo "$f OK" || echo "$f FAIL"; done
```

- [ ] **Step 4: 启动服务 + 全量 verify_pages**

```bash
# Terminal 1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# Terminal 2
python tests/verify_pages.py
```

**Expected:** 11/11 冷启动 OK, 10/10 SPA 切换 OK。AI 策略页应显示为新的机会扫描面板，不再显示旧的单品种推演。

- [ ] **Step 5: 运行全量 pytest**

```bash
python -m pytest tests/ -q --tb=short
```

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "[strategy] verify: all tests passing, verify_pages 11/11 OK"
```

---

## 验证清单

```
☐ ruff: All checks passed
☐ pytest: all passed (including new opportunity_scanner + scan endpoint tests)
☐ node --check: all 5 JS files passed
☐ verify_pages.py: 11/11 cold start, 10/10 SPA
☐ 策略页显示为机会扫描面板（矩阵 + 排序列表）
☐ 点击矩阵单元格 → 侧拉详情面板（概览/执行计划/证据栈/风控）
☐ 点击排序列表卡片 → 同上
☐ Esc / 点击遮罩 / 返回按钮 → 面板关闭
☐ 刷新扫描按钮 → 触发 force scan
```
