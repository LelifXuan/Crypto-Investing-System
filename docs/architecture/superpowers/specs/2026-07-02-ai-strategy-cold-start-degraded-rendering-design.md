# AI Strategy Cold-Start Degraded Rendering + Background Prewarm — Design Spec

- **Date**: 2026-07-02
- **Branch**: `codex/fix-spa-rendering-cleanup` (V1.7)
- **Author**: Codex (接手维护)
- **Status**: Design approved, awaiting spec user-review → writing-plans

## 1. Problem Statement

### 1.1 用户观察
打开 AI 策略页 (`/strategy-page`) 时，**顶部出现红色错误提示条**：
> "统一策略读取失败，请稍后重试"

错误一致出现，**不论用户先前是否打开过其他页面**。这意味着即使 V1.7 引入了 `daily_first_page_prewarm` 中间件（`app/main.py:265-276`），用户在 UTC 日切之外打开策略页时，仍触发冷启动路径。

### 1.2 根因分析
策略页 (`app/static/pages/strategy/index.js:152`) 并行拉取 4 个 endpoint：

```javascript
const results = await Promise.allSettled([
  api.getUnifiedStrategy(instrumentId, { force, signal }),     // /strategy/unified
  api.getMonitoringDashboard(instrumentId, "1d", { signal }),   // /monitoring/dashboard
  api.getBtcDerivativesDashboard({ signal }),                   // /btc-derivatives/dashboard
  api.getMacroOverview({ signal }),                             // /monitoring/macro-overview
]);
```

在 `index.js:172-176`，若 `dataAccess.unified` 为 null（`/strategy/unified` 抛错），前端展示红色 `errorState`：

```javascript
if (!dataAccess.unified) {
  if (status) status.innerHTML = statusBanner("统一策略读取失败，请稍后重试", "error");
  const content = document.getElementById("strategy-content");
  if (content) content.innerHTML = errorState("统一策略读取失败，请稍后重试");
  return;
}
```

实测发现 `/strategy/unified` 在 cache 充足时可正常返回 200 + 完整 payload；但在**某些上游依赖陈旧/失败的场景**（如 onchain 上游缺失、macro 观察为空、btc_derivatives 缓存过期），`UnifiedStrategyService.build_unified_strategy()` 调用链中某个 engine 抛异常，endpoint 返回 5xx → 前端 Promise.allSettled 收到 rejection → 红色错误条。

### 1.3 设计目标
1. **永不抛错**：`/strategy/unified` 在任何上游失败场景下都返回 HTTP 200 + JSON payload
2. **降级渲染**：即使数据陈旧/缺失，前端也要渲染页面骨架，仅展示 warning 而非 error
3. **后台预热**：用户首次打开策略页时，**后台静默**触发 monitoring / derivatives / macro 的预热任务；无需用户手动操作
4. **数据契约兼容**：现有 `status="ready"` payload 完全兼容；新增 `degraded` 状态不影响旧前端

## 2. Architecture

### 2.1 系统边界
- **本设计仅修改** AI 策略页相关代码（API 端点 + 后端服务 + 前端 adapter + 前端 index.js）
- **不修改**：monitoring / derivatives / macro 三个独立 endpoint 的现有行为（它们已经各自具备降级路径）

### 2.2 数据流
```
用户点击 /strategy-page
    │
    ├─ SPA mount: index.js renderStrategy()
    │    ├─ fire-and-forget api.prewarmStrategy()           ← 新增
    │    └─ loadUnifiedStrategy()
    │         ├─ Promise.allSettled(4 endpoints)
    │         │    ├─ /strategy/unified  ──→  UnifiedStrategyService
    │         │    │                          ├─ loader.load()       (已加 try/except)
    │         │    │                          ├─ structure_engine    (需加固)
    │         │    │                          ├─ macro_engine        (需加固)
    │         │    │                          ├─ derivatives_engine  (需加固)
    │         │    │                          ├─ onchain_engine      (需加固)
    │         │    │                          ├─ risk_gate_engine    (需加固)
    │         │    │                          ├─ trade_plan_engine   (需加固)
    │         │    │                          ├─ evidence_builder    (需加固)
    │         │    │                          └─ narrative_renderer  (需加固)
    │         │    │
    │         │    ├─ /monitoring/dashboard  ──→ MonitoringDashboardService
    │         │    ├─ /btc-derivatives/dashboard ──→ BtcDerivativesLiveService
    │         │    └─ /monitoring/macro-overview  ──→ MacroOverviewService
    │         │
    │         ├─ if !dataAccess.unified
    │         │    ├─ statusBanner("warning")                ← 新增（替换 "error"）
    │         │    ├─ degradedState skeleton render          ← 新增 helper
    │         │    └─ api.prewarmStrategy()                 ← 新增
    │         │
    │         └─ else: renderModel(normalized payload)
    │
    └─ prewarmStrategy() ──→ POST /strategy/prewarm          ← 新增端点
                                 └─ precompute_service.enqueue_hint()
                                      candidates=["monitoring","btc-derivatives","macro-overview"]
                                      priority=2, visible=false
                                      (后台 worker 异步执行)
```

### 2.3 关键设计决策
1. **HTTP 200 + degraded payload**（而非 5xx）—— 让前端用 payload 字段判断，而非 HTTP 状态码
2. **每个 engine 独立 try/except** —— 一个失败不影响其他（与现状一致，只是要补全现有漏洞）
3. **background prewarm 用现有 precompute_service** —— 复用 V1.7 已有的 `enqueue_hint()` 机制
4. **degraded 视觉用 warning 颜色**（黄色），区别于 error（红色）

## 3. Components

### 3.1 后端：`/strategy/unified` 端点加固

**File**: `app/api/v1/endpoints/strategy.py`

**改动**:
- 整个 endpoint body 包 try/except
- 失败时返回 HTTP 200 + degraded payload (含 `degraded: true`, `degraded_components`, `prewarm_status`)
- 记录 warning 级 logger

### 3.2 后端：`MarketContextBuilder.get_context()` 加固

**File**: `app/services/market_context.py`

**改动**:
- `ChipStructureService.analyze()` 调用包 try/except，失败时返回 low_confidence fallback
- `MacroOverviewService.build_overview()` 调用包 try/except，失败时返回空 MacroOverviewResponse
- `OnchainFeatureEngine.build()` 已有 `_missing()`，仅加 try/except 防止新代码引入 throws

### 3.3 后端：`UnifiedStrategyService.build_unified_strategy()` 加固

**File**: `app/services/strategy_unified/unified_service.py`

**改动**:
- 每个 engine（structure / macro / capital / derivatives / onchain / cross_horizon / risk_gate / trade_plan / evidence / narrative）包 try/except
- 失败时该 engine 返回 degraded fallback，标记 `degraded_components`
- 最终 payload 中新增 `degraded: bool`, `degraded_components: list[str]`, `prewarm_status: str`

### 3.4 后端：新端点 `/strategy/prewarm`

**File**: `app/api/v1/endpoints/strategy.py`

**改动**:
- 新增 `POST /strategy/prewarm` 端点
- 调用 `precompute_service.enqueue_hint()` enqueue 三个依赖的预热任务
- 返回 `{status: "enqueued", eta_seconds: 30}`（不等待实际执行）

### 3.5 后端：Schema 更新

**File**: `app/schemas/strategy_unified.py`

**改动**:
- `StrategyUnifiedRead` 新增 3 个 optional 字段：
  - `degraded: bool = False`
  - `degraded_components: list[str] = []`
  - `prewarm_status: str = "idle"`
- 向后兼容：旧 payload 缺这些字段时按默认值处理

### 3.6 前端：`degradedState` helper

**File**: `app/static/core/dom.js`

**改动**:
- 新增 `degradedState(title, detail)` helper
- 与 `errorState()` 视觉区别：黄色边框 + warning 图标（非红色）
- 展示友好提示："正在后台预热，30 秒后自动更新"

### 3.7 前端：`api.prewarmStrategy()`

**File**: `app/static/core/api.js`

**改动**:
- 新增 `prewarmStrategy(instrumentId)` 方法
- 调用 `POST /strategy/prewarm`，timeoutMs=3000（短超时，仅 fire-and-forget）

### 3.8 前端：`index.js` mount + 降级渲染

**File**: `app/static/pages/strategy/index.js`

**改动**:
- `renderStrategy().mount()` 第一行调用 `api.prewarmStrategy()`（fire-and-forget）
- `loadUnifiedStrategy()` line 172-176：替换 `errorState` 为 `degradedState`，statusBanner 从 "error" 改为 "warning"
- 添加 `failed.length === 4` 分支同样的降级处理（4 endpoint 全失败）
- 新增对 payload 中 `degraded: true` 的识别：statusBanner 显示 "数据部分降级"

### 3.9 测试：degraded 路径覆盖

**新增 file**: `tests/test_strategy_unified_degraded.py`
- Mock 各 upstream 失败，断言 endpoint 返回 200 + degraded payload
- 测试 prewarm endpoint 成功 enqueue
- 测试 frontend degraded 状态渲染（Playwright）

**修改 file**: `tests/test_strategy_unified_api.py`
- 断言新字段存在且默认值正确

## 4. Data Flow Details

### 4.1 degraded payload 形状

```json
{
  "instrument_id": "btc-usdt-perp",
  "generated_at": "2026-07-02T06:30:00Z",
  "status": "degraded",                       // ← 旧值：ready / ready_with_warnings；新增：degraded
  "degraded": true,                            // ← 新增字段
  "degraded_components": ["onchain_regime"],   // ← 新增字段
  "prewarm_status": "enqueued",                // ← 新增字段（idle / enqueued / running / ready）
  "refresh_state": "computed_with_context_fallback",
  "refresh_limitations": [...],
  "unified_state": {
    "code": "DATA_DEGRADED",
    "label": "数据质量不足",
    "permission": "observe",
    "risk_level": "low",
    "instruction": "部分数据源不可用，等待后台预热完成。",
    "current_price": 60730.4
  },
  "horizon_views": {...},                      // 正常填充（即使个别 timeframe degraded）
  "horizon_governance": {...},
  "market_operation": {
    "chain": {
      "onchain_regime": {
        "bias": "NEUTRAL",
        "confidence": 0,
        "details": {
          "data_status": "upstream_missing",
          "source_page": "onchain"
        }
      }
      // 其他 4 维正常
    }
  },
  "timeframe_stack": [...],
  "trade_plans": [...],
  "risk_alerts": [
    {"label": "链上数据缺失", "severity": "warning", ...}
  ],
  ...
}
```

### 4.2 preload 流程（前端 mount）

```
mount() {
  // 1. fire-and-forget prewarm（不等返回）
  api.prewarmStrategy(instrumentId).catch(() => {});

  // 2. 立即加载当前缓存
  await loadUnifiedStrategy();
}

loadUnifiedStrategy() {
  // 4 endpoint 并行（V1.7 已实现）
  const results = await Promise.allSettled([...]);

  if (!dataAccess.unified) {
    // 3a. 触发后台预热（如果 mount 时未成功）
    api.prewarmStrategy(appState.selectedInstrumentId).catch(() => {});

    // 3b. degraded 渲染（替换 errorState）
    statusBanner("warning", "策略推演暂时不可用，已自动触发后台预热");
    degradedState("策略推演暂时不可用", "30 秒后自动更新");
    return;
  }

  // 4. 正常渲染（V1.7 已实现）
  renderModel(model);
}
```

### 4.3 后台 prewarm 任务

`POST /strategy/prewarm` 内部：
```python
precompute_service.enqueue_hint(PrecomputeHintRequest(
    current_page="strategy",
    instrument_id=instrument_id,
    timeframe="1d",
    reason="strategy_cold_start",
    candidates=["monitoring", "btc-derivatives", "macro-overview"],
    priority=2,
    visible=False,  # 用户看不到 worker 日志
))
```

后台 worker（已存在）会：
- 调用 `IndicatorMonitoringService.sync_*()` 收集 monitoring 数据
- 调用 `btc_derivatives_live_service.dashboard(force=True)` 刷新衍生品
- 调用 `MacroOverviewService.build_overview()` 刷新宏观

完成后，下一次 `/strategy/unified` 请求会自动返回新数据。

## 5. Error Handling

| 失败场景 | 旧行为 | 新行为 |
|---|---|---|
| `/strategy/unified` 任一 engine 抛错 | HTTP 500，前端红错误条 | HTTP 200 + degraded payload，前端黄色 warning banner |
| `/strategy/unified` 整个 service 抛错 | HTTP 500 | HTTP 200 + 全 degraded payload，前端 degradedState |
| 4 endpoint 全部失败 | 红错误条（4/4 failed） | 黄 degradedState + auto-prewarm |
| 单个 endpoint 失败（unified 成功） | 黄色 warning banner（V1.7 已有） | 保持 + 新增 `degraded_components` 列表 |
| `degraded: true` payload | N/A | statusBanner 显示 "数据部分降级" |
| prewarm endpoint 失败 | N/A | fire-and-forget 静默失败，不影响页面渲染 |

## 6. Testing Strategy

### 6.1 单元测试（pytest）
- `tests/test_strategy_unified_degraded.py`（新增）：
  - Mock `UnifiedStrategyService.build_unified_strategy` 抛错 → endpoint 返回 200 + degraded
  - Mock 各 engine 抛错 → payload 含正确 `degraded_components`
  - Mock `/strategy/prewarm` 调用 → 验证 enqueue_hint 参数正确

- `tests/test_strategy_unified_api.py`（修改）：
  - 断言新字段默认值
  - 断言 degraded payload 形状

- `tests/test_market_context_builder.py`（修改）：
  - 断言 chip/macro/onchain 抛错时 get_context 仍返回 fallback

### 6.2 前端测试（Playwright + pytest）
- 新增 `tests/test_strategy_degraded_frontend.py`：
  - Mock `/strategy/unified` 返回 degraded payload → 验证 degradedState 渲染
  - 验证 prewarm endpoint 被调用（fire-and-forget）
  - 验证 console 无 error，页面无红色元素

### 6.3 端到端测试
- 冷启动 backend → 直接访问 `/strategy-page` → 验证：
  1. 页面立即渲染（无红错误条）
  2. 触发 prewarm 后台任务
  3. 30 秒后页面自动获得新鲜数据

## 7. Backward Compatibility

- ✅ 现有 `status="ready"` payload 不变
- ✅ 现有 `refresh_state` / `refresh_limitations` 字段不变
- ✅ 新字段全部 optional + 默认值，旧前端忽略新字段正常工作
- ✅ `StrategyUnifiedRead` schema `extra="allow"` 已存在，payload 可含未声明字段
- ✅ 不影响 monitoring / derivatives / macro 三个独立 endpoint

## 8. Files Affected

### 修改
- `trading-system-codex/app/api/v1/endpoints/strategy.py` — 加固 + 新增 `/strategy/prewarm`
- `trading-system-codex/app/services/market_context.py` — 三处 try/except 加固
- `trading-system-codex/app/services/strategy_unified/unified_service.py` — 每个 engine try/except
- `trading-system-codex/app/schemas/strategy_unified.py` — 新增 3 个 optional 字段
- `trading-system-codex/app/static/core/dom.js` — 新增 `degradedState()` helper
- `trading-system-codex/app/static/core/api.js` — 新增 `prewarmStrategy()` 方法
- `trading-system-codex/app/static/pages/strategy/index.js` — mount prewarm + 降级渲染
- `trading-system-codex/tests/test_strategy_unified_api.py` — 断言新字段

### 新增
- `trading-system-codex/tests/test_strategy_unified_degraded.py` — degraded 路径测试
- `trading-system-codex/tests/test_strategy_degraded_frontend.py` — 前端 Playwright 测试

## 9. Out of Scope

- 不修改 monitoring / derivatives / macro 三个独立 endpoint 的现有行为
- 不引入新的 precompute worker 调度策略（复用现有 `enqueue_hint` 机制）
- 不修改 `daily_first_page_prewarm` middleware（保持 V1.7 行为）
- 不实现前端轮询状态（保持 fire-and-forget）

## 10. Open Questions

None — design approved by user.