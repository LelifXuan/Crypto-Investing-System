# 跨品种跨周期机会扫描器 — 设计文档

**日期**: 2026-07-24  
**状态**: 已确认  
**范围**: AI 策略页改造 — 从被动单品种单级别推演 → 主动全品种全级别机会扫描

---

## 一、问题陈述

当前 AI 策略页存在两个核心缺陷：

1. **单时间帧盲区**：用户打开策略页默认看到某个级别（如 4H）的策略判定。如果 4H 判定"无交易机会"，用户看到的是空白/等待状态，不知道是否应该退到日线或周线去寻找机会。

2. **被动选币**：用户必须手动在下拉框切换 BTC/ETH/HYPE/BNB 等品种。系统不会主动告诉用户"当前 ETH 1d 有一个高置信度做空机会"。

**根因**：策略页是"查询式"交互（你问我答），而非"推送式"交互（系统告诉你哪里有机会）。

---

## 二、设计目标

将策略页从 **被动查询** 改为 **主动扫描 + 按需深入**：

- 打开策略页 → 自动扫描全部品种 × 核心级别的交易机会 → 矩阵概览 + 排序推荐
- 点击某个机会 → 右侧滑入该品种该级别的完整策略推演
- 后台每 15 分钟静默更新扫描结果（仅在数据发生足够变化时触发重算）
- 1H/15M 级别不参与扫描，仅作为侧拉详情中的"进出场点位优化"辅助数据

---

## 三、页面结构

### 3.1 布局方案：A+B 左右分栏

```
┌────────────────────── 机会扫描面板（默认视图）──────────────────────┐
│                                                                      │
│  ┌─── 左侧：机会矩阵 ───────┐  ┌─── 右侧：排序推荐列表 ──────────┐  │
│  │  品种  │ 1w │ 1d │ 4h  │  │  #1 BTC·1w 做多  72%  战略级   │  │
│  │  BTC   │ 🟢 │ 🟢 │ ⏸️  │  │  #2 BNB·1w 做多  70%  战略级   │  │
│  │  ETH   │ ⏸️ │ 🔴 │ 🔴  │  │  #3 ETH·1d 做空  61%  战术级   │  │
│  │  HYPE  │ ⏸️ │ ⏸️ │ 🟢  │  │  #4 BTC·1d 做多  68%  战术级   │  │
│  │  BNB   │ 🟢 │ ⏸️ │ ⏸️  │  │  ...                           │  │
│  │  OKB   │ ⏸️ │ ⏸️ │ ⏸️  │  │                                 │  │
│  └──────────────────────────┘  └─────────────────────────────────┘  │
│                                                                      │
│  ┌─── 侧拉详情面板（点击任意机会后从右侧滑入）───────────────────┐  │
│  │  ← 返回扫描  |  BTC · 1w · 做多 · 置信度 72%                  │  │
│  │  ┌─ 概览 ─┬─ 执行计划 ─┬─ 证据栈 ─┬─ 风控 ─┬─ 事件监控 ─┐   │  │
│  │  │  ...   │   ...     │   ...    │  ...   │   ...     │   │  │
│  │  └────────┴───────────┴──────────┴────────┴───────────┘   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 交互流

```
打开策略页 → 自动触发 GET /strategy/scan
    → 渲染矩阵 + 排序列表（默认视图）
    → 用户点击某个机会
        → 右侧滑入详情面板（复用现有 render* 模块）
        → 面板内调用 GET /strategy/unified?instrument=X&timeframe=Y
    → 用户点击「返回扫描」或点击矩阵中另一个机会
        → 详情面板切换内容（不关闭，仅更新）
    → 用户点击面板外部遮罩或关闭按钮
        → 面板关闭，回到扫描主视图
```

### 3.3 状态保持

- 详情面板打开时，用户切换到其他页面再切回来，面板保持打开状态（不丢失上下文）
- 扫描结果缓存 15 分钟，切回页面时如果缓存未过期则直接复用
- 手动刷新按钮始终可用

---

## 四、后端设计

### 4.1 新端点：`GET /api/v1/strategy/scan`

**无请求参数**（自动读取数据库中已配置的品种列表）。

**返回结构**：

```json
{
  "scanned_at": "2026-07-24T10:30:00Z",
  "instruments": ["btc-usdt-perp", "eth-usdt-perp", "hype-usdt-perp", "bnb-usdt-perp", "okb-usdt-perp"],
  "timeframes": ["1w", "1d", "4h"],
  "matrix": [
    {
      "instrument_id": "btc-usdt-perp",
      "instrument_code": "BTC",
      "timeframe": "1w",
      "direction": "LONG",
      "direction_label": "做多",
      "confidence": 72,
      "score": 85,
      "summary": "周线EMA多头排列 + 宏观顺风 + 衍生品无冲突",
      "risk_reward": 2.4,
      "leverage_hint": "spot",
      "position_cap": "standard",
      "primary_driver": "structure",
      "conflicts": []
    }
  ],
  "ranked": [ /* 同上，按 score 降序排列 */ ],
  "cache_meta": {
    "fresh_until": "2026-07-24T10:45:00Z",
    "source": "cache",
    "instruments_scanned": 5,
    "opportunities_found": 6
  }
}
```

### 4.2 综合评分公式

```
score = confidence       × 0.40   // 方向置信度 (0-100，直接来自 UnifiedStrategy)
      + risk_reward_norm × 0.25   // 盈亏比归一化 (min(rr/5, 1) × 100)
      + consistency      × 0.20   // 信号一致性 (多空信号同向=100, 混合=50, 矛盾=0)
      + timeframe_bonus  × 0.15   // 级别权重 (1w=100, 1d=70, 4h=40)
```

**信号一致性计算**：统计 DirectionResolution 中各模块信号的方向。如果技术/结构/衍生品/宏观四个模块中 ≥3 个同向 → 100；2个同向 → 50；≤1个同向或存在显式矛盾 → 0。

### 4.3 实现方式：复用 UnifiedStrategyService 的轻量路径

不重新实现策略计算。`OpportunityScanner` 调用 `UnifiedStrategyService.build_unified_strategy()` 的**轻量变体**：

- 跳过 `EvidenceTraceBuilder`（不需要完整证据栈）
- 跳过 `NarrativeRenderer`（不需要中文叙事）
- 跳过 `UnifiedTradePlanEngine`（不需要完整交易计划）
- 仅计算到 `DirectionResolutionResult` + `TradeDecision` 的摘要级别

这样单次扫描耗时约为完整 unified 的 40-50%，5品种 × 3级别 = 15 次约 3-5 秒。

### 4.4 缓存策略

- 扫描结果写入 `PageSnapshotCache`（`cache_key = "strategy_scan"`），TTL 15 分钟
- 15 分钟内重复请求直接返回缓存
- 传 `?force=true` 强制重新扫描
- 后台 precompute worker 在以下条件触发重新扫描：
  - 任一品种的 mark price 变化 > 2%（距上次扫描）
  - 任一品种的 OI 变化 > 5%
  - 用户手动点击"刷新扫描"

### 4.5 新服务文件

`app/services/strategy_unified/opportunity_scanner.py`

```python
class OpportunityScanner:
    def __init__(self, repository, unified_service_factory):
        ...

    async def scan_all(
        self,
        instrument_ids: list[str],
        timeframes: list[str] = ("1w", "1d", "4h"),
    ) -> ScanResult:
        """并行扫描所有品种×级别，聚合为 ScanResult"""
        ...

    def compute_score(self, result: DirectionResolutionResult) -> float:
        """综合评分"""
        ...
```

---

## 五、前端设计

### 5.1 新增文件

| 文件 | 职责 |
|---|---|
| `pages/strategy/renderScanMatrix.js` | 机会矩阵表格（品种×级别） |
| `pages/strategy/renderScanRanked.js` | 排序推荐列表（按 score 降序） |
| `pages/strategy/renderDetailPanel.js` | 侧拉详情面板（复用现有策略渲染模块） |

### 5.2 修改文件

| 文件 | 改动 |
|---|---|
| `pages/strategy/index.js` | 重写为扫描主页 + 面板切换逻辑 |
| `core/api.js` | + `getStrategyScan()` 方法 |

### 5.3 机会矩阵（renderScanMatrix.js）

5行（品种）× 3列（级别）表格。每个单元格：
- 🟢 绿色背景：LONG，显示置信度
- 🔴 红色背景：SHORT，显示置信度
- ⏸️ 灰色：WAIT / NO_TRADE
- 单元格可点击，点击后打开侧拉详情面板

### 5.4 排序推荐列表（renderScanRanked.js）

仅显示有方向（非 WAIT）的机会，按 score 降序排列。每行卡片：
- 品种 · 级别 · 方向（大字）
- 置信度 badge + score
- 一句话摘要（如"周线EMA多头排列 + 宏观顺风"）
- 级别标签（战略级/战术级/执行级）
- 杠杆提示（spot / 3x / 5x）
- 如果该品种已有持仓，标注"已有仓位"并降低透明度（提醒避免重复建仓）

### 5.5 侧拉详情面板（renderDetailPanel.js）

- 从右侧滑入，宽度约 55-60% 视口
- 顶部：返回按钮 + 面包屑（品种 · 级别 · 方向）
- 内容区：复用现有 `renderOverview`, `renderExecutionPlan`, `renderEvidenceStack`, `renderRiskPanel`, `renderEventWatch`
- 切换机会时：面板内容平滑更新（不关闭再打开）
- 关闭方式：点击返回按钮 / 点击面板外遮罩 / 按 Esc

---

## 六、数据流

```
┌─────────────┐     GET /strategy/scan      ┌──────────────────────┐
│  前端策略页  │ ──────────────────────────→  │  OpportunityScanner   │
│  index.js   │ ←────────────────────────── │  .scan_all()          │
└──────┬──────┘     ScanResult JSON          └──────┬───────────────┘
       │                                            │
       │ 渲染矩阵 + 排序列表                           │ 并行调用 15 次
       │                                            │ build_unified_strategy()
       │ 用户点击某个机会                              │ (轻量模式: 仅到 DirectionResolution)
       │                                            │
       │  GET /strategy/unified?                     │
       │  instrument=BTC&timeframe=1w                │
       │ ──────────────────────────────────────────→ │
       │ ←────────────────────────────────────────── │
       │  完整 UnifiedStrategy JSON                   │
       │                                            │
       │ 侧拉面板渲染（复用现有 render* 模块）            │
       │                                            │
       │ 1H/15M 数据作为进出场点位优化                    │
       │ (从 unified 的 trade_plan 中提取)              │
       │                                            │
└───────┴────────────────────────────────────────────┘
```

---

## 七、不做的事项

| 事项 | 原因 |
|---|---|
| 历史回测面板 | 需要完整回测引擎 + 历史数据管线，工作量过大，下期独立评估 |
| 15M 级别参与扫描 | 用户明确：15M/1H 仅作为详情中的进出场点位优化，不参与机会扫描 |
| 自动下单 | 属于执行模块，不在本次范围 |
| 1M 级别参与扫描 | 月线变化极慢，参与扫描意义不大 |
| 通知推送（浏览器 Notification） | 下期考虑，本次仅做页面内刷新提示 |

---

## 八、风险与已知约束

1. **扫描耗时**：15 次 UnifiedStrategy 轻量计算约 3-5 秒。首次打开策略页时用缓存 + skeleton 过渡，后台预热确保后续访问命中缓存。
2. **品种数量扩展**：当前 5 个品种，如果未来扩展到 10+，采用分批扫描 + 增量更新策略。当前阶段不需要。
3. **扫描与预计算 worker 的关系**：扫描缓存和 unified 缓存独立存储。扫描缓存失效时触发后台重扫，不阻塞页面渲染。
4. **侧拉面板与 SPA 路由**：面板状态不体现在 URL 中（不 pushState），切页时面板关闭。这是有意设计，保持路由简洁。
