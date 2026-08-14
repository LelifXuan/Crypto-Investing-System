# Gold Allocation Page V4 — Monet 玻璃卡片风格

**日期**: 2026-07-22
**状态**: 设计完成
**设计标准**: 严格对标 `btc_derivatives.js` 页面风格

## 1. 设计原则

完全融入项目现有设计系统，不对标独创风格：

- **卡片系统**: `.card` 类（frosted glass, Monet 色板, `backdrop-filter: blur(18px)`）
- **Eyebrow**: `<p class="eyebrow">`（accent 色，uppercase，0.2em letter-spacing）
- **Section heading**: `eyebrow + h2` 左侧 + 一句解释文字右侧（对标 `btc-section-heading`）
- **Chip 标签**: `.chip` / `.status-chip` 系统，五档 bias: `chip-bullish` (teal) / `chip-neutral` (gray) / `chip-bearish` (warm brown) / `chip-warning` (amber)
- **禁止 emoji**: 不用 🟢🟡🔴✅❌✓✗ 等 emoji 做状态标记
- **宽度**: 使用全局 `--shell-width`，不写自主 `max-width`
- **Hero**: `hero-card` 类（Monet radial gradient + shadow）

## 2. 页面结构（4 段）

```
┌─────────────────────────────────────────────────┐
│ ① Hero                                           │
│   GOLD ALLOCATION / 黄金宏观与配置                 │
│   宏观信号中性 — 按既定纪律执行定投    [刷新 XAUT]   │
├─────────────────────────────────────────────────┤
│ ② Macro Signals (三列 .card 网格)                 │
│   实际利率 TIPS 10Y  │  美元指数 DXY  │  波动率 VIX  │
│   2.03%  偏空       │  120.4  中性   │  18.8  中性  │
├────────────────────┬────────────────────────────┤
│ ③ Workbench        │                            │
│   SPOT DCA         │   CONTRACT REFERENCE       │
│   权重条 + 公式     │   XAUT 价格 / MA / 回撤     │
│   三层加仓门禁      │   衍生品 OI/费率/COT        │
│   建议金额 ¥500     │                            │
├────────────────────┴────────────────────────────┤
│ ④ Data Governance                                │
│   数据源状态: 宏观在线 · XAUT 可用 · 衍生品暂缺    │
└─────────────────────────────────────────────────┘
```

## 3. 各段详细设计

### 3.1 Hero

```
┌──────────────────────────────────────────────────────┐
│  GOLD ALLOCATION                          [刷新 XAUT] │
│  黄金宏观与配置                                        │
│  宏观信号中性 — 宏观不形成方向性约束，按既定纪律执行定投   │
└──────────────────────────────────────────────────────┘
```

- CSS: `hero-card`（已有全局样式）
- Eyebrow: "GOLD ALLOCATION" (accent 色, 12px, 0.2em)
- H1: "黄金宏观与配置" (34px, -0.04em)
- 副标题: XAUT 行情更新时间 + 宏观判断一句话（16px, text-secondary）
- 右侧按钮: `button compact`，点击触发 force refresh

### 3.2 Macro Signals（三列卡片）

对标 BTC derivatives 的 `btc-decision-grid` 三列布局。每个卡片：

```
┌──────────────────────┐
│ 实际利率    TIPS 10Y  │  ← eyebrow + monospace code badge
│                      │
│ 2.03%                │  ← 34px bold
│ [偏空]               │  ← chip-bearish
│ 利率偏高，债券吸引力   │  ← 12px text-secondary
│ 上升，压制黄金         │
│                      │
│ 来源 FRED · 06-23    │  ← 10px text-muted
└──────────────────────┘
```

三个信号灯：
| Eyebrow | Code | 数据源 | Bias 阈值（黄金视角） |
|---------|------|--------|---------------------|
| 实际利率 | TIPS 10Y | FRED `real_yield_5y` | ≤0.5 bullish / ≥2.0 bearish / ≥2.8 strong_bearish |
| 美元指数 | DXY | FRED `dollar_index` | ≤98 strong_bullish / ≥105 bearish / ≥108 strong_bearish |
| 波动率 | VIX | FRED `vix` | ≤12 strong_bearish / ≥22 bullish / ≥28 strong_bullish |

Bias chip 样式：
- `strong_bullish` → `chip-bullish` (teal bg + text)
- `bullish` → `chip-bullish-soft`
- `neutral` → `chip-neutral`
- `bearish` → `chip-bearish`
- `strong_bearish` → `chip-bearish` 
- `missing` → `status-chip` with "数据不足"

流动性冲击检测：当 TIPS≥2.0 AND DXY≥105 AND VIX≥25 时，在 Hero 区显示 warning chip。

### 3.3 Spot DCA（左栏）

```
┌────────────────────────────┐
│ SPOT DCA                   │
│ 现货定投                    │
│                            │
│ 当前权重 5.0% / 目标 5%-8%  │
│ ████████░░░░░              │  ← 进度条 (#5b8a83 色)
│ [下限临界]                  │  ← chip-neutral
│                            │
│  x    +    n × x    =  ¥1,500 │
│ ¥500      ¥1,000    触发合计 │  ← 公式区 (.card 内嵌 panel)
│                            │
│ 加仓条件门禁                 │
│ ① 宏观门禁  [通过] TIPS<2.8% │  ← 行级 chip
│ ② 回撤触发  [触发] 12%≥8%   │
│ ③ 指标确认  [1/5] 需≥3      │
│   RSI(14)  —  ✗             │  ← 子网格，5行2列
│   布林位置  —  ✗             │
│   距EMA20  —  ✗             │
│   CCI(20)   —  ✗             │
│   成交量 Z  -1.2  ✗         │
│                            │
│ ┌────────────────────────┐ │
│ │ 本月建议                │ │  ← accent 浅色背景
│ │ ¥500      [基础定投]    │ │  ← 大字号金额 + chip
│ │ 加仓未触发（1/5 确认）   │ │
│ └────────────────────────┘ │
└────────────────────────────┘
```

- 权重条：`height: 6px; background: rgba(160,140,108,0.12);` 内嵌 `#5b8a83` 色 fill
- 公式区：`background: rgba(91,138,131,0.05)` 浅 teal 背景，`border-radius: 12px`
- 门禁行：
  - 通过 → `border-left: 3px solid #5b8a83` + teal bg
  - 触发 → `border-left: 3px solid #b8924a` + amber bg（和 chip-warning 同色系）
  - 未通过 → 灰色左边框
- 建议区：`border: 1px solid rgba(91,138,131,0.15); background: linear-gradient(135deg, rgba(91,138,131,0.08), rgba(91,138,131,0.03))`
- 金额字号：32px bold

### 3.4 Contract Reference（右栏）

```
┌────────────────────────────┐
│ CONTRACT REFERENCE          │
│ 合约参考                    │
│                            │
│ ┌────────────────────────┐ │
│ │ XAUT 最新价  4,092     │ │  ← bearish 浅色 banner
│ │ [MA50 下方]            │ │     价格跌破 MA50
│ └────────────────────────┘ │
│                            │
│ MA50   4,350              │ │
│ MA200  4,680   [下方]     │ │  ← 2列网格
│ 60日回撤 -12.0%           │ │
│ NATR    1.7%              │ │
│ 成交量Z -1.2              │ │
│ 7日变化 -1.9%             │ │
│                            │
│ 衍生品数据                  │ │
│ OI变化(4w)  数据积累中     │ │  ← 2列网格
│ 资金费率    数据积累中     │ │
│ COT净多分位 待录入        │ │
│ 更新时间    2026-07-22    │ │
└────────────────────────────┘
```

- XAUT 价格 banner：根据 MA50 位置着色 — `above_ma50=false` 时用 `rgba(176,117,88,0.06)` bearish 浅背景
- 技术网格：`grid-template-columns: 1fr 1fr; gap: 10px`，每格 `background: rgba(91,138,131,0.04); border-radius: 8px`
- 衍生品网格：同上，空数据用 `text-muted` 色显示占位文字
- MA50/MA200 chip：`chip-bullish-soft` (上方) / `chip-bearish` (下方)

### 3.5 Data Governance（页脚）

```
┌─────────────────────────────────────────────┐
│ 数据治理                                     │
│ K线样本: 260天  │  宏观源: FRED·BLS·ISM      │
│ [宏观在线] [XAUT 可用] [衍生品暂缺]           │
└─────────────────────────────────────────────┘
```

- 单行 `.card`，flex 布局
- 左侧：数据源描述（label + value）
- 右侧：`status-chip` 状态标签（对标 BTC 的 `btc-provider-card`）
  - 可用 → `chip-bullish-soft` 
  - 暂缺 → `chip-warning`

## 4. CSS 命名规范

全部复用全局类，新增类使用 `gold-` 前缀（保持和现有 gold 相关 CSS 一致）：

| 新增类 | 用途 |
|--------|------|
| `.gold-signal-card` | 宏观信号卡片（`.card` 的子类，增加 34px 数值字号） |
| `.gold-formula-box` | 公式展示区 |
| `.gold-gate-row` | 门禁条件行 |
| `.gold-gate-row.passed` | 通过状态 |
| `.gold-gate-row.triggered` | 触发状态 |
| `.gold-tech-grid` | 2 列技术指标网格 |
| `.gold-tech-tile` | 网格中单个 tile |
| `.gold-price-banner` | XAUT 价格横幅 |
| `.gold-weight-bar` | 权重进度条 |
| `.gold-weight-fill` | 进度条填充 |
| `.gold-recommendation` | 建议金额区 |
| `.gold-formula-var` | 公式变量 x / n×x |

不新建任何 `.gold-v3-` / `.gold-v4-` 前缀，直接用 `.gold-`。

## 5. 前端 JS 结构

`app/static/pages/gold_v4.js`（替换 `gold_v3.js`）：

- 导入: `api.js` (getGoldV3Allocation, getGoldDerivatives), `dom.js` (escapeHtml, formatNumber, setRoot)
- 渲染函数:
  - `renderHero(data)` → hero section
  - `renderSignalCard(signal)` → 单个信号卡片
  - `renderSpotDca(spot)` → 现货定投左栏
  - `renderContractRef(contract)` → 合约参考右栏
  - `renderGovernance(data)` → 数据治理页脚
- 生命周期: `renderGoldV4()` export，返回 `{ unmount, ready }`

bias → chip class 映射:
```javascript
function biasChipClass(bias) {
  return {
    strong_bullish: "chip-bullish",
    bullish: "chip-bullish-soft",
    neutral: "chip-neutral",
    bearish: "chip-bearish",
    strong_bearish: "chip-bearish",
    missing: "chip-warning",
  }[bias] || "chip-neutral";
}
```

bias label 映射（中文）:
```javascript
function biasLabel(bias) {
  return {
    strong_bullish: "强势看多", bullish: "看多",
    neutral: "中性", bearish: "看空",
    strong_bearish: "强势看空", missing: "数据不足",
  }[bias] || "中性";
}
```

## 6. 后端变更

**无变更**。V3 的 schemas 和 endpoints 已满足 V4 需求：
- `GET /gold/v3/allocation` → `GoldV3AllocationResponse` (signals + spot + contract)
- `GET /gold/derivatives` → OI/资金费率/COT

唯一调整：前端调用时合并 derivatives 数据到 contract 对象（同 V3 逻辑）。

## 7. 文件变更

| 操作 | 文件 |
|------|------|
| 新建 | `app/static/pages/gold_v4.js` |
| 修改 | `app/static/styles.css` — 追加 `.gold-*` 类 |
| 修改 | `app/static/main.js` — 路由指向 `gold_v4.js`，render 改为 `renderGoldV4` |
| 删除 | `app/static/pages/gold_v3.js` |
| 新建 | `tests/test_gold_v4_frontend_static.py` |
| 删除 | `tests/test_gold_v3_frontend_static.py` |

## 8. 与 V3 的关键差异

| 方面 | V3（被否决） | V4 |
|------|------------|-----|
| 卡片 | `.gold-v3-section-card` 自建类 | `.card` 全局类 |
| 信号 | emoji + 自建 `.gold-v3-signal-light` | `.card` + `.eyebrow` + `.chip` |
| Section head | 内联 h2 | `btc-section-heading` 模式 |
| 颜色 | #d4a853 金色渐变 | Monet 色板 (#5b8a83 teal, #b07558 bearish) |
| 门禁 | emoji ✅❌✓✗ | `.chip` + 左边框色条 |
| 建议卡 | 金色渐变背景 | accent 浅色背景 (同 Monet teal) |
| 宽度 | `max-width: 1100px` 自建 | 继承全局 `--shell-width` |
| 页脚 | `button compact` 单独 | 对标 BTC governance bar |
