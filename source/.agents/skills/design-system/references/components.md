# 组件清单与用法

> 来源：`app/static/styles.css` + `app/static/ui/*.js` + `app/static/core/*.js`。
> 所有组件遵循"内联样式禁用、状态 chip 不滥用告警色、emoji 禁用"。

## 1. 按钮 `.btn`

- 由 `app/static/core/dom.js` 生成 `.btn / .btn-{variant} / .btn-{size}`。
- 基础：控件圆角 `6px`、`font-weight: 600`、内联 flex、gap 6px。
- 尺寸：`.btn-sm`(6px 12px / 13px)、`.btn-md`(9px 16px / 14px)、`.btn-lg`(12px 22px / 16px)。
- 变体：`.btn-primary`（纯色 `--accent-strong`，白字）、`.btn-secondary`、更多见 styles.css。
- 焦点：`:focus-visible` 必须 `outline: 2px solid var(--accent-strong); outline-offset: 2px`。
- 禁用：`.btn:disabled` opacity 0.55。
- pill 只用于状态和短分段选择，不用于普通按钮或一级导航。

## 2. 数字指标卡 `.metric` / `.metric-box`

- `.metric`：卡片式大数字。`.metric span` 标签（13px/600/`--muted-strong`）、
  `.metric strong` 数值（30-38px/600/`-0.05em`/tabular-nums）。
- 变体：`.metric-accent` / `.metric-sand` / `.metric-slate` / `.metric-danger`。
- `.metric-box`：紧凑小数字卡。`strong` 18px/`-0.03em`/tabular-nums。
- 网格：`.metric-grid` / `.metric-grid-compact` / `.metric-box` 网格布局。

## 3. 状态 chip

- 语义色矩阵见 `references/tokens.md` §6——**chip 颜色必须匹配语义，文字必须冗余说明**。
- 方向 chip 用 `chipToneForDirection()` 派生 bull/bear/neutral（system 卡分支）。
- 禁止：用 Neutral 灰色统一渲染所有"已确认"chip 而不读 direction。

## 4. App Shell

- 模板唯一 Shell：`.app-sidebar` + `.app-topbar` + `#page-root`。
- 页面事实由 `main.js` 的 `PAGE_META` 派生，不得另建标题/路由映射。
- 页面使用 `setRoot(content, { layout })`；上下文用 `updatePageContext()`。
- 桌面侧栏 `216px`，可折叠为 `64px`；窄屏侧栏变为 overlay。
- 证据、风险、来源不得放入全站占位栏；应进入相关页面的图表侧栏、详情面板或按需抽屉。
- 导航抽屉必须支持 scrim、Escape、焦点锁定与焦点恢复。

## 5. 卡片 `.card` / `.panel`

- `.card`：`--surface-elevated`、1px `--border`、10–14px 圆角、极轻阴影。
- `.hero-card`：padding `28px 30px`。
- 普通内容区禁止普遍 blur 和无意义 hover 抬升；只读面板保持稳定。

## 6. 表格

- `th`: 12px / 700 / `0.08em` / uppercase / `--muted-strong`；sticky thead（`.table-wrap` 等滚动容器内生效）。
- `td`: `--ink` / **tabular-nums**（2026-08-11 落地）/ padding `15px 16px`。
- `tbody tr:hover`: `rgba(15,118,110,0.05)`。
- 密集表：`.etf-dense-table`、`.etf-combined-table`、`.monitoring-observation-table`。
- **可选改造（Mercury 借鉴，未做）**：表头 13px/400/0.1px/非大写。

## 7. 下拉（禁止原生 `<select>`）

- 全站用 `app/static/ui/dropdown.js` 的 `mountDropdown`。
- 静态守卫：`tests/test_no_native_select_remaining.py` 禁止任何 `<select` 字面量回归。

## 8. 抽屉 / 弹窗

- 动效必须用 `--ease-drawer`（`cubic-bezier(0.32,0.72,0,1)`）+ `--dur-drawer`(240ms)。
- 详情抽屉状态隔离：打开 A 项不应残留 B 项状态（audit §6.5）。

## 9. 图表 `app/static/ui/charts.js`

- 颜色读取 `getComputedStyle(:root)` 的 `--chart-*` token（见 tokens.md），失败时用内置 fallback。
- K线 wick 用 `--direction-up #16a34a` / `--direction-down #dc2626`（高饱和，仅图表）。
- tooltip 深色底（`--chart-tooltip-bg rgba(21,35,42,0.92)`）——与页面浅色对比，保留。
- **tooltip 键盘焦点触发缺失**（audit §6.4 P1-A11Y）——新 tooltip 必须支持键盘焦点。

## 10. 空态 / 加载态

- 空态用虚线 dashed 卡片上下排版（BTC 衍生品教训）。
- 不允许用"仍在 loading"通用 class 渲染 warming shell——必须渲染稳定页面结构。

## 11. 禁止清单（历史教训）

| 禁止 | 原因 | 守卫 |
|---|---|---|
| `<select` 字面量 | 原生下拉割裂设计语言 | `test_no_native_select_remaining.py` |
| emoji 当系统/状态符号 | 跨平台渲染不一致 | `tests/a11y_scan.py` 静态部分 |
| 内联 style 手写图形 | 无法走 token | `tests/css_audit.py` |
| 用 curl 代替 Playwright 验证 | HTTP 200 不代表页面渲染正确 | AGENTS.md §六.1 |
| 模板引外部 CDN | 慢 CDN 阻塞 DOMContentLoaded | 统一 `loadScriptOnce` |
| 只改 A 页不验 B 页 | SPA 共享依赖会跨页回归 | `verify_pages.py` 全量 |
