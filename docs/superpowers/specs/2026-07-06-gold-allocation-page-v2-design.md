# 黄金配置页 V2 设计 (gold-allocation-page-v2)

> 状态：方案B（推荐方案）— 用户已批准
> 日期：2026-07-06
> 作者：ZCode + 用户
> 关联版本：v1.7.x 当前分支

## 1. 背景与动机

黄金配置页 (`app/static/pages/gold_allocation.js`, 468 行) 当前只渲染"执行层"（DCA + 加仓工作台），与其他信息密集型页面（BTC 衍生品 1051 行、技术分析 1465 行、形态结构 1240 行、监控 1192 行）相比复杂度明显偏低。

**根因**：
1. 前端只调用了 `POST /gold/execution-plan` 1 个 API
2. 后端已经有完整的多模块配置引擎 `app/services/gold_allocation_engine.py`（7 个加权模块、目标区间、推理步骤、风险提示）暴露在 3 个未启用的 API 中
3. `app/static/styles.css` 中存在 **37 个** `gold-page` / `gold-decision-header` / `gold-workbench-grid` / `gold-module-card` / `gold-evidence-layout` 等复杂版 CSS 类，但当前 JS 未启用

**机会**：后端 V2 引擎 + 复杂版 CSS 都已就绪，本次改造以**零后端改动**为约束，把"复杂度"对齐到 BTC 衍生品页的级别。

## 2. 目标

让黄金配置页从"执行表单"升级为"V2 配置工作台 + 执行子区块"，信息密度向 BTC 衍生品页对齐：

1. 用户进入页面后**先看到 V2 配置决策**（总评分 / 目标区间 / 状态 / 建议金额 / 主指令）
2. **7 个模块证据卡默认展开**，每个模块给出 score / confidence / data_quality / headline / facts / interpretation / warnings
3. **1-2 个趋势图表**（XAUT 价格回撤、央行净购金 / ETF 资金流）
4. **执行层（DCA + 加仓）保留为页内子区块**，不破坏用户日常操作

## 3. 非目标 (Out of Scope)

- 投资组合可调输入面板（方案 C 内容，留给后续单独 brainstorm）
- 后端 V2 引擎调整 / 新增 API
- 新增或修改 CSS 类（**完全复用现有 ~37 个未启用的类**）
- 移动端响应式（沿用现有 shell 框架）
- 多语言
- 暗色模式微调

## 4. 架构

### 4.1 数据流

```
Page load
  ↓
  GET  /gold/allocation  (portfolio 默认值) → 渲染 V2 决策带 + 7 模块卡
  GET  /gold/fundamentals → 渲染基本面小面板
  GET  /gold/market-state → 渲染 XAUT 卡片 + 提供图表数据
  POST /gold/execution-plan (本地表单 state) → 渲染执行子区块

用户调整执行表单（dailyDcaAmount 等）→ debounce 450ms → 重调 POST /gold/execution-plan（不影响 V2 层）
用户点击「刷新基本面」→ 重调 GET /gold/fundamentals
用户点击「刷新 V2 配置」→ 重调 GET /gold/allocation
```

### 4.2 状态

```javascript
let latestAllocation = null;   // /gold/allocation 响应
let latestFundamentals = null; // /gold/fundamentals 响应
let latestMarket = null;       // /gold/market-state 响应
let latestPlan = null;         // /gold/execution-plan 响应
// 既有：localStorage 状态、controller、debounceTimer 保留
```

### 4.3 页面布局（沿用 BTC 衍生品页式）

```
┌────────────────────────────────────────────────────────────┐
│  Hero: 黄金配置 V2 工作台       [刷新 V2] [刷新基本面]      │
│  eyebrow: GOLD ALLOCATION                                    │
│  副标题: 多模块加权评分 + 长期目标区间 + 执行工作台          │
├────────────────────────────────────────────────────────────┤
│  V2 决策带 (.gold-decision-header)                           │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┐    │
│  │总评分  │目标区间│当前权重 │ 状态  │建议金额│主指令  │    │
│  └────────┴────────┴────────┴────────┴────────┴────────┘    │
│  推理步骤 (.gold-decision-metrics)  + 风险提示 (warnings)   │
├────────────────────────────────────────────────────────────┤
│  趋势图表 (1-2 张) — 复用 renderChart()                     │
│  XAUT 30日价格 + 60日回撤线 | 央行净购金 12m vs 3m           │
├────────────────────────────────────────────────────────────┤
│  7 个模块卡 (.gold-module-card 网格)                          │
│  宏观货币 / 官方储备 / 供给刚性 / 组合对冲 / 流动性 / 衍生品 │
│  / XAUT  — 默认全部展开                                      │
│  每卡：headline + facts[] + interpretation + warnings +     │
│        data_quality chip + score 仪表                        │
├────────────────────────────────────────────────────────────┤
│  基本面快照 (.gold-market-panel) — 来自 /gold/fundamentals  │
│  央行净购金 | ETF 资金流 | 期货 OI | COT 净多 | 供给平衡     │
├────────────────────────────────────────────────────────────┤
│  已有：XAUT 代理行情 + 代数化执行策略 (黄金坑)               │
├────────────────────────────────────────────────────────────┤
│  已有：执行子区块（参数表单 + 系统诊断）                     │
└────────────────────────────────────────────────────────────┘
```

### 4.4 CSS 类映射（既有、不新增）

| 区块 | 既有类 | 来源 |
| --- | --- | --- |
| V2 决策带 | `.gold-decision-header`, `.gold-decision-metrics`, `.gold-primary-instruction` | styles.css 7885-7935 |
| 模块卡 | `.gold-module-card`, `.gold-module-head`, `.gold-module-card.is-secondary` | 8014-8050 |
| 工作台布局 | `.gold-workbench-grid`, `.gold-left-stack`, `.gold-right-stack` | 7892-7901 |
| 证据布局 | `.gold-evidence-layout`, `.gold-evidence-primary`, `.gold-evidence-secondary`, `.gold-driver-section` | 7941-7963 |
| 行情卡 | `.gold-market-panel`, `.gold-market-head`, `.gold-market-values`, `.gold-window-grid` | 7965-8013 |
| 诊断 | `.gold-diagnostics-card` | 7880 |
| 既有执行区 | `.gold-v3-*`, `.gold-formula-*`, `.gold-execution-*` | 8158+ 保留 |

### 4.5 模块卡渲染规范

每个模块从 `allocation.drivers[<key>]` 取（`build_gold_allocation_plan.drivers` 已是 dict）。

```javascript
function renderModuleCard(card) {
  // card: {key, title, score, confidence, state, data_quality, headline, facts, interpretation, warnings, window_views, allocation_effect}
  return `
    <article class="gold-module-card" data-module="${card.key}">
      <header class="gold-module-head">
        <h3>${card.title}</h3>
        <span class="chip chip--${card.state}">${stateLabel(card.state)}</span>
      </header>
      <div class="gold-module-score">
        <b>${card.score}</b>
        <small>置信度 ${(card.confidence * 100).toFixed(0)}% · ${qualityLabel(card.data_quality)}</small>
      </div>
      <p class="gold-module-headline">${card.headline}</p>
      <ul class="gold-module-facts">
        ${card.facts.map(f => `<li>${f}</li>`).join('')}
      </ul>
      <details class="gold-module-detail">
        <summary>解读与窗口</summary>
        <p>${card.interpretation}</p>
        ${renderWindowViews(card.window_views)}
        ${card.warnings.length ? `<ul class="gold-module-warnings">${card.warnings.map(w => `<li>${w}</li>`).join('')}</ul>` : ''}
      </details>
    </article>
  `;
}
```

`state` → 中文标签映射：
- `supportive` / `strong_support` → 支撑
- `headwind` / `tight` / `selloff_watch` / `crowded` / `volatile` → 风险
- `neutral` / `normal` / `loose` / `low_hedge_need` / `moderate_hedge_need` / `high_hedge_need` / `watch` / `missing` → 中性 / 缺失

### 4.6 趋势图表

#### 图 1: XAUT 关键指标快照（单点 + 变化）
- **数据源**: `/gold/market-state` 返回的 `price` / `ret_1d` / `ret_7d` / `ret_30d` / `drawdown_60d` / `natr_14` / `above_ma50` / `above_ma200`
- **类型**: 横向条形图 — 7D / 30D 变化 + 60D 回撤
- **颜色**: 正值 `#0f766e`，负值 `#c35a1d`
- **空状态**: 任一字段缺失时显示「XAUT 关键指标待刷新」占位
- **说明**: `/gold/market-state` 当前仅返回当期值，不返回时序；本图展示"变化幅度"代替"价格走势"，避免在前端编造历史数据。后续若后端提供时序再升级为折线图。

#### 图 2: 央行净购金 12m vs 3m + ETF 1m
- **数据源**: `/gold/fundamentals` → `central_bank_net_purchase_tonnes_12m` / `_3m` / `gold_etf_flow_tonnes_1m`
- **类型**: 双条形图（仅 2-3 根柱，最简）
- **空状态**: 任一字段缺失时回退为单柱

> **降级原则**：时间序列若不存在，不要在前端编造；改为「当期值 + 同环比变化」的简化展示。

## 5. 错误处理

| 场景 | 行为 |
| --- | --- |
| `/gold/allocation` 401/403 | 显示 hero 下方 banner「配置层需登录」，保留执行层 |
| `/gold/allocation` 500/超时 | 红色 banner + 保留执行层 + 「重试」按钮 |
| `/gold/fundamentals` 失败 | 基本面快照区显示「基本面待刷新」占位，不影响其他区 |
| `/gold/market-state` 失败 | XAUT 卡显示占位 + 执行层 quote_state = "stale" |
| `/gold/execution-plan` 失败 | 既有路径已有 `statusBanner("error")` 行为，保留 |
| 控制器 abort | 沿用现有 `controller.abort()` 模式 |

## 6. 测试

### 6.1 前端静态测试（既有 `test_gold_frontend_static.py` 增强）

新增断言：
- V2 决策带类 `gold-decision-header` 出现在 DOM
- 7 个 `data-module` 属性（macro_monetary_environment / official_reserve_demand / supply_rigidity / portfolio_hedging_need / liquidity_selloff_rebound / derivatives_pressure / xaut_price_state）
- 趋势图表容器存在
- 既有执行子区块断言保留

### 6.2 现有测试

- `test_gold_allocation_api.py` — 验证 `GET /gold/allocation` 仍返回兼容 schema（不需改）
- `test_gold_allocation_engine.py` — 后端不动
- `test_gold_frontend_static.py` — 扩展断言（见 6.1）

### 6.3 手动验证

- 登录态/未登录态均能进入页（未登录时 V2 决策带显示登录提示，不影响执行层）
- 调整执行表单参数 → 450ms 后执行层刷新，V2 层不变
- 浏览器 DevTools 检查：网络请求 4 个 endpoint，状态码 2xx
- Chart.js 实例化无控制台错误

## 7. 文件改动清单

| 文件 | 改动 |
| --- | --- |
| `app/static/pages/gold_allocation.js` | 重写：从 468 → ~1100-1200 行；新增 V2 决策带 / 7 模块卡 / 趋势图 / 基本面板 |
| `tests/test_gold_frontend_static.py` | 新增断言（V2 决策带 + 7 模块 data-module + 图表容器） |
| `CHANGELOG.md` | 新增条目 |
| `docs/superpowers/specs/2026-07-06-gold-allocation-page-v2-design.md` | 本文档 |

**不改动的文件**：
- `app/services/gold_allocation_engine.py`（后端）
- `app/services/gold_dca_dip.py`
- `app/services/gold_macro_adapter.py`
- `app/services/goldhub_data.py`
- `app/schemas/gold_allocation.py`
- `app/api/v1/endpoints/gold.py`
- `app/static/styles.css`（**完全复用现有未启用类**）

## 8. 实施风险与回滚

**风险**：
- 7 个模块的 `facts` / `warnings` 字符串可能包含后端尚未填实的占位（如 "宏观证据暂未完整返回"）— 接受现状，按既有行为展示
- 复用既有 CSS 类时若发现类名细节与新 HTML 结构不完全匹配 → 用最小组装（`section-head compact` + 现有 `.gold-module-card` 内部结构）解决，不新增 CSS

**回滚**：单文件 `git revert` 即可，不动后端。

## 9. 后续 (Follow-up)

- 投资组合可调输入面板（方案 C）
- 把"基本面快照"升级为带时序趋势的完整面板
- 把 `/gold/allocation` 与 `/gold/market-state` 的 30s 轮询改为前端定时器
