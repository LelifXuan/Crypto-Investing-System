# Strategy / Market Operation 卡片 UI 修正 Spec（2026-07-31）

> 本 spec 由用户截图驱动，针对 `/strategy-page` 详情抽屉内的 `跨维度市场作战图`（MARKET OPERATION section，6 张维度卡）的视觉问题做修正。**不动 JS、不动业务逻辑、不动数据 schema**——纯 CSS 改写 + 1 个 SVG chevron 注入。

| 项 | 内容 |
|---|---|
| Spec 日期 | 2026-07-31 |
| 解决对象 | `app/static/pages/strategy/renderMarketOperation.js`（仅 markup 视觉部分）+ `app/static/styles.css`（仅 `.strategy-*` 选择器子集）|
| 范围 | 不触数据获取 / 业务逻辑 / 详情面板路由 / 其他详情卡片 |
| 依据 | 用户 17:38 上传截图 1+2（5+5=10 截图覆盖 overview / detail 抽屉）|

---

## 1. 现状与问题

### 1.1 Grid 宽度不整齐
- **观察**：截图 1 显示 5 张卡片分为 3+2；上半 3 张各 ~30% 屏宽，下半 2 张各 ~50% 屏宽——视觉上"粗 / 细"对立。
- **根因**：`styles.css:9491-9501` 的 `.strategy-v2-grid.five` 使用 `repeat(auto-fit, minmax(280px, 1fr))`。
- **推断**：在 900px 面板宽下，280px floor 装得下 3 列；auto-fit 把第 4 张换行到第 2 行后，**只放 2 张时被强制拉宽到 1fr**，造成宽度不均。
- **影响**：6 张维度卡因布局抖动给读者"卡片之间无关联"的错觉，违背"作战图"语义。

### 1.2 summary 信息层叠过紧
- **观察**：eyebrow（10px 小写 letterspaced）+ 强字标题（18px）+ 状态文字（12px）+ 含义段落（14px）4 段文字紧密堆叠，靠 margin 8 / 12 区分。
- **根因**：`.strategy-operation-card-title { display: flex; flex-direction: column; gap: 4px }` 仅给 title row 内部 4px gap；上下节之间无视觉锚点。
- **影响**：扫视时需仔细分辨"哪一句是方向 / 哪一句是置信"。

### 1.3 详情段无节奏
- **观察**：截图 1/2 显示打开 detail 后，"关键位置 / 数据覆盖 / 数据来源 / 策略影响 / 下一步 / 本轮缺失" 6 段文本全部贴在一起，`strong` 标签 + 内联文本，无视觉分组。
- **根因**：`.strategy-operation-card-detail p` 没有任何间距或分隔线规则。
- **影响**：阅读 detail 时无法快速扫描层级。

### 1.4 evidence 列表默认 bullet
- **观察**：截图右侧"● 关键位置：..."列表用浏览器默认黑色实心圆点。
- **根因**：`<ul>` 无 list-style override。
- **影响**：与卡片整体的米色调不协调。

### 1.5 链接语义不明
- **观察**：截图底部的"点击查看本类别证据与缺失项"是青色加粗 `<small>`。
- **根因**：源代码把它做成 `<small>` 标签，没有 `<a href>` 也没有视觉上的箭头。
- **影响**：用户不知道这是一个触发折叠的 affordance。

---

## 2. 目标

| # | 目标 | 验证方式 |
|---|---|---|
| 1 | 5-6 张卡始终等宽（3 列 + 自动 wrap 2 列 + 单列）| Playwright bounding rect 全行宽差 ≤ 2px |
| 2 | summary 信息层级清晰：eyebrow / 方向主标题 / 状态 chip / 含义 4 段视觉锚点明确 | 截图对比 §1.2 |
| 3 | detail body 6 段有清晰分隔与节奏 | 截图对比 §1.3 |
| 4 | evidence 列表用 tone 化 bullet，不用浏览器默认 | 截图对比 §1.4 |
| 5 | 折叠 affordance 用 ▶ SVG + hover 下划线 | 截图对比 §1.5 |
| 6 | tone 颜色：BULLISH / BEARISH / NEUTRAL 主标题按语义着色 | DevTools computed style |

---

## 3. 设计

### 3.1 Grid — 强制 3 列

```css
.strategy-v2-grid.five {
  /* 2026-07-31: switched from auto-fit to fixed 3 cols so the 5-card
   * case renders as 3+2 with all 5 cards equal width. On panels
   * < 720px, fall back to 2 cols; on < 480px to 1 col. */
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 960px) {
  .strategy-v2-grid.five {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
  .strategy-v2-grid.five {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

### 3.2 Summary — 4 段视觉锚点

每个 summary 内部 HTML 不变；纯 CSS 改：

```css
.strategy-operation-card > summary {
  min-height: 220px;
  padding: 20px 22px 18px;
  cursor: pointer;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: var(--surface-glass);
  backdrop-filter: var(--blur-soft);
  border-radius: 12px 12px 0 0;     /* closed state: top rounded */
  transition: background 160ms ease;
}
.strategy-operation-card > summary:hover { background: var(--surface-elevated); }
.strategy-operation-card[open] > summary { border-radius: 12px 12px 0 0; }

/* Layer 1: eyebrow */
.strategy-operation-card > summary > .eyebrow {
  margin: 0;
  color: var(--muted);
  letter-spacing: 0.18em;
}

/* Layer 2: direction row — large + tone color + chevron SVG */
.strategy-operation-card-title {
  display: flex;
  flex-direction: row;            /* 横向：方向 + 右侧 chevron */
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 0;
}
.strategy-operation-card-title strong {
  font-size: 28px;                 /* 28px, was 18px */
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  white-space: nowrap;
  /* tone-aware color via existing structure:
   * .strategy-operation-card[data-tone="bull"] / bear / neutral  */
}
.strategy-operation-card[data-tone="bull"]   .strategy-operation-card-title strong { color: var(--bullish-strong); }
.strategy-operation-card[data-tone="bear"]   .strategy-operation-card-title strong { color: var(--bearish-strong); }
.strategy-operation-card[data-tone="neutral"] .strategy-operation-card-title strong { color: var(--muted-strong); }

/* Layer 3: confidence chip (replace plain text) */
.strategy-operation-card-title span {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(91, 138, 131, 0.08);
  color: var(--accent-strong);
  white-space: nowrap;
}

/* Layer 4: meaning */
.strategy-operation-card > summary > p:not(.eyebrow) {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--ink);
}
.strategy-operation-card > summary > small {
  color: var(--accent);
  font-weight: 600;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: auto;
}
.strategy-operation-card > summary > small::before {
  content: "";
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 4px solid currentColor;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  transition: transform 160ms ease;
}
.strategy-operation-card[open] > summary > small::before {
  transform: rotate(90deg);
}
```

**`data-tone` 属性**需要在 renderMarketOperation.js 里给 `<details>` 元素加上 `data-tone` 属性（基于 direction：BULLISH→bull、BEARISH→bear、NEUTRAL→neutral）。这是 **唯一** 一处 markup 改动。

```js
// in renderResolutionOperationCard:
const tone = direction === "BULLISH" ? "bull" : direction === "BEARISH" ? "bear" : "neutral";
return `
  <details class="strategy-v2-card strategy-operation-card" data-tone="${tone}">
    ...
  </details>
`;
```

### 3.3 Detail body — 分隔与节奏

```css
.strategy-operation-card-detail {
  padding: 18px 22px 22px;
  border-top: 1px solid var(--border-glass-soft);
  display: grid;
  gap: 12px;
}
.strategy-operation-card-detail dl {
  margin: 0;
  display: grid;
  gap: 10px;
}
.strategy-operation-card-detail dt {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}
.strategy-operation-card-detail dd {
  margin: 0 0 4px 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink);
}
.strategy-operation-card-detail ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.strategy-operation-card-detail ul li {
  position: relative;
  padding-left: 16px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink);
}
.strategy-operation-card-detail ul li::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 0.6em;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.5;
}
```

`renderMarketOperation.js` 中 detail body markup **不变**——`<p>` 与 `<ul>` 与 `<strong>` 仍可用；新 CSS 对 `<strong>` 加 padding-left 的 label 样式即可。但为了语义清晰（label-value dl），最小修改建议把 `<p><strong>关键位置：</strong>...</p>` 改为 `<div><span class="op-detail-label">关键位置</span><span class="op-detail-value">...</span></div>`——**这是 markup 改动**。

**最小方案**：保持 `<p><strong>` 结构，给 CSS 加新规则：

```css
.strategy-operation-card-detail p {
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border-glass-soft);
}
.strategy-operation-card-detail p:last-of-type {
  border-bottom: 0;
  padding-bottom: 0;
}
.strategy-operation-card-detail strong {
  display: inline-block;
  min-width: 80px;
  margin-right: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}
```

不需改 markup。

### 3.4 Tone 颜色矩阵（语义 → 颜色）

| Tone | 主标题 color | evidence bullet | 主标题 bg-soft（hover / open）|
|---|---|---|---|
| bull | `var(--bullish-strong)` = `#466f6a` | `var(--bullish)` 50% | `rgba(91,138,131,0.10)` |
| bear | `var(--bearish-strong)` = `#8c5d40` | `var(--bearish)` 50% | `rgba(176,117,88,0.10)` |
| neutral | `var(--muted-strong)` = `#5e6a78` | `var(--neutral)` 50% | `rgba(125,136,147,0.10)` |

依赖既有 token（已在 `:root` 中），无需新加 token。

### 3.5 折叠 affordance

`<small>` 改为内联链接式样 + 内联 SVG chevron：

- **关闭态**：`▶ 展开本类别证据与缺失项`（青色 + bold）
- **打开态**：chevron 旋转 90° → `▼ 收起证据与缺失项`（保持 CSS `transform: rotate(90deg)` 即可）

---

## 4. 文件改动清单

| 文件 | 改动 |
|---|---|
| `app/static/pages/strategy/renderMarketOperation.js` | `renderResolutionOperationCard` 在 `<details>` 上加 `data-tone="${tone}"` 属性（一行 markup 改动）|
| `app/static/styles.css` | 替换 `.strategy-operation-card` / `.strategy-v2-grid.five` / `.strategy-operation-card-title` / `.strategy-operation-card-detail` 相关规则；新增 `.strategy-operation-card[data-tone="..."]` 选择器 |
| `tests/screenshots/strategy-market-operation-redesign/` | 4 张截图（关闭态 1440 / 打开态 1440 / 1440 等宽验证 / 1366 2 列降级）|

**不动**：
- 详情抽屉布局（`renderDetailPanel.js`）
- 其他详情卡片（execution / risk / overview / evidence / trade-plans）
- 数据 schema / API / 图表

---

## 5. 测试矩阵

| 类型 | 内容 |
|---|---|
| 静态守卫 | `tests/test_strategy_market_operation_card.py`：① grid 是 3 列 ② `data-tone` 在 markup 中 ③ tone CSS 选择器存在 ④ bullet 是 SVG / pseudo-element（不是 `list-style: disc`）|
| 运行时 | `tests/_visual_strategy_market_operation.py`：Playwright 拉 `/strategy-page` → 等 detail 抽屉 → 测 5 张 summary 卡的 `offsetWidth` 全部相等（差 ≤ 2px）→ 截图 |
| L2 回归 | `tests/verify_pages.py` 全 11 页过 0 fail |

---

## 6. 验收标准

| # | 标准 |
|---|---|
| 1 | 5 张卡宽度差 ≤ 2px（截图） |
| 2 | summary 4 段视觉锚点明确：eyebrow muted / 方向大号 tone-color / 状态 chip / meaning 默认色 |
| 3 | detail body 6 段有 dashed 分隔 |
| 4 | evidence bullet 是 SVG 圆点 tone 色（不是浏览器默认 disc）|
| 5 | 折叠 affordance ▶ SVG + hover 下划线 + 打开态旋转 90° |
| 6 | 全部验证脚本 PASS + verify_pages 不引入新 fail |

---

## 7. 风险

| # | 风险 | 缓释 |
|---|---|---|
| R-1 | 改 `data-tone` markup 字符串，可能影响其他静态守卫 | 仅加 1 个属性、值集合有限 |
| R-2 | grid 改 3 列 → 窄屏 5 张 3+2 比 auto-fit 多一行 | 加 `@media (max-width: 960px)` 降到 2 列 |
| R-3 | 改 tone-color 让 bull/bear 卡片颜色不同 → 用户原本理解 "卡只是数据载体" | 主标题 + tone 化不影响卡片背景/边框/形状，色彩克制 |

---

## 8. 实施顺序

按单 commit 一阶段执行：

| 阶段 | 内容 | commit 域 |
|---|---|---|
| 1 | grid 强制 3 列 + media query | `[config]` |
| 2 | summary 4 段层级 + tone-color 主标题 + chevron SVG + data-tone markup | `[frontend]` + `[config]` |
| 3 | detail body 分隔节奏 + evidence bullet pseudo-element | `[config]` |
| 4 | 截图 + Playwright 验证 + 静态守卫 | `[test]` |

每阶段独立可回滚。

---