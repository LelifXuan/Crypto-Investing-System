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
| **② 缺失宏观指标** | 黄金作为宏观资产，但页面完全没有 TIPS 实际利率、DXY、CPI 同比、VIX 这些直接影响黄金价格的因素 | 新增**4 个核心宏观指标卡**，复用后端 `MacroOverviewService` 已有数据（不需新增后端逻辑） |
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
│       结论 + 置信度 + 5 张 evidence-chip (TIPS/DXY/CPI/VIX/...) │
│   - 配置建议 (.gold-decision-card[data-tone="..."])             │
│       目标区间 + 低/达标/超配 + 月度动作                          │
│   - 执行计划 (.gold-decision-card[data-tone="..."])             │
│       今日 DCA + 黄金坑状态 + 冷却中/触发中/就绪                  │
├─────────────────────────────────────────────────────────────────┤
│ ③ 4 个核心宏观指标 (.gold-macro-strip, 类比 .btc-level-strip)   │
│   4 张 .gold-macro-card (min-height 220px):                     │
│   ┌────────────┬────────────┬────────────┬────────────┐         │
│   │ TIPS 5Y    │ DXY        │ CPI YoY    │ VIX        │         │
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
    "tips_5y": {
        "value": 1.85,           # 从 macro.layer_map.cross_asset_confirmation.indicators[?].key="real_yield_5y"
        "unit": "%",
        "display_label": "美国5年期通胀保值国债收益率",
        "source": "fred",
        "observation_ts": "2026-07-05",
        "delta_4w": -0.12,        # 从 real_rate_delta_4w / 派生
        "bias": "bullish",        # 多空语义（新增）
        "threshold_low": 0.5,     # scoring registry
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
- `gold_macro_adapter.py:104-170` 的 `macro_overview_to_gold_macro()` 新增 `_gold_macro_snapshot()` 函数，从 `result["layer_map"]` 提取 4 个指标的 value_num 和 status，并计算 `bias`
- 多空语义判断（黄金视角）：
  - **TIPS** 越低 → 黄金机会成本越低 → **看多**（`<0.5% bullish`, `>2.8% bearish`）
  - **DXY** 越低 → 美元弱 → 黄金以美元计价上涨 → **看多**（`<98 bullish`, `>108 bearish`）
  - **CPI YoY** 适度通胀利好 → **看多**（`2-5% bullish`, `>5% 或 <0% bearish`）
  - **VIX** 越高 → 风险厌恶 → 黄金避险 → **看多**（`>28 strong_bullish`, `<15 bearish`）

**判断函数**：

> **阈值来源说明**：4 个指标的 `low/high` 阈值（0.5/2.8, 98/108, 2/5, 15/28）**直接来自项目自有配置 `app/monitoring/configs/macro_scoring_registry.v1.json`** — 这是项目官方已经在 `macro/scoring_engine.py` 使用的评分阈值。spec 不引入新数字。
>
> 但配置里的 `higher_value_bias="bearish_for_risk_assets"` 是**针对风险资产**的视角；我们这里要**对黄金重新解读方向**：
> - TIPS 低 / DXY 低 → 美元弱 → 黄金（USD 计价）涨 → **看多**
> - CPI 适度（2-4%）→ 抗通胀 → 黄金 **看多**；CPI 过高/过低 → 央行政策风险 → **看空**
> - VIX 高 → 风险厌恶 → 黄金避险 → **看多**
        return "neutral"
    def bias_for_dxy(value):  # 越低越看多
        if value is None: return "missing"
        if value <= 98: return "strong_bullish"
        if value <= 102: return "bullish"
        if value >= 108: return "strong_bearish"
        if value >= 105: return "bearish"
        return "neutral"
    def bias_for_cpi(value):  # 适度看多
        if value is None: return "missing"
        if 2.0 <= value <= 4.0: return "bullish"
        if value > 5.0 or value < 1.0: return "bearish"
        return "neutral"
    def bias_for_vix(value):  # 越高越看多
        if value is None: return "missing"
        if value >= 28: return "strong_bullish"
        if value >= 22: return "bullish"
        if value <= 12: return "strong_bearish"
        if value <= 15: return "bearish"
        return "neutral"

    tips = find("real_yield_5y")
    dxy = find("dxy") or find("dollar_index")
    cpi = find("cpi_yoy")
    vix = find("vix")

    return {
        "tips_5y": {**({"value": tips["value_num"]} if tips else {}),
                    "unit": tips.get("unit", "%") if tips else "%",
                    "display_label": tips.get("display_label", "美国5年实际利率") if tips else "",
                    "source": tips.get("source_provider", "") if tips else "",
                    "bias": bias_for_tips(tips["value_num"]) if tips else "missing",
                    "status": tips.get("status", "missing") if tips else "missing"},
        "dxy": {...类似...},
        "cpi_yoy": {...类似...},
        "vix": {...类似...},
    }
```

#### 4.6.2 前端渲染：4 张宏观卡

```javascript
function renderMacroStrip(snapshot) {
  if (!snapshot) return "";
  const items = [
    {key: "tips_5y", label: "TIPS 5Y", value: snapshot.tips_5y},
    {key: "dxy", label: "DXY", value: snapshot.dxy},
    {key: "cpi_yoy", label: "CPI 同比", value: snapshot.cpi_yoy},
    {key: "vix", label: "VIX", value: snapshot.vix},
  ];
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
    <article class="gold-macro-card">
      <div>
        <strong>${label}</strong>
        <span class="gold-bias-chip gold-bias-${macro.bias}">${biasLabel(macro.bias)}</span>
      </div>
      <b>${formatNumber(macro.value, 2)}${macro.unit || ""}</b>
      <small>${macro.display_label} · 来源 ${macro.source}</small>
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
