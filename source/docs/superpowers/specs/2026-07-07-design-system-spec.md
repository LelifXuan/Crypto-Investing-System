# 设计系统统一框架 spec (design-system)

> 状态：**用户已批准**（方案：只抽 spec + components.js；chip 4 档 data-tone；docs/superpowers/specs/）
> 日期：2026-07-07
> 作者：ZCode + 用户
> 范围：**仅产 spec 文档与 `components.js` helper**；不动既有页面（用户后续可单独决定哪些页重构）

## 1. 背景与动机

### 现状（2026-07-06 审计）

仓库有 10 个 page + 9432 行 CSS：

| Tier | 页面 | 特征 |
|---|---|---|
| Tier 1 现代 | `gold_allocation.js` (689 行) + `btc_derivatives.js` (1051 行) | hero-card + section-head + chip + bottom-group 完整四件套 |
| Tier 2 半现代 | `analysis.js` (1465 行) | 共享基础类但无 bottom-group |
| Tier 3 老 V1 | `knowledge.js` (468 行) + `monitoring.js` (1192 行) + `market_events.js` (295 行) + `macro_calendar.js` (270 行) | 私有命名空间 + 裸 section |
| Tier 4 小作坊 | `alerts.js` (780 行) + `structure.js` (1240 行) + `ashare_etf.js` (538 行) | 自创 alert-* / structure-* / etf-* 命名空间 |

**核心问题**：
- 175 个 class 中**仅 9 个跨页面共享（5%）**，166 个单页私有
- `chip-bullish/bearish/neutral/event/warning/danger/success` 多套并行
- `data-state` / `data-tone` / `data-status` / `data-bias` 4 套状态驱动并行
- CSS 变量（22 颜色 + 7 尺寸 + 5 边框阴影）覆盖完整但**未驱动组件**（私有类多硬编码）
- 用户指定：**knowledge 与 monitoring 是问题最大的两页**

### 动机

让"设计语言"从**两个孤立参考实现 + 9 个独立小作坊**升级为**单一规范 + 组件库 + 设计 token 引用**。

## 2. 目标

1. **统一规范**：一份 spec 文档定义全仓页面模板、组件契约、状态色规范
2. **组件库**：`components.js` helper 覆盖 80% 重复模式（hero / decision grid / 工具栏 / 二级容器 / chip / 状态态）
3. **不动现有页面**：本次仅出 spec + helper；后续页面改造是独立项目
4. **未来新增页面**：直接按 spec + helper 写，0 设计决策成本

## 3. 非目标

- ❌ 重构 knowledge/monitoring/alerts/structure 等现有页面
- ❌ 删除任何现有私有 CSS 类
- ❌ 改变 CSS 变量值（仅规范"用法"）
- ❌ 移动端响应式细化（沿用既有）
- ❌ 新增设计 token（颜色 / 间距已足够）

## 4. 设计系统规范

### 4.1 4 档状态色（核心约定）

**仅 4 档**：`bullish` / `bearish` / `warning` / `neutral`

| 状态 | CSS 类 | CSS 变量 | 用途 |
|---|---|---|---|
| bullish | `.gold-bias-bullish` / `[data-tone="bullish"]` | `--bullish` | 看多 / 正常 / 通过 |
| bearish | `.gold-bias-bearish` / `[data-tone="bearish"]` | `--bearish` | 看空 / 失败 / 警告（红） |
| warning | `.gold-bias-strong_bearish` / `[data-tone="warning"]` | `--warning` | 需关注 / 降级 / 风险（黄） |
| neutral | `.gold-bias-neutral` / `[data-tone="neutral"]` | `--neutral` | 中性 / 无数据 / 等待 |

**强档（optional）**：`strong_bullish` / `strong_bearish`（仅用于多空标签，**不用于**决策卡 / 状态指示）

**别名兼容**（保留旧用法）：
- `chip-bullish` / `chip-bearish` / `chip-warning` / `chip-neutral`（已存在 styles.css:2278-2321）
- `data-state="bullish|bearish|warning|neutral"`（BTC 衍生品页）
- `data-tone="bullish|bearish|warning|neutral"`（黄金配置 V2）**— 推荐**

**新增的 soft 变体**（可选）：
- `chip-bullish-soft` / `chip-bearish-soft`（用于 secondary 状态，不喧宾夺主）

### 4.2 9 段递进布局（页面骨架）

任何新页面应至少包含以下几段（按需增减）：

```
① Hero          .hero-card + .eyebrow + h1 + 副文 + 右侧 actions
② 决策带        .bottom-group > .section-head > .decision-grid > .decision-card[data-tone]
③ 关键指标条    .bottom-group > .key-strip > .key-card[4 列]
④ 7 模块证据    .bottom-group > .module-section > .module-card[data-tone]
⑤ 图表区        .bottom-group > .chart-section > .chart-card > canvas
⑥ 详情 + 操作   .bottom-group > .detail-grid > .detail-card + .action-panel
⑦ 设置 + 诊断   .bottom-group > .settings-grid > .settings-card + .diagnostics-card
⑧ 单点深度      .indicator-layout > .indicator-section × 2
⑨ 数据治理      .bottom-group > details.drawer
```

每个段位的关键约定：

- **所有段位都包在 `.bottom-group`**（圆角 18 + 阴影 + 半透明白底，styles.css:9351）
- **每段顶部有 `.section-head`**（eyebrow + h2 + section-summary，可选 .compact）
- **决策带必须 3 列**（`.decision-grid` repeat(3, ...)）
- **关键指标条必须 4 列**（`.key-strip` repeat(4, ...)）
- **数据治理用 `<details>` 折叠**（避免占主屏空间）

### 4.3 DOM 模式（templates）

#### 4.3.1 Hero

```html
<section class="hero-card" data-page-tone="bullish">
  <div>
    <p class="eyebrow">PAGE NAME</p>
    <h1>页面标题</h1>
    <p>一句总结 / 动态 verdict</p>
  </div>
  <div class="hero-actions">
    <span class="status-chip">...</span>
    <button class="button compact">刷新</button>
  </div>
</section>
```

#### 4.3.2 决策带

```html
<section class="bottom-group">
  <div class="section-head compact">
    <div>
      <p class="eyebrow">DECISIONS</p>
      <h2>决策带</h2>
      <p class="section-summary">3 个核心结论。</p>
    </div>
  </div>
  <div class="decision-grid">
    <article class="decision-card" data-tone="bullish">
      <p class="eyebrow">宏观环境</p>
      <h3>结论</h3>
      <p>说明文字</p>
      <small>支撑数字</small>
    </article>
    <!-- 重复 2 次, 总 3 张 -->
  </div>
</section>
```

#### 4.3.3 关键指标条

```html
<section class="bottom-group">
  <div class="section-head compact">
    <div>
      <p class="eyebrow">MACRO INPUTS</p>
      <h2>宏观输入</h2>
    </div>
  </div>
  <div class="key-strip">
    <article class="key-card" data-bias="bullish">
      <div>
        <strong>指标名</strong>
        <span class="bias-chip bias-bullish">看多</span>
      </div>
      <b>1.85%</b>
      <small>说明 · 来源</small>
      <p class="key-reason">判断依据</p>
    </article>
    <!-- 重复 3 次, 总 4 张 -->
  </div>
</section>
```

#### 4.3.4 模块证据卡

```html
<section class="bottom-group">
  <div class="section-head compact">
    <div>
      <p class="eyebrow">MODULES</p>
      <h2>模块证据</h2>
    </div>
  </div>
  <div class="module-grid">
    <article class="module-card" data-tone="bullish" data-module="key">
      <header class="module-head">
        <h3>模块名</h3>
        <span class="status-chip chip-bullish">支撑</span>
      </header>
      <b class="module-score">75</b>
      <small>置信度 80% · 直接</small>
      <p class="module-headline">headline</p>
      <ul class="module-facts">
        <li>事实 1</li>
      </ul>
    </article>
  </div>
</section>
```

#### 4.3.5 图表区

```html
<section class="bottom-group">
  <div class="section-head compact">
    <div>
      <p class="eyebrow">CHARTS</p>
      <h2>图表</h2>
    </div>
  </div>
  <div class="chart-grid">
    <article class="chart-card" data-tone="bullish">
      <header class="chart-head">
        <div>
          <p class="eyebrow">图表 1</p>
          <h3>标题</h3>
        </div>
        <span class="status-chip">类型</span>
      </header>
      <div class="chart-wrap">
        <canvas></canvas>
      </div>
    </article>
  </div>
</section>
```

#### 4.3.6 数据治理

```html
<section class="bottom-group">
  <details class="drawer">
    <summary>数据治理与可信度</summary>
    <div class="governance-grid">
      <article><span>报价状态</span><b>...</b></article>
      <article><span>K 线数量</span><b>...</b></article>
    </div>
  </details>
</section>
```

### 4.4 CSS 变量用法约定

**所有 page JS 应使用 CSS 变量，不要硬编码**：

| 类别 | 变量 | 用法 |
|---|---|---|
| 间距 | `--content-gap`, `--section-gap`, `--card-padding` | section 间 / section 内 / card 内 padding |
| 圆角 | `--radius`, `--radius-sm` | 大型容器 24px / 小型 card 16px |
| 阴影 | `--shadow-card`, `--shadow-hover` | 默认 / hover |
| 颜色 | `--accent`, `--bullish`, `--bearish`, `--warning`, `--neutral` | 通过 `[data-tone]` 间接使用 |
| 字体 | `--font-sans` | 不写死字体栈 |

CSS 变量全集：`styles.css:1-47`。

### 4.5 字号 / 圆角 / 间距规范

| 用途 | 字号 / 圆角 / 间距 | 备注 |
|---|---|---|
| Page h1 | `clamp(34px, 3vw, 46px)` | 已是全局约定（styles.css:115） |
| Section h2 | `clamp(24px, 1.5vw, 30px)` | 已是全局约定（styles.css:122） |
| Card title | 17-21px | 决策卡 / 模块卡标题 |
| Card metric | 22-25px | 数值显示 |
| 数值（重要） | 25px strong | `.key-card b` |
| Card padding | `var(--card-padding)` (28px) | 全 card 统一 |
| 二级容器 padding | 22px | `.bottom-group` |
| 卡片间距 | `var(--content-gap)` (24px) | grid gap |
| 卡片圆角 | `var(--radius-sm)` (16px) 或 14px | 标准 card |
| 二级容器圆角 | 18px | `.bottom-group` |

## 5. 组件库 `components.js`

新建 `app/static/core/components.js`：

### 5.1 核心 helper 列表

```javascript
// === Hero ===
export function hero({ eyebrow, title, subtitle, actions, tone = null })
// 渲染 .hero-card + 副文 + 右侧 actions（按钮 / chip / 状态）
// 若 tone 非空，自动加 data-page-tone 属性

// === 决策带 ===
export function decisionGrid({ eyebrow, title, summary, decisions })
// decisions: [{ eyebrow, title, body, hint, tone }]
// 渲染 .bottom-group > .section-head > .decision-grid (3 张)

// === 关键指标条 ===
export function keyStrip({ eyebrow, title, summary, items, liquidityBanner = null })
// items: [{ label, value, unit, source, bias, reason, displayLabel }]
// 渲染 4 列 .key-strip; liquidityBanner 非空时显示 .liquidity-shock-banner

// === 模块证据卡 ===
export function moduleSection({ eyebrow, title, summary, modules })
// modules: [{ key, title, score, confidence, dataQuality, state, headline, facts, interpretation }]
// 渲染 .bottom-group > .module-grid (N 张 module-card)

// === 图表区 ===
export function chartSection({ eyebrow, title, summary, charts })
// charts: [{ id, title, type, data, tone }]
// 渲染 .bottom-group > .chart-grid > .chart-card + canvas

// === Chip / 状态 ===
export function biasChip(bias)
// 5 档 → "强势看多/看多/中性/看空/强势看空" + CSS class

export function statusChip(text, tone = "neutral")
// 4 档 → 返回 <span class="status-chip tone-X">

export function heroChip(text, tone = "neutral")
// 与 statusChip 相同, 但语义上用于 hero 区域

// === 二级容器 ===
export function bottomGroup(content, options = {})
// options: { tone: "bullish" | "bearish" | "warning" | "neutral" }
// 渲染 <section class="bottom-group" data-tone="...">content</section>

// === 段头 ===
export function sectionHead({ eyebrow, title, summary, compact = true, extras = "" })
// 渲染 .section-head .compact 块

// === 数据治理 ===
export function governanceSection(items)
// items: [{ label, value }]
// 渲染 .bottom-group > details.drawer > .governance-grid

// === 数据状态 ===
export function dataState({ kind, message })
// kind: loading | empty | error | degraded
// 渲染对应 .data-state .data-state-X

// === 流动性冲击警告 ===
export function liquidityShockBanner()
// 渲染 .liquidity-shock-banner, 用于 .bottom-group 顶部
```

### 5.2 调用示例

新页面骨架：

```javascript
import { hero, decisionGrid, keyStrip, bottomGroup, sectionHead,
         moduleSection, chartSection, governanceSection, biasChip, statusChip,
         dataState, liquidityShockBanner } from "../core/components.js";

export function renderNewPage() {
  return [
    hero({
      eyebrow: "NEW PAGE",
      title: "新页面",
      subtitle: "一句话总结。",
      actions: `<button class="button compact">刷新</button>`,
      tone: "bullish",
    }),

    bottomGroup([
      sectionHead({ eyebrow: "DECISIONS", title: "决策带" }),
      decisionGrid({ decisions: [...] }),
    ].join("")),

    bottomGroup([
      sectionHead({ eyebrow: "MACRO", title: "宏观输入" }),
      keyStrip({ items: [...] }),
    ].join("")),

    governanceSection([{ label: "数据状态", value: "OK" }]),
  ].join("");
}
```

## 6. CSS 类新增（最小集合）

为了让 components.js 输出能渲染，需要在 `styles.css` 追加：

```css
/* === Design System 1.0 === */

/* Hero */
.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Decision Grid */
.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.decision-card {
  min-height: 200px;
  padding: 18px 20px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.decision-card[data-tone="bullish"] {
  border-color: rgba(15, 118, 110, 0.30);
  background: rgba(15, 118, 110, 0.04);
}
.decision-card[data-tone="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
  background: rgba(195, 90, 29, 0.04);
}
.decision-card[data-tone="warning"] {
  border-color: rgba(183, 121, 31, 0.30);
  background: rgba(183, 121, 31, 0.04);
}
.decision-card[data-tone="neutral"] {
  border-color: rgba(106, 124, 135, 0.20);
  background: rgba(106, 124, 135, 0.04);
}

/* Key Strip (4 列关键指标) */
.key-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.key-card {
  min-height: 200px;
  padding: 18px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.key-card[data-bias^="strong_bullish"],
.key-card[data-bias="bullish"] {
  border-color: rgba(15, 118, 110, 0.30);
}
.key-card[data-bias^="strong_bearish"],
.key-card[data-bias="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
}
.key-card[data-bias="warning"] {
  border-color: rgba(183, 121, 31, 0.30);
  background: rgba(183, 121, 31, 0.04);
}
.key-card[data-bias="missing"] {
  border-color: rgba(183, 121, 31, 0.30);
  background: rgba(183, 121, 31, 0.04);
}
.key-reason {
  font-size: 12px;
  color: var(--muted);
  margin: 8px 0 0;
  line-height: 1.4;
}

/* Module Grid */
.module-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.module-card {
  padding: 18px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.module-card[data-tone="bullish"] {
  border-color: rgba(15, 118, 110, 0.30);
}
.module-card[data-tone="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
}
.module-card[data-tone="warning"] {
  border-color: rgba(183, 121, 31, 0.30);
}
.module-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.module-score {
  display: block;
  font-size: 26px;
  font-weight: 800;
  margin: 4px 0 6px;
  color: var(--ink);
}
.module-headline {
  font-size: 13px;
  color: var(--muted-strong);
  margin: 0 0 10px;
  line-height: 1.5;
}
.module-facts {
  list-style: disc;
  margin: 8px 0 0 18px;
  padding: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}

/* Chart */
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.chart-card {
  padding: 18px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.chart-wrap {
  position: relative;
  height: var(--chart-height, 300px);
}

/* Bottom Group (与 BTC/Gold 既有同名, 复用 styles.css:9351) */
.bottom-group {
  padding: 22px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.32);
  box-shadow: 0 18px 48px rgba(23, 37, 34, 0.05);
  margin-bottom: var(--content-gap);
}

/* Section Head (与既有同名) */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: var(--content-gap);
}
.section-head.compact {
  margin-bottom: 14px;
}
.section-summary {
  color: var(--muted);
  font-size: 13px;
  margin: 6px 0 0;
}

/* Eyebrow (与既有同名) */
.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 11px;
  font-weight: 800;
  color: var(--accent);
  margin: 0 0 6px;
}

/* Hero Card (与既有同名) */
.hero-card {
  position: relative;
  padding: 28px 30px;
  border-radius: var(--radius);
  background:
    radial-gradient(120% 100% at 0% 0%, rgba(15,118,110,.08), transparent 55%),
    radial-gradient(120% 100% at 100% 100%, rgba(195,90,29,.05), transparent 55%),
    linear-gradient(180deg, var(--surface-elevated) 0%, var(--panel-accent) 100%);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-soft);
  margin-bottom: var(--content-gap);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.hero-card[data-page-tone="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
  background:
    radial-gradient(120% 100% at 0% 0%, rgba(195,90,29,.10), transparent 55%),
    linear-gradient(180deg, var(--surface-elevated) 0%, var(--panel) 100%);
}
.hero-card[data-page-tone="warning"] {
  border-color: rgba(183, 121, 31, 0.30);
}

/* Liquidity Shock Banner */
.liquidity-shock-banner {
  padding: 12px 16px;
  border-left: 3px solid var(--bearish);
  background: rgba(195, 90, 29, 0.06);
  border-radius: 4px;
  font-size: 13px;
  color: var(--ink);
  margin: 0 0 var(--content-gap) 0;
}

/* Governance (drawer 模式) */
.drawer {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.4);
}
.drawer > summary {
  cursor: pointer;
  padding: 14px 16px;
  font-weight: 700;
  font-size: 14px;
  color: var(--ink);
}
.drawer[open] > summary {
  border-bottom: 1px solid var(--border);
}
.governance-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 16px;
}
.governance-grid article {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.governance-grid article span {
  color: var(--muted);
  font-size: 12px;
}
.governance-grid article b {
  font-size: 18px;
  font-weight: 800;
  color: var(--ink);
}

/* Data State (与既有同名) */
.data-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--muted-strong);
}
.data-state-loading {
  background: var(--accent-soft);
  border-color: rgba(15, 118, 110, 0.20);
}
.data-state-empty {
  background: rgba(106, 124, 135, 0.05);
}
.data-state-error {
  background: rgba(195, 90, 29, 0.06);
  border-color: rgba(195, 90, 29, 0.30);
  color: var(--bearish);
}

/* Status Chip 4 档 */
.status-chip {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.status-chip.chip-bullish { background: var(--bullish-soft); color: var(--accent-strong); }
.status-chip.chip-bearish { background: var(--bearish-soft); color: var(--bearish); }
.status-chip.chip-warning { background: var(--warning-soft); color: var(--warning); }
.status-chip.chip-neutral { background: rgba(106, 124, 135, 0.12); color: var(--neutral); }

/* Bias Chip (5 档多空, 与 gold-bias-* 同名但提供基线) */
.bias-chip {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
}
.bias-chip.bias-strong_bullish { background: rgba(15, 118, 110, 0.20); color: #0b5f58; }
.bias-chip.bias-bullish { background: var(--bullish-soft); color: var(--accent-strong); }
.bias-chip.bias-neutral { background: rgba(106, 124, 135, 0.12); color: var(--neutral); }
.bias-chip.bias-bearish { background: var(--bearish-soft); color: var(--bearish); }
.bias-chip.bias-strong_bearish { background: rgba(195, 90, 29, 0.20); color: #8c3a10; }
.bias-chip.bias-missing { background: var(--warning-soft); color: var(--warning); }
```

**总新增：~250 行 CSS**（一次性写入 styles.css 末尾，可被所有未来页面使用）。

## 7. 组件库 API（伪代码）

```javascript
// app/static/core/components.js
import { escapeHtml, byId } from "./dom.js";

// ---------- Hero ----------
export function hero({ eyebrow, title, subtitle, actions = "", tone = null }) {
  const toneAttr = tone ? ` data-page-tone="${tone}"` : "";
  return `
    <section class="hero-card"${toneAttr}>
      <div>
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h1>${escapeHtml(title)}</h1>
        ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
      </div>
      ${actions ? `<div class="hero-actions">${actions}</div>` : ""}
    </section>
  `;
}

// ---------- Section Head ----------
export function sectionHead({ eyebrow, title, summary = "", compact = true, extras = "" }) {
  return `
    <div class="section-head${compact ? " compact" : ""}">
      <div>
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h2>${escapeHtml(title)}</h2>
        ${summary ? `<p class="section-summary">${escapeHtml(summary)}</p>` : ""}
      </div>
      ${extras}
    </div>
  `;
}

// ---------- Bottom Group ----------
export function bottomGroup(content, { tone = null } = {}) {
  const toneAttr = tone ? ` data-tone="${tone}"` : "";
  return `<section class="bottom-group"${toneAttr}>${content}</section>`;
}

// ---------- Decision Grid (3 卡) ----------
export function decisionGrid({ decisions }) {
  return `<div class="decision-grid">${decisions.map(d => `
    <article class="decision-card" data-tone="${escapeHtml(d.tone || "neutral")}">
      <p class="eyebrow">${escapeHtml(d.eyebrow)}</p>
      <h3>${escapeHtml(d.title)}</h3>
      ${d.body ? `<p>${escapeHtml(d.body)}</p>` : ""}
      ${d.hint ? `<small>${escapeHtml(d.hint)}</small>` : ""}
    </article>`).join("")}</div>`;
}

// ---------- Key Strip (4 列) ----------
export function keyStrip({ items, liquidityBanner = null }) {
  return `
    ${liquidityBanner ? `<div class="liquidity-shock-banner">${escapeHtml(liquidityBanner)}</div>` : ""}
    <div class="key-strip">
      ${items.map(item => `
        <article class="key-card" data-bias="${escapeHtml(item.bias || "missing")}">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            ${biasChip(item.bias)}
          </div>
          <b>${escapeHtml(item.value)}${escapeHtml(item.unit || "")}</b>
          <small>${escapeHtml(item.displayLabel || "")}${item.source ? ` · 来源 ${escapeHtml(item.source)}` : ""}</small>
          ${item.reason ? `<p class="key-reason">${escapeHtml(item.reason)}</p>` : ""}
        </article>`).join("")}
    </div>
  `;
}

// ---------- Module Section ----------
export function moduleSection({ modules }) {
  return `<div class="module-grid">
    ${modules.map(m => `
      <article class="module-card" data-tone="${escapeHtml(m.tone || "neutral")}" data-module="${escapeHtml(m.key || "")}">
        <header class="module-head">
          <h3>${escapeHtml(m.title)}</h3>
          ${statusChip(m.label || "中性", m.tone || "neutral")}
        </header>
        <b class="module-score">${escapeHtml(String(m.score ?? "—"))}</b>
        <small>置信度 ${Math.round((m.confidence || 0) * 100)}% · ${escapeHtml(m.dataQuality || "—")}</small>
        <p class="module-headline">${escapeHtml(m.headline || "")}</p>
        ${m.facts && m.facts.length ? `<ul class="module-facts">
          ${m.facts.map(f => `<li>${escapeHtml(f)}</li>`).join("")}
        </ul>` : ""}
      </article>`).join("")}
  </div>`;
}

// ---------- Chart Section (占位 + 注册) ----------
export function chartSection({ charts, onRender }) {
  return `<div class="chart-grid">
    ${charts.map(c => `
      <article class="chart-card" data-tone="${escapeHtml(c.tone || "neutral")}">
        <header class="chart-head">
          <div>
            <p class="eyebrow">${escapeHtml(c.eyebrow || "")}</p>
            <h3>${escapeHtml(c.title)}</h3>
          </div>
          ${c.kind ? `<span class="status-chip">${escapeHtml(c.kind)}</span>` : ""}
        </header>
        <div class="chart-wrap" id="chart-${escapeHtml(c.id)}"></div>
      </article>`).join("")}
  </div>
  <script>(${onRender.toString()})();</script>`;
}

// ---------- Governance Section ----------
export function governanceSection(items) {
  return `
    <section class="bottom-group">
      <details class="drawer">
        <summary>数据治理与可信度</summary>
        <div class="governance-grid">
          ${items.map(item => `
            <article>
              <span>${escapeHtml(item.label)}</span>
              <b>${escapeHtml(String(item.value ?? "—"))}</b>
            </article>`).join("")}
        </div>
      </details>
    </section>
  `;
}

// ---------- Chip Helpers ----------
const BIAS_LABELS = {
  strong_bullish: "强势看多", bullish: "看多", neutral: "中性",
  bearish: "看空", strong_bearish: "强势看空", missing: "数据不足",
};

export function biasChip(bias) {
  const label = BIAS_LABELS[bias] || "中性";
  const cls = bias || "neutral";
  return `<span class="bias-chip bias-${escapeHtml(cls)}">${escapeHtml(label)}</span>`;
}

export function statusChip(text, tone = "neutral") {
  return `<span class="status-chip chip-${escapeHtml(tone)}">${escapeHtml(text)}</span>`;
}

// ---------- Data State ----------
export function dataState({ kind, message }) {
  const cls = ["loading", "empty", "error", "degraded"].includes(kind) ? kind : "empty";
  const icons = { loading: "•", empty: "—", error: "!", degraded: "⚠" };
  return `<div class="data-state data-state-${cls}">
    <span>${icons[cls] || ""}</span>
    <strong>${escapeHtml(message)}</strong>
  </div>`;
}

export function liquidityShockBanner(message) {
  return `<div class="liquidity-shock-banner">${escapeHtml(message)}</div>`;
}
```

## 8. 文件改动清单

| 文件 | 改动 |
|---|---|
| `docs/superpowers/specs/2026-07-07-design-system-spec.md` | 新建（本文档） |
| `app/static/core/components.js` | 新建（约 150 行 helper） |
| `app/static/styles.css` | 末尾追加约 250 行设计系统 CSS |
| **不动** | 任何现有 page 文件 |

## 9. 验证

- 单元测试：在 `tests/test_design_system.py` 中
  - 验证 `hero()` 输出包含 `class="hero-card"`
  - 验证 `decisionGrid()` 输出 3 张 `data-tone` 卡
  - 验证 `keyStrip()` 输出 4 张 `data-bias` 卡
  - 验证 `biasChip("bullish")` 输出 `class="bias-chip bias-bullish"`
  - 验证 CSS 包含所有规范类（grep 验证）
- 视觉冒烟：创建 `app/static/pages/_design_system_demo.js` 示例页（独立路由），展示所有组件

## 10. 风险与回滚

- 风险：CSS 类与现有页面的私有类名可能冲突（如 `.module-card` 已存在）
  - 缓解：grep 验证 + 用 BEM 命名空间（`.ds-*` 前缀）或保留现有命名
- 回滚：单文件 revert（components.js + styles.css 末尾追加块）

## 11. 后续（Follow-up，独立项目）

- 重构 knowledge.js（用新组件库替换 35 个 .knowledge-* 类）
- 重构 monitoring.js（用新组件库替换 48 个 .monitoring-* 类）
- 重构 alerts.js / structure.js / ashare_etf.js（待定）
- 把所有现有私有 chip helper（5+ 套）统一到 `statusChip(text, tone)` 与 `biasChip(bias)`

---

## 12. 自审

- ✅ 无占位符 / TBD
- ✅ 内部一致：4 档状态色命名贯穿全文
- ✅ 范围聚焦：spec + components.js + CSS，不动现有页
- ✅ 歧义消除：每个 helper 给出签名 + 用法 + DOM 示例