# 黄金配置页 V2 设计 (gold-allocation-page-v2)

> 状态：方案B（推荐方案）— 用户已批准
> 日期：2026-07-06（初版）/ 2026-07-07（V2 修订：多空标签 + 宏观指标 + 设计语言）
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

## 2.1 修订动因（2026-07-07）

初版 spec 完成后，用户对实际页面截图提出 3 个具体反馈，本节专门纳入：

| 反馈 | 现状问题 | 修订方向 |
|---|---|---|
| **① 标签语义错位** | 核心/派生指标卡右上角显示"可用/偏低/偏高"——这是**数据状态**（值是否在阈值内），用户期望看到的是**多空判断**（市场方向） | 后端 `_status_for_value()` 增加 `bias` 字段，前端渲染**5 档多空标签**：强势看多 / 看多 / 中性 / 看空 / 强势看空 |
| **② 缺失宏观指标** | 黄金作为宏观资产，但页面完全没有实际利率(TIPS yield)、DXY、CPI 同比、VIX 这些直接影响黄金价格的因素 | 新增**4 个核心宏观指标卡**（real_yield_10y / DXY / CPI YoY / VIX），复用后端 `MacroOverviewService` 已有数据（不需新增后端逻辑） |
| **③ 设计语言不统一** | 当前 `.gold-v3-*` 视觉密度比 BTC 衍生品页低 ~70%（信息单元 15 vs 50+）；chip 仅单色，无 bottom-group 二级容器，无状态色调，叙事层级浅 | 全页改用 **BTC 衍生品页式 9 段递进**：Hero 决策带 → 工具栏 → 关键价位 → 图表 → 证据层 → 配置/执行 → 明细 → 治理。chip 改 4 色变量（bullish/bearish/warning/accent），新增 `.gold-bottom-group` 二级容器 |

修订范围：
- **后端**：扩展 `_indicator_card()` 输出多空语义字段；`_macro_card()` 在响应顶层新增 `gold_macro_snapshot`（4 指标原始值 + bias）
- **前端**：重写 `gold_allocation.js`（468 → ~1100-1300 行）；启用既有 24 个 `.gold-*` 类 + 新增 4 个二级容器/状态色类
- **设计语言**：完全沿用 BTC 衍生品页的 9 段递进叙事

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

### 4.3 页面布局（沿用 BTC 衍生品页式 9 段递进）

> **设计原则**：完全贴齐 BTC 衍生品页的视觉密度与叙事层级。9 段递进（hero 决策 → 数据图表 → 推断块 → 工具规划 → 数据治理），而非初版的 4 段并列。

```
┌─────────────────────────────────────────────────────────────────┐
│ ① Hero (.gold-v3-hero, 类比 .btc-derivatives-hero)             │
│   eyebrow: GOLD ALLOCATION V2                                   │
│   h1: 黄金宏观与配置工作台                                       │
│   副文: 多模块加权评分 + 宏观信号 + 长期目标区间 + 执行计划       │
│   右侧: [状态 pill: bullish/bearish/neutral] + [刷新 V2] + freshness│
├─────────────────────────────────────────────────────────────────┤
│ ② 决策带 (.gold-decision-grid, 类比 .btc-decision-grid)         │
│   3 张 decision card (min-height 230px):                         │
│   - 宏观环境 (.gold-decision-card[data-tone="bullish"])         │
│       结论 + 置信度 + 5 张 evidence-chip (实际利率/DXY/CPI/VIX/...) │
│   - 配置建议 (.gold-decision-card[data-tone="..."])             │
│       目标区间 + 低/达标/超配 + 月度动作                          │
│   - 执行计划 (.gold-decision-card[data-tone="..."])             │
│       今日 DCA + 黄金坑状态 + 冷却中/触发中/就绪                  │
├─────────────────────────────────────────────────────────────────┤
│ ③ 4 个核心宏观指标 (.gold-macro-strip, 类比 .btc-level-strip)   │
│   4 张 .gold-macro-card (min-height 220px):                     │
│   ┌────────────┬────────────┬────────────┬────────────┐         │
│   │ 实际利率    │ DXY        │ CPI YoY    │ VIX        │         │
│   │ (TIPS yield)│ 美元指数   │ 美国CPI    │ 波动率     │         │
│   │ 1.85%      │ 103.5      │ 2.7%       │ 18.4       │         │
│   │ [看多]     │ [看空]     │ [中性]     │ [中性]     │         │
│   │ 实际利率   │ 美元指数    │ 美国CPI    │ 波动率     │         │
│   │ 距离 4W: -│ vs 4W: -   │ 距离上期:  │ 当前档位:  │         │
│   └────────────┴────────────┴────────────┴────────────┘         │
├─────────────────────────────────────────────────────────────────┤
│ ④ 7 模块证据卡 (.gold-module-section, 类比 .btc-inference-grid) │
│   每张 article (data-tone):                                     │
│   - 宏观货币 | 官方储备 | 供给刚性 | 组合对冲 | 流动性 | 衍生品 | XAUT │
│   - 每卡: score + confidence + data_quality + 5 个 evidence-chip │
├─────────────────────────────────────────────────────────────────┤
│ ⑤ 图表区 (.gold-chart-sections)                                │
│   2 张图:                                                        │
│   - XAUT 关键指标 (7D/30D/60D 回撤 + NATR, 类比 .btc-chart-card)│
│   - 基本面快照 (央行净购金 12m vs 3m, ETF 1m, 类比 .btc-chart-card)│
├─────────────────────────────────────────────────────────────────┤
│ ⑥ XAUT 代理行情 + 黄金坑结构 (.gold-bottom-group, 类比 .btc-bottom-group)│
│   - 左侧: .gold-market-panel (XAUT 价格 + 7D/30D)               │
│   - 右侧: .gold-strategy-panel (代数化公式 + n×x + 触发条件)     │
├─────────────────────────────────────────────────────────────────┤
│ ⑦ 执行子区块 (.gold-bottom-group)                              │
│   - 左: .gold-settings-card (本地参数表单)                      │
│   - 右: .gold-system-card (K 线/指标/诊断)                      │
├─────────────────────────────────────────────────────────────────┤
│ ⑧ 核心 + 派生指标卡 (.gold-indicator-layout)                  │
│   2 张 section × 4-8 张 indicator card, 每卡右上角改为          │
│   "强势看多/看多/中性/看空/强势看空" 5 档多空标签                │
├─────────────────────────────────────────────────────────────────┤
│ ⑨ 数据治理 (.gold-bottom-group, 折叠 .gold-details-drawer)    │
│   - 报价状态 + K 线数量 + 缺失字段 + 数据源健康                  │
│   - 类比 .btc-quality-details / .btc-method-notes 折叠面板       │
└─────────────────────────────────────────────────────────────────┘
```

**叙事递进（9 段）**：
1. **状态**（Hero） — 一句话告诉你现在怎样
2. **结论**（决策带 3 卡） — 宏观/配置/执行三件事的判定
3. **输入**（4 个宏观） — 影响宏观结论的 4 个原始信号
4. **证据**（7 模块） — 长期配置的 7 维拆解
5. **数据**（图表） — 趋势与历史
6. **结构**（XAUT + 黄金坑） — 当下行情 + 触发结构
7. **执行**（执行子区块） — 日常纪律
8. **细节**（核心/派生指标） — 单点深度
9. **治理**（数据健康） — 可信度

对比初版的 4 段并列：信息单元从 15 → ~50；叙事从"分块堆叠" → "由浅入深"。

### 4.4 CSS 类映射（既有 + 复用 + 新增）

#### A. 启用既有未用的 24 个 `.gold-*` 类（来自初版 spec，本轮未变）

| 区块 | 既有类 | 来源 |
| --- | --- | --- |
| V2 决策带 | `.gold-decision-header`, `.gold-decision-metrics`, `.gold-primary-instruction` | styles.css 7885-7935 |
| 模块卡 | `.gold-module-card`, `.gold-module-head`, `.gold-module-card.is-secondary` | 8014-8050 |
| 工作台布局 | `.gold-workbench-grid`, `.gold-left-stack`, `.gold-right-stack` | 7892-7901 |
| 证据布局 | `.gold-evidence-layout`, `.gold-evidence-primary`, `.gold-evidence-secondary`, `.gold-driver-section` | 7941-7963 |
| 行情卡 | `.gold-market-panel`, `.gold-market-head`, `.gold-market-values`, `.gold-window-grid` | 7965-8013 |
| 诊断 | `.gold-diagnostics-card` | 7880 |
| 既有执行区（保留） | `.gold-v3-*`, `.gold-formula-*`, `.gold-execution-*` | 8158+ |

#### B. 复用 BTC 衍生品页既有 `.btc-*` 设计模式（前端样式约定）
- `data-state="bullish|bearish|neutral"` / `data-tone` 属性驱动 chip 颜色
- 4 色变量（继承 BTC 既有定义，**不新增 CSS 变量**）：`--bullish #0f766e` / `--bearish #c35a1d` / `--warning #b7791f` / `--accent #0f766e`
- `.btc-bottom-group` 二级容器模式（圆角 18 / 阴影 / 半透明白底）
- `.btc-evidence-chip` / `.btc-chart-insight` 小标签
- `.btc-warning` 左侧 3px 警告边条
- `.btc-details-drawer` 折叠面板

#### C. 新增 4 个黄金页专用 CSS 类（**新增行 ≤ 30**）

| 新增类 | 用途 | 行数估计 |
|---|---|---|
| `.gold-bottom-group` | 二级容器（圆角 18 + 阴影 + 半透明白底） | 6 行 |
| `.gold-decision-grid` | 3 列决策带网格 | 4 行 |
| `.gold-decision-card` | 单个决策卡（min-height 230px） | 8 行 |
| `.gold-macro-strip` | 4 列宏观指标条 | 4 行 |
| `.gold-macro-card` | 单个宏观卡（min-height 220px） | 8 行 |
| `.gold-bias-strong-bullish` / `.gold-bias-bullish` / `.gold-bias-neutral` / `.gold-bias-bearish` / `.gold-bias-strong-bearish` | 5 档多空 chip 颜色（5 × 6 行） | 30 行 |
| `.gold-warning` | 左侧 3px 警告边条（复用 BTC 模式） | 6 行 |

**总计新增 ≤ 70 行**。其余视觉完全沿用 BTC 既有 `.btc-*` 变量与样式。

### 4.5 模块卡渲染规范（强化多空标签）

每个模块从 `allocation.drivers[<key>]` 取（`build_gold_allocation_plan.drivers` 已是 dict）。

#### 4.5.1 后端改造：`_indicator_card()` 增加 `bias` 字段

`app/services/gold_dca_dip.py:332-339` 现有 `_status_for_value()` 返回数据语义：
```python
def _status_for_value(value, *, lower=None, upper=None) -> str:
    if value is None: return "数据不足"
    if lower is not None and value <= lower: return "偏低"
    if upper is not None and value >= upper: return "偏高"
    return "可用"
```

**改造**：拆为两个并行函数：

```python
def _status_for_value(value, *, lower=None, upper=None) -> str:
    """数据语义（保留旧字段给 diagnostic 使用）"""
    # 现有逻辑

def _bias_for_indicator(key: str, value: float | None, *, lower=None, upper=None) -> str:
    """多空语义（5 档：strong_bullish / bullish / neutral / bearish / strong_bearish）

    判定规则：
    - value 为 None → missing
    - 指标不在 bullish_low/bearish_low 集合内 → neutral（默认中性）
    - bullish_low 集合（越低越看多黄金）：
      rsi_14 / cci_20 / percent_b
    - bearish_low 集合（越低越看空黄金）：
      close_vs_ema20_pct / close_vs_ema50_pct / return_7d / return_14d /
      drawdown_from_30d_high / drawdown_from_60d_high
    - 无阈值（lower=None and upper=None）→ neutral
    - 强档阈值：lower*0.7 / upper*1.3
    """
    if value is None: return "missing"
    bullish_low = {"rsi_14", "cci_20", "percent_b"}
    bearish_low = {"close_vs_ema20_pct", "close_vs_ema50_pct", "return_7d", "return_14d",
                   "drawdown_from_30d_high", "drawdown_from_60d_high"}
    if lower is None and upper is None: return "neutral"
    if key in bullish_low:
        if lower is not None and value <= lower * 0.7: return "strong_bullish"
        if lower is not None and value <= lower: return "bullish"
        if upper is not None and value >= upper * 1.3: return "strong_bearish"
        if upper is not None and value >= upper: return "bearish"
        return "neutral"
    if key in bearish_low:
        if lower is not None and value <= lower * 0.7: return "strong_bearish"
        if lower is not None and value <= lower: return "bearish"
        if upper is not None and value >= upper * 1.3: return "strong_bullish"
        if upper is not None and value >= upper: return "bullish"
        return "neutral"
    return "neutral"
```

**关键约束**：
- `ema_20 / ema_50 / ema_200 / atr_14 / natr_14` 等**无方向语义的指标** → **统一返回 `neutral`**，不参与多空判断（这些指标仅作为"技术状态"展示，不映射多空）
- 实际有方向语义的指标共 9 个：`rsi_14 / cci_20 / percent_b` + 6 个 bearish_low
- `natr_14` 不在 bullish_low（先前误列已删除；NATR 越高波动越大，但对黄金无明确方向语义，留 neutral）

`_indicator_card()` 输出新增 `bias` 字段：
```python
return {
    "key": key, "label": label, "value": value,
    "display_value": _format_card_value(value, unit, digits),
    "unit": unit,
    "status": _status_for_value(value, lower=lower, upper=upper),  # 数据语义（保留）
    "bias": _bias_for_indicator(key, value, lower=lower, upper=upper),  # 多空语义（新增）
    "note": note,
}
```

#### 4.5.2 前端映射（5 档 → 中文标签 + CSS 类）

| `bias` 字段 | 中文标签 | CSS 类 | 颜色变量 |
|---|---|---|---|
| `strong_bullish` | 强势看多 | `.gold-bias-strong-bullish` | `--bullish-strong` (待定) |
| `bullish` | 看多 | `.gold-bias-bullish` | `--bullish` |
| `neutral` | 中性 | `.gold-bias-neutral` | `--muted` |
| `bearish` | 看空 | `.gold-bias-bearish` | `--bearish` |
| `strong_bearish` | 强势看空 | `.gold-bias-strong-bearish` | `--bearish-strong` (待定) |
| `missing` | 数据不足 | `.gold-bias-missing` | `--warning` |

#### 4.5.3 `renderIndicatorCard` 修改

```javascript
function renderIndicatorCard(card) {
  return `
    <article class="gold-indicator-card" data-bias="${card.bias}">
      <div>
        <strong>${escapeHtml(card.label || "指标")}</strong>
        <span class="gold-bias-chip gold-bias-${escapeHtml(card.bias)}">${biasLabel(card.bias)}</span>
      </div>
      <b>${escapeHtml(card.display_value || "-")}</b>
      <small>${escapeHtml(card.note || "")}</small>
    </article>
  `;
}

function biasLabel(bias) {
  return {
    strong_bullish: "强势看多",
    bullish: "看多",
    neutral: "中性",
    bearish: "看空",
    strong_bearish: "强势看空",
    missing: "数据不足",
  }[bias] || "中性";
}
```

### 4.6 4 个核心宏观指标（新增段落）

#### 4.6.1 后端暴露：`gold_macro_snapshot`

`/gold/allocation` 端点（`gold.py:174-193`）目前已经调用 `_macro_payload(repo)` 但**不暴露 layer_map 给前端**。

**改造**：`app/services/gold_allocation_engine.py` 的 `AllocationPlan.to_dict()` 或 `build_gold_allocation_plan()` 返回值新增字段：

```python
gold_macro_snapshot = {
    "real_yield_10y": {
        "value": 1.85,           # 从 macro.layer_map.cross_asset_confirmation.indicators[?].key="real_yield_5y"
        "unit": "%",
        "display_label": "美国10年期实际利率 (TIPS yield)",
        "source": "fred",
        "observation_ts": "2026-07-05",
        "delta_4w": -0.12,
        "bias": "bearish",        # 黄金视角多空语义
        "bias_reason": "实际利率 1.85% 处于中性区间，但方向中性偏空",
        "threshold_low": 0.5,
        "threshold_high": 2.8,
        "status": "ok",
    },
    "dxy": { "value": 103.5, "unit": "index", "display_label": "美元指数DXY", ... },
    "cpi_yoy": { "value": 2.7, "unit": "%", "display_label": "美国CPI同比", ... },
    "vix": { "value": 18.4, "unit": "index", "display_label": "VIX波动率", ... },
}
```

**改造点**：
- `gold_allocation_engine.py:1073-1090` 返回 `AllocationPlan` 时追加 `gold_macro_snapshot` 字段
- `gold_macro_adapter.py:104-170` 的 `macro_overview_to_gold_macro()` 新增 `_gold_macro_snapshot()` 函数
- **指标命名修正**：黄金配置页用 `real_yield_10y`（10 年期 TIPS yield），不是 `real_yield_5y`。语义上是"通胀调整后的实际利率"，是黄金机会成本的核心代理。系统里不叫 "TIPS"，因为 TIPS 是资产本身，实际参与判断的是 yield/利率水平。
- 阈值 low/high 仍取 `macro_scoring_registry.v1.json`（real_yield_5y 条目）— 5Y/10Y 在判断黄金方向上结论一致（实际利率越高越压制黄金），阈值可比但需在 spec 中显式声明。

#### 4.6.2 黄金视角 vs 风险资产视角的方向关系（用户专业修正）

**核心结论表**：

| 指标 | 风险资产视角 | 黄金视角 | 方向关系 |
|---|---|---|---|
| **real_yield_10y** (TIPS yield) | 上升压制风险资产估值 | **上升提高黄金机会成本，压制黄金**（黄金不产生利息，实际利率越高，债券等有息资产吸引力越强，黄金相对吸引力下降） | **一致偏空** |
| **DXY** | 美元走强代表流动性收紧，压制风险资产 | **美元走强通常压制美元计价黄金**（World Gold Council 把美元和债券收益率列为黄金"机会成本"驱动） | **一致偏空**（**危机例外**：若 DXY 上行来自全球避险/美元荒且 VIX 急升，黄金短期先受流动性抛售压制，后看避险买盘是否回流） |
| **CPI YoY** | 上升通常提高紧缩预期，压制风险资产 | **不固定**：取决于实际利率 — 实际利率下行偏多，实际利率上行偏空 | **不固定**（CPI × RealYield × DXY 二维判断） |
| **VIX** | 上升代表风险厌恶，压制风险资产 | **正常风险厌恶支持黄金（反向）**；**流动性冲击下先不直接看多**（VIX 急升 + DXY 急升 + RealYield 上行 = 卖流动性补保证金） | **通常反向**（**流动性冲击例外**） |

#### 4.6.3 阈值与判断函数

**阈值来源说明**：4 个指标的 `low/high` 阈值（0.5/2.8, 98/108, 2/5, 15/28）**直接来自项目自有配置 `app/monitoring/configs/macro_scoring_registry.v1.json`** — 这是项目官方已经在 `macro/scoring_engine.py` 使用的评分阈值。spec 不引入新数字。

**关键事实**：配置里 `higher_value_bias="bearish_for_risk_assets"` 是**针对风险资产**视角。黄金作为反风险资产，**4 个指标中 2 个需要反转方向判断**：

| 指标 | registry 方向（风险资产） | 黄金方向 | 处理 |
|---|---|---|---|
| real_yield_10y | high = bearish_for_risk_assets | high = bearish_for_gold | **一致**，直接用阈值 |
| DXY | high = bearish_for_risk_assets | high = bearish_for_gold | **一致**，直接用阈值 |
| CPI YoY | high = bearish_for_risk_assets | **不固定**（取决于 real_yield + DXY） | **二维判断表**（见下） |
| VIX | high = bearish_for_risk_assets | **反向**（正常避险）+ 例外（流动性冲击） | **反转阈值 + 状态机判断** |

#### 4.6.4 CPI 二维判断表（黄金视角）

CPI 不是单调函数。CPI 与 RealYield、DXY 组合产生不同判断：

| CPI 状态 | RealYield | DXY | 黄金判断 | 备注 |
|---|---|---|---|---|
| CPI 上行，Fed 被动落后 | **下行** | **不强** | **看多黄金** | 通胀利好 + 利率压力小 + 美元不强势 |
| CPI 上行，市场定价更高利率 | **上行** | **上行** | **看空黄金** | 紧缩预期 + 实际利率上行 + 美元走强 |
| CPI 温和回落，降息预期增强 | **下行** | **走弱** | **看多黄金** | 降息预期利好 |
| CPI 快速下行，衰退风险升温 | 不确定 | 可能上行 | **等待 VIX / DXY / ETF 确认** | 不输出单方向 bias |

**实现**：CPI 的 bias 输出 `bullish/bearish/neutral` 三档 + `bias_reason` 字段说明判断依据；不输出 5 档（强档留给单指标）。

#### 4.6.5 VIX 状态机判断（黄金视角）

| VIX 状态 | 其他条件 | 黄金判断 |
|---|---|---|
| VIX 温和上升 (15-22) | 任意 | **看多黄金**（避险属性增强） |
| VIX 急升 (>28) | DXY 不强 + RealYield 不上行 | **强势看多黄金** |
| VIX 急升 (>28) | DXY 急升 + RealYield 上行 | **流动性冲击模式：先看空（黄金被卖补保证金），待压力缓和后回到避险逻辑** |
| VIX 低 (<15) | 任意 | 中性 / 看空（无避险需求） |

#### 4.6.6 DXY 危机例外

| DXY 状态 | 其他条件 | 黄金判断 |
|---|---|---|
| DXY 走强（>105） | VIX 平稳 | **看空黄金** |
| DXY 走强（>105） | VIX 急升（>25）+ RealYield 上行 | **流动性冲击模式：先看空黄金**（美元荒） |
| DXY 走强（>105） | VIX 急升但 RealYield 下行 | **不一致**：黄金短期受压制，但若美元压力缓和后回流避险买盘，重新评估 |

#### 4.6.7 完整判断函数

```python
def _gold_macro_snapshot(macro: dict) -> dict:
    """从 macro layer_map 提取 4 个核心宏观指标 + 计算黄金视角的多空 bias。
    
    重要：以下 bias 计算**仅针对黄金视角**，不复用 registry 的 risk-assets bias。
    
    阈值来源: app/monitoring/configs/macro_scoring_registry.v1.json
    方向重写: 本 spec 4.6.2-4.6.6 节定义
    """
    layer_map = (macro or {}).get("layer_map") or {}
    indicators_by_layer = {
        layer["layer_key"]: layer.get("indicators", [])
        for layer in (macro or {}).get("layers", [])
        if isinstance(layer, dict)
    }
    flat_indicators = [ind for ind_list in indicators_by_layer.values() for ind in ind_list]

    def find(indicator_key: str) -> dict | None:
        for ind in flat_indicators:
            if ind.get("indicator_key") == indicator_key:
                return ind
        return None

    # === 指标取值 ===
    real_yield = find("real_yield_5y") or find("real_yield_10y")  # 优先 10Y；fallback 5Y
    dxy = find("dxy") or find("dollar_index")
    cpi = find("cpi_yoy")
    vix = find("vix")

    def value_of(ind: dict | None) -> float | None:
        return ind.get("value_num") if ind else None

    ry_val = value_of(real_yield)
    dxy_val = value_of(dxy)
    cpi_val = value_of(cpi)
    vix_val = value_of(vix)

    # === 流动性冲击检测（VIX 急升 + DXY 急升 + RealYield 上行） ===
    # 用于修正 VIX/DXY 在危机阶段的方向判断
    liquidity_shock = (
        vix_val is not None and vix_val >= 25 and
        dxy_val is not None and dxy_val >= 105 and
        ry_val is not None and ry_val >= 2.0
    )

    # === real_yield_10y 方向: high = bearish_for_gold (一致) ===
    def bias_for_real_yield(value):
        if value is None: return ("missing", "数据不足")
        # 阈值: low=0.5, high=2.8 (from registry real_yield_5y)
        if value <= 0.5: return ("strong_bullish", "实际利率低于 0.5%，持有黄金机会成本极低，强烈支持黄金")
        if value <= 1.5: return ("bullish", "实际利率处于低位，债券吸引力弱，利好黄金")
        if value >= 2.8: return ("strong_bearish", "实际利率高于 2.8%，持有黄金机会成本高，强烈压制黄金")
        if value >= 2.0: return ("bearish", "实际利率偏高，债券吸引力上升，压制黄金")
        return ("neutral", "实际利率处于中性区间")

    # === DXY 方向: high = bearish_for_gold (一致 + 危机例外) ===
    def bias_for_dxy(value):
        if value is None: return ("missing", "数据不足")
        if liquidity_shock:
            return ("bearish", "DXY 走强叠加 VIX 急升，流动性冲击模式：黄金短期先被卖补保证金")
        if value <= 98: return ("strong_bullish", "美元指数极弱，黄金 USD 计价上涨空间打开")
        if value <= 102: return ("bullish", "美元偏弱，支撑黄金")
        if value >= 108: return ("strong_bearish", "美元极强，强势压制黄金")
        if value >= 105: return ("bearish", "美元走强，压制黄金")
        return ("neutral", "美元处于中性区间")

    # === CPI 二维判断（结合 real_yield + dxy）===
    def bias_for_cpi(value):
        if value is None: return ("missing", "数据不足")
        # CPI 上行 + RealYield 下行 + DXY 不强 → 看多
        if value >= 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 偏高但实际利率下行 / 美元不强 → 抗通胀需求支撑黄金")
        # CPI 上行 + RealYield 上行 + DXY 上行 → 看空
        if value >= 3.0 and ry_val is not None and ry_val >= 2.0:
            if dxy_val is not None and dxy_val >= 105:
                return ("bearish", "CPI 高位 + 实际利率上行 + 美元走强，紧缩周期压制黄金")
        # CPI 温和回落 + RealYield 下行 + DXY 走弱 → 看多（降息预期）
        if 1.5 <= value < 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 温和回落 + 实际利率下行 + 美元不强，降息预期支撑黄金")
        # CPI 快速下行（CPI < 1.0）+ 衰退风险 → 等待确认
        if value < 1.0:
            return ("neutral", "CPI 快速下行，衰退风险升温，需结合 VIX/DXY/ETF 流向确认（不输出单方向）")
        # 其它中性情形
        return ("neutral", "CPI 处于中性区间，需结合其他宏观信号综合判断")

    # === VIX 方向: 反向 (normal) + 流动性冲击例外 ===
    def bias_for_vix(value):
        if value is None: return ("missing", "数据不足")
        if liquidity_shock:
            # 流动性冲击下 VIX 急升不代表避险买盘
            return ("bearish", "VIX 急升叠加 DXY 走强 + 实际利率上行 → 流动性冲击模式，黄金先被卖补保证金，待压力缓和后回到避险逻辑")
        if value >= 28: return ("strong_bullish", "VIX 急升，市场风险厌恶强烈，黄金避险属性显著")
        if value >= 22: return ("bullish", "VIX 上升，避险需求支撑黄金")
        if value <= 12: return ("strong_bearish", "VIX 极低，市场过度乐观，避险需求缺失")
        if value <= 15: return ("bearish", "VIX 偏低，避险需求不足")
        return ("neutral", "VIX 处于中性区间")

    def build(ind, bias_fn, fallback_label):
        if not ind:
            return {"value": None, "unit": "%" if "yield" in str(ind) else "",
                    "display_label": fallback_label, "source": "",
                    "bias": "missing", "bias_reason": "数据不足",
                    "status": "missing"}
        bias, reason = bias_fn(ind.get("value_num"))
        return {
            "value": ind.get("value_num"),
            "unit": ind.get("unit", ""),
            "display_label": ind.get("display_label", fallback_label),
            "source": ind.get("source_provider", ""),
            "observation_ts": ind.get("observation_ts", ""),
            "bias": bias,
            "bias_reason": reason,    # 新增字段：人类可读的判断依据
            "threshold_low": 0.5 if "yield" in str(ind) else None,
            "threshold_high": 2.8 if "yield" in str(ind) else None,
            "status": ind.get("status", "unknown"),
        }

    return {
        "real_yield_10y": build(real_yield, bias_for_real_yield, "美国10年期实际利率 (TIPS yield)"),
        "dxy": build(dxy, bias_for_dxy, "美元指数 DXY"),
        "cpi_yoy": build(cpi, bias_for_cpi, "美国 CPI 同比"),
        "vix": build(vix, bias_for_vix, "VIX 波动率"),
        "_diagnostics": {
            "liquidity_shock_detected": liquidity_shock,
            "liquidity_shock_definition": "VIX>=25 AND DXY>=105 AND RealYield>=2.0",
        },
    }
```

**关键设计**：
1. **新增 `bias_reason` 字段**：每张宏观卡不仅显示 5 档标签，还显示**人类可读的判断依据**（如 "CPI 偏高但实际利率下行 → 抗通胀需求支撑黄金"），让用户理解为什么这样判断
2. **`_diagnostics` 字段**：响应顶层暴露流动性冲击检测结果，前端可据此切换"危机模式"视觉（如 hero 加红色边条）
3. **`real_yield_5y` 与 `real_yield_10y` 兼容**：优先取 10Y，fallback 到 5Y（如果 10Y 数据缺失）

#### 4.6.8 前端渲染：4 张宏观卡（含 bias_reason 显示）

```javascript
function renderMacroStrip(snapshot) {
  if (!snapshot) return "";
  const items = [
    {key: "real_yield_10y", label: "实际利率 (TIPS yield)", value: snapshot.real_yield_10y},
    {key: "dxy", label: "DXY 美元指数", value: snapshot.dxy},
    {key: "cpi_yoy", label: "CPI 同比", value: snapshot.cpi_yoy},
    {key: "vix", label: "VIX 波动率", value: snapshot.vix},
  ];
  // 若 liquidity_shock_detected，hero 加红边
  const liquidityShock = snapshot._diagnostics?.liquidity_shock_detected;
  return `
    <section class="gold-bottom-group">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">MACRO INPUTS</p>
          <h2>宏观输入</h2>
          <p class="section-summary">直接影响黄金价格的 4 个宏观信号。</p>
        </div>
      </div>
      <div class="gold-macro-strip">
        ${items.map(item => renderMacroCard(item.label, item.value)).join("")}
      </div>
    </section>
  `;
}

function renderMacroCard(label, macro) {
  if (!macro || macro.status === "missing") {
    return `
      <article class="gold-macro-card" data-status="missing">
        <div>
          <strong>${label}</strong>
          <span class="gold-bias-chip gold-bias-missing">数据不足</span>
        </div>
        <b>—</b>
        <small>${macro?.display_label || ""}</small>
      </article>
    `;
  }
  return `
    <article class="gold-macro-card" data-bias="${macro.bias}">
      <div>
        <strong>${label}</strong>
        <span class="gold-bias-chip gold-bias-${macro.bias}">${biasLabel(macro.bias)}</span>
      </div>
      <b>${formatNumber(macro.value, 2)}${macro.unit || ""}</b>
      <small>${macro.display_label} · 来源 ${macro.source}</small>
      <p class="gold-macro-reason">${macro.bias_reason || ""}</p>
    </article>
  `;
}
```

### 4.7 状态色板（5 档多空 + 4 档数据状态）

#### 4.7.1 多空 chip（5 档，CSS 类名与 `.gold-bias-X` 对应）

```css
.gold-bias-chip {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.gold-bias-strong-bullish { background: var(--bullish-soft, rgba(15,118,110,0.18)); color: var(--bullish, #0f766e); }
.gold-bias-bullish       { background: rgba(15,118,110,0.10); color: var(--bullish, #0f766e); }
.gold-bias-neutral       { background: var(--accent-soft); color: var(--muted-strong); }
.gold-bias-bearish       { background: rgba(195,90,29,0.10); color: var(--bearish, #c35a1d); }
.gold-bias-strong-bearish{ background: rgba(195,90,29,0.18); color: var(--bearish, #c35a1d); }
.gold-bias-missing       { background: rgba(183,121,31,0.10); color: var(--warning, #b7791f); }
```

#### 4.7.2 卡片 data-tone（继承 BTC 模式）

`.gold-decision-card[data-tone="bullish"]` / `[data-tone="bearish"]` / `[data-tone="neutral"]` 沿用 BTC 页同款 4 色边框/背景变量，**不新增 CSS 变量**。

#### 4.7.3 二级容器（bottom-group）

```css
.gold-bottom-group {
  padding: 22px;
  border: 1px solid rgba(15,118,110,0.08);
  border-radius: 18px;
  background: rgba(255,255,255,0.32);
  box-shadow: 0 18px 48px rgba(23,37,34,0.05);
}
```

### 4.8 趋势图表

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
