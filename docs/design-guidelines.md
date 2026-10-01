# 交易系统研究终端设计手册

> 当前源码产品版本 V2.3.1、应用版本 2.3.1（现行策略语义更新至 2026-09-30）。以下 2026-08-31 页面迁移与验收数字为历史基线，保留当时应用版本 1.8.1 的记录。

## UI 2.0 P1 — ACCEPTED / FROZEN

2026-08-30：四页为 Monitoring、BTC、Events、Macro；P1 共享合同冻结，后续扩展须带回归测试。
验证：改动 JS `node --check`、改动 Python `py_compile`；Workbench/UI2/P1 合同 28 passed；
`python tests/verify_pages.py`：11/11 冷启动、10/10 SPA 通过，pageerror/console error/失败响应为 0。
截图由 `VERIFY_SCREENSHOT_DIR` / `WORKBENCH_SCREENSHOT_DIR` 输出到独立目录，不覆盖基准。
首次验证暴露的 BTC abort 后旧页面重绘与 timer 重启已修复并补测试，随后全量重跑通过。
P2 操作核心按 Command → Pin → Resize → URL 验收；这条记录描述 P1 冻结批次，V2.3 页面范围见下方迁移基线。

> 版本 3.5 · 冷灰 / 冷紫 / 蓝灰全站视觉基线（2026-09-09）
> 适用范围：`source/app/templates/page.html`、`source/app/static/styles.css`、`source/app/static/editorial.css`、`source/app/static/ui/` 与 `source/app/static/pages/`。

### V2.3 页面迁移基线（2026-08-31）

H0–H4 及最终同版软件门禁已通过：1986 passed、6 既有 skip、5 warnings，11/11 冷启动、10/10 SPA、8/8 压力场景。便携包独立验证与敏感清理状态见 `docs/ui2-page-migration-acceptance.md` 指向的外部交付记录。
当前 Workbench 页面为 Monitoring、BTC、Events、Macro、Analysis、Structure。
Analysis 保留指标意图跨上下文恢复；Structure 身份采用形态类型与 UTC 起始锚点，冲突拒绝独立选择。
Strategy 采用 ADR 0023：保留完整 Detail Panel，仅增加四个页面命令，不加入 Inspector/URL 恢复。
ETF、Gold 不迁移；Knowledge 保持 reference layout。不是完整 P2 Complete。
静态子模块使用协商缓存；旧版首次升级执行 Ctrl+Shift+R 一次。当时 UI 验收标识 V2.3 与应用版本 1.8.1 分开记录。
主基线 2560×1440，2560×1600 仅高屏复核；Inspector ≤1180px drawer、≤900px bottom sheet 不变。
静态 Structure 图表 surface 禁止 hover 位移；鼠标 click 与 PointerEvent 使用相同 CSS 像素口径，布局重排不能把静止鼠标解释为新的 preview 意图。
2026-08-31 发布卫生补验：2013 passed、4 skip、0 warnings；11/11 冷启动、10/10 SPA 与 8/8 压力场景通过。指南关闭必须以 `hidden` 配合 `display:none` 离开布局及可访问树，不以透明度代替隐藏。详见 `docs/ui23-release-hygiene.md`；不扩大页面范围或业务计算。

---

## 0. 手册定位与使用方式

本手册同时记录三类信息：

- **现行规范**：新功能和修复必须遵守的设计规则。
- **实现基线**：2026-08-20 浏览器审查与代码审查确认的当前生效样式。
- **审查债务**：当前系统仍存在、但本次仅记录而不扩大修改范围的问题。

约束优先级：

1. 根目录 `AGENTS.md` 的工程、验证、数据正确性和可访问性约束；
2. 本手册的视觉语言、组件模式和页面结构；
3. `source/docs/design-guidelines-legacy.md`（2026-08-27 V3.2 归档）中的旧工程细则；本节起以本手册为唯一权威；
4. 页面局部样式。

修改 UI 时必须先确认本手册是否已有对应模式。没有模式时，先补充组件规范，再新增实现；不要从单个页面复制一套近似组件。

---

## 1. 产品设计方向

### 1.1 Design Read

**面向专业研究与配置决策的高密度市场终端，采用克制的编辑部式信息层级、低饱和冷灰白表面、深冷紫操作语言和蓝灰配套色，重点突出数据状态、时间、来源和可执行边界。**

设计旋钮：

| 旋钮 | 取值 | 含义 |
|---|---:|---|
| Variance | 4/10 | 页面有领域差异，但共享骨架和控件必须稳定 |
| Motion | 3/10 | 高频操作几乎无动画，抽屉和弹层保留短动画 |
| Density | 8/10 | 桌面研究终端优先，压缩装饰而不压缩可读性 |

### 1.2 核心原则

1. **结论先于装饰**：方向、置信度、数据时效和权限边界必须先于图形修饰出现。
2. **数据状态不是市场结论**：冷缓存、失败、缺失属于系统可用性，不得显示成看空或高风险判断。
3. **结构稳定**：加载、成功、降级和空态应共享同一页面骨架，避免内容跳动。
4. **一页一主任务**：页面可以高密度，但首屏必须能回答“当前状态是什么、下一步看哪里”。
5. **语义不只靠颜色**：状态同时使用文字、图标或形状；颜色只负责加速扫描。
6. **共享组件优先**：相同层级的按钮、下拉、折叠、状态底栏不得在不同页面重新设计。

### 1.3 明确不做

- 不做营销页式 hero、宣传口号、彩色渐变 CTA。
- 不使用 emoji 代替图标。
- 不用大面积告警色制造紧迫感。
- 不把所有内容都放进卡片；同一卡片内部优先用间距和 hairline 分隔。
- 不在终端界面展示内部 URL、异常栈、HTTP 状态或实现术语。
- 不执行下单；所有交易建议必须保留研究与权限边界。

---

## 2. 样式来源与令牌架构

### 2.1 当前级联关系

模板按以下顺序加载样式：

```text
styles.css       基础组件、页面历史样式、图表与动效 token
    ↓
editorial.css    当前应用外壳、最终视觉语义和页面级修正
    ↓
页面后置选择器   特定领域组件的必要变体
```

因此，颜色、圆角、阴影等同名变量的**最终生效值以 `editorial.css` 为准**。禁止只查看 `styles.css :root` 就更新设计文档。

### 2.2 三层令牌模型

新 token 按以下层级组织：

```text
Primitive：原始值，如冷灰、冷紫、蓝灰、间距 8px
    ↓
Semantic：用途，如 --accent、--border、--space-action
    ↓
Component：组件特例，如 --topbar-height、--glass-shadow
```

当前代码仍以语义 token 为主，primitive 与 component 层尚未完全拆分。新增组件不得继续扩张重复色值；优先复用语义 token，只有跨页组件才允许增加 component token。

### 2.3 命名规则

```text
--{category}-{role}-{variant}-{state}
```

推荐：`--text-secondary`、`--space-action`、`--chip-bullish-border`、`--button-primary-bg-hover`。

禁止：

- 以页面名命名通用颜色，如 `--gold-purple`；
- 以数值命名语义颜色，如 `--gray-217`；
- 在 HTML 或普通组件 CSS 中直接写新的十六进制颜色。

图表可以使用独立序列色，但应集中在 chart token 或单一 palette map 中，不能散落在各页面渲染函数。

---

## 3. 当前生效的视觉令牌

### 3.1 中性色与表面

| Token | 当前值 | 用途 |
|---|---|---|
| `--bg` | `#eef1f5` | 应用画布 |
| `--bg-strong` | `#e5e9f0` | 左侧导航背景 |
| `--surface` | `#f5f7fa` | 普通表面 |
| `--surface-elevated` | `#fbfcfe` | 卡片与实色浮层 |
| `--surface-muted` | `#edf0f5` | 弱化区、锁定态、标签背景 |
| `--ink` | `#211d2b` | 主文字 |
| `--text-secondary` | `#5f5968` | 描述、辅助标签 |
| `--text-tertiary` | `#746c7d` | 时间、缺失和低优先级信息；在当前两个主表面上的对比度为 4.89:1 / 4.68:1 |
| `--border` | `#d5dae2` | 标准边框 |
| `--border-strong` | `#c2c9d3` | 强分隔 |

这是“冷灰白表面 + 深冷紫主题色 + 蓝灰配套色”的研究终端。画布、导航、普通容器和浮层依靠明度区分层级，浅紫只用于低权重选中背景。

### 3.2 操作色与状态色

| 语义 | Token | 当前值 | 使用规则 |
|---|---|---|---|
| 主操作 | `--accent` | `#554a78` | 选中、强调、轻量交互 |
| 主操作加强 | `--accent-strong` | `#40365f` | 主要按钮、焦点、章节标识 |
| 按下 | `--accent-pressed` | `#312a4a` | active / 强 hover |
| 信息 | `--info` | `#3e6f9f` | 数据在线、快照、说明 |
| 看多 | `--bullish` | `#34745f` | 明确的市场方向 |
| 看空 | `--bearish` | `#a34f5f` | 明确的市场方向 |
| 警告 | `--warning` | `#9b6a25` | stale、degraded、受限 |
| 错误 | `--danger` | `#9d3f48` | 不可用、失败、阻断 |
| 中性 | `--neutral` | `#746e79` | 无方向或不适用 |

强制规则：

- 深冷紫只表达操作、选中和产品识别；蓝灰用于信息与辅助层级，二者都不替代看多/看空。
- 看多、看空不能用同一主题色色阶区分。
- `warning` 不是“市场风险高”的默认颜色，仅表达系统或执行层面的注意状态。
- K 线涨跌可使用更清晰的 `--direction-up` / `--direction-down`，但只限密集价格图。
- 页面画布与通用容器的环境光只允许使用中性灰或 `--info-*` 蓝灰；禁止用 warning、danger、bearish 或旧米棕色制造径向晕染。
- warning、danger、bearish 只能出现在与其语义直接对应的 chip、细边、图表序列或小范围提示内，不能成为卡片、空态、工具栏和整页背景。
- `missing`、`unknown` 与尚未完成计算的置信度统一显示为“待评估”或明确的数据阶段；不得渲染成红色、琥珀色或大号风险结论。

### 3.3 间距、圆角与阴影

| Token | 当前值 | 用途 |
|---|---:|---|
| `--space-inline` | 6px | 图标与文字 |
| `--space-action` | 8px | 同级操作 |
| `--space-control` | 12px | 表单与工具栏控件 |
| `--space-card` | 16px | 同组卡片 |
| `--space-section` | 24px | 页面大区块 |
| `--content-gap` | 24px | 页面内容容器间距 |
| `--canvas-gutter` | `clamp(20px, 1.5vw, 36px)` | 页面画布边距 |
| `--radius-card` | 10px | 紧凑次级卡片 |
| `--radius` | 14px | 标准卡片 |
| 玻璃浮层 | 18px | 抽屉、指南、tooltip |

阴影分三级：

- `--shadow-soft`：静态卡片；
- `--shadow-hover`：仅可交互卡片 hover；
- `--glass-shadow`：浮动玻璃层。

静态信息卡 hover 不上浮。只有链接卡、按钮卡或带 `data-pressable` 的卡片允许 `translateY(-1px)`。

---

## 4. 排版系统

### 4.1 字体

```css
--font-sans: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
--font-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
```

- Body：15px / 1.6；窄屏为 16px / 1.56。
- 数字、价格、百分比、时间使用 `font-variant-numeric: tabular-nums`。
- 等宽字体只用于代码、ID、固定宽度数值，不用于整段正文。

### 4.2 层级

| 层级 | 当前基线 | 用途 |
|---|---|---|
| Shell H1 | 20px / 600 | 顶栏中的唯一页面标题 |
| Page display | 32–40px / 700 | 少数 workbench 或参考页的内容导语，不承担文档 H1 |
| Section H2 | 24–28px / 700 | 页面一级内容区 |
| Compact section H2 | 18–20px / 700 | 数据治理、折叠栏、紧凑工具卡 |
| H3 | 16px / 700 | 卡片内分组 |
| Body | 15px / 400 | 正文与数据说明 |
| Control | 14px / 600 | 按钮、下拉、输入 |
| Eyebrow | 10px / 650 | 英文分类标签，0.14em 字距 |
| Caption | 10–12px | 时间、来源、状态补充 |

语义规则：

- `#app-page-title` 是文档中的页面 H1。
- `#page-root` 内的主要区块使用 H2，子分组使用 H3。
- 页面内大型导语如需 display 样式，优先使用 class，不再新增第二个 H1。
- 标题使用 `text-wrap: balance`，正文使用 `text-wrap: pretty`。

---

## 5. 全局应用外壳

### 5.1 左侧导航

- 桌面宽度 216px，折叠后 64px。
- 分组顺序固定为：研究、Crypto、配置、参考。
- 当前页必须同时使用背景、左侧指示线和文字权重表达选中态。
- 图标使用内嵌 SVG；折叠后保留可理解的 `aria-label`。
- 1180px 及以下切换为离屏抽屉，配套 scrim 和滚动锁定。（§13.2 #7 断点收敛后由 1279px 改为 1180px；正文与 §11 断点表一致）

### 5.2 全站顶栏

- 高度固定为 `--topbar-height: 64px`。
- `position: sticky; top: 0; z-index: 1000`，任何页面内容不得覆盖它。
- 结构顺序：移动端导航按钮 → 面包屑/页面标题 → 页面上下文 chip → 全局数据质量。
- 当前材质：Quiet Shell 高不透明 neutral surface、hairline divider，`box-shadow: none`、`backdrop-filter: none`。Glass 仅用于确有需要的 floating surfaces，不用于 Topbar 装饰。
- 尊重用户的透明度偏好；在 `prefers-reduced-transparency` 下提供实色降级。
- 程序化定位到区块时使用 `scroll-margin-top: calc(var(--topbar-height) + var(--space-card))`，避免标题被遮挡。

### 5.3 页面画布

```text
.app-main
├── .app-topbar
└── .app-workspace
    └── #page-root[data-layout]
```

- 页面宽度占满可用主区，禁止重新套一个固定宽度 app shell。
- `#page-root` 使用统一 `--canvas-gutter`。
- 页面根容器负责区块 gap；子卡片不各自堆叠 `margin-bottom`。
- 返回顶部按钮固定在安全区内，必须可键盘访问。

---

## 6. 页面布局家族

当前路由分成四类布局：

| Layout | 页面 | 结构重点 |
|---|---|---|
| `overview` | 监控总览、市场事件、宏观日历 | 状态概览 → 主要信息流/明细 |
| `analysis` | 技术指标、形态结构、BTC 衍生品 | 工具栏 → 图表/证据 → 结论 |
| `workbench` | AI 策略、A股 ETF、黄金配置 | 操作输入 → 结果 → 数据治理 |
| `reference` | 知识百科 | 目录/筛选 → 内容 → 参考轨道 |

页面不得因为领域不同就改变全局外壳、按钮层级和状态语义；差异应主要体现在内容结构和图表。

---

## 7. 共享组件规范

### 7.1 标准卡片

当前标准：

```css
background: var(--surface-elevated);
border: 1px solid var(--border);
border-radius: 14px;
box-shadow: var(--shadow-soft);
padding: clamp(20px, 1.4vw, 28px);
```

- 卡片本身不使用 backdrop blur；玻璃材质留给顶栏和浮层。
- 不嵌套完整卡片。内部区块使用背景微差、边线或 grid 分隔。
- `.section-head` 使用 16px gap，标题区与操作区同一视觉基线。
- 数据密集区允许紧凑 padding，但必须在同一组内一致。
- 页面根容器用 24px gap 分隔大区块，直接子区块不再叠加上下 margin；同组独立卡片用 16px gap。
- 图表卡片的标题与绘图区各自承担内边距，不再叠加通用卡片 padding。
- 通用卡片、图表壳、空态与摘要面板只使用 `--surface*`、`--border*` 和低强度 `--info-*`；不得保留旧暖米色或棕色边框的硬编码回退值。

### 7.2 按钮

| 类型 | 高度 | 样式 | 场景 |
|---|---:|---|---|
| Primary | 40px | 深紫实心、白字 | 刷新、生成、确认 |
| Secondary | 40px | 浅表面、标准边框 | 次级动作 |
| Compact | 38px | 14px / 600 | 工具栏与紧凑区 |
| Icon | 44×44px | 透明底、8px 圆角 | 导航、关闭、辅助动作 |

- 同一操作组只能有一个 primary。
- `:active` 使用 `scale(0.96)`；hover 只提升对比度或阴影。
- 必须逐项声明 transition property，禁止 `transition: all`。
- icon-only 按钮必须有 `aria-label`。
- 禁用态保留标签可读性，并通过 `disabled` 或 `aria-disabled` 表达。

### 7.3 Chip / Badge

Chip 只表达短状态、来源、方向或筛选，不承载完整句子。

| 类型 | 语义 |
|---|---|
| `chip-bullish-soft` | 偏多 |
| `chip-bearish-soft` | 偏空 |
| `chip-neutral` | 中性/不适用 |
| `chip-info` | 信息/已就绪 |
| `chip-warning` | 过期/降级/受限 |
| `chip-danger` | 失败/不可用 |
| `chip-translating` | 翻译处理中 |

规则：

- 同一状态在不同页面必须使用相同 tone。
- 不用紫色同时表示方向与选中。
- Chip 背景保持低饱和，正文对比度满足 WCAG AA。

### 7.4 下拉菜单

全站统一使用 `app/static/ui/dropdown.js` 的 `mountDropdown`，禁止原生 `<select>`。

| Size | 高度 | 字号 | 圆角 |
|---|---:|---:|---:|
| Compact | 38px | 14px | 6px |
| Default | 40px | 14px | 6–12px，按所在组件统一 |

- 同一工具栏内使用等宽 grid，trigger `width: 100%`。
- 长标签在 trigger 截断，在 popover 显示完整内容。
- 键盘支持 Arrow、Enter、Escape；焦点返回触发器。
- Popover 不得被卡片 `overflow` 裁切。
- Trigger 与 popover 统一使用 `--surface` 冷灰表面、`--ink` 深色文字；禁用态使用 `--surface-muted` 与可读的 `--text-secondary`。
- 普通筛选栏上下 padding 为 12px，控件保持 38–40px；不得通过扩大控件高度填满容器。

### 页面指南与紧凑概览

- 页面使用指南入口位于左侧导航底部、系统状态上方；收起导航后只显示描边图标，保留可访问名称。
- 桌面指南面板位于侧栏右侧，下边距至少 24px；宽度最多 615px，高度最多 680px，且不越过顶栏和视口安全区。移动端改为视口内浮层。
- 指南关闭时不参与布局和键盘导航；Escape 关闭后焦点返回入口，SPA 离开时移除面板与监听器。
- 宏观日历折叠概览在桌面保持 80–88px 高，标题 20px；窄屏允许内容换行，不强制固定高度。
- 黄金配置的信息区为等宽双列，六张图表按两列三行排列；900px 及以下恢复单列，图表跟随容器宽度调整。

### 7.5 折叠横栏

唯一实现入口：`source/app/static/ui/disclosure.js`。页面可以保留私有 class 作为事件 hook，但不得再用它声明按钮的颜色、尺寸、圆角、阴影或 chevron。

合法变体：

| Variant | 结构 | 规格 | 使用场景 |
|---|---|---|---|
| `section` | 横栏右侧独立按钮 | 40px 高、最小宽度 104px、14px / 600、6px 圆角 | 日历、监控分组、证据与规划区块 |
| `section-compact` | 横栏右侧独立按钮 | 36px 高、最小宽度 82px、12.5px / 600；粗指针命中区至少 44px | 知识百科紧凑章节 |
| `inline` | 整行标题即触发器 | 最小高度 44px、中性表面、左右分布 | AI 详情审计、知识指南内部明细 |

标准 anatomy：

```text
button.disclosure-toggle[aria-expanded][aria-controls]
├── span.disclosure-toggle__label
└── span.disclosure-toggle__chevron[aria-hidden=true]
    └── svg
```

状态规则：

| 状态 | 背景 / 边框 | 文字与图标 | 动效 |
|---|---|---|---|
| Default | `--accent-strong` | 白色 | 无 |
| Hover | `--accent-pressed` | 白色 | 颜色与阴影 180ms |
| Active | 同 hover | 白色 | `scale(.96)` / 120ms |
| Focus | 默认 | 白色 | 2px `--accent-strong` outline |
| Disabled | `--surface-muted` / `--border` | `--text-tertiary` | 无阴影、不可操作 |

- 同一横栏层级必须使用同一 variant；不得因内容不同重新设计按钮。
- 同一个按钮负责展开与收起并固定在横栏右侧，位置不得随状态变化。
- 文案使用“展开/收起 + 对象”，如“展开规划”“收起日历”；对象明确时可只写“展开/收起”。
- 折叠时 chevron 朝右，展开时朝下；chevron 只作辅助，不能替代文字。
- 使用 `aria-expanded`，受控内容使用 `hidden`；两者必须在同一次状态更新中同步。
- 默认状态由信息频率决定：低频明细默认折叠，高频核心结论可默认展开。
- `prefers-reduced-motion` 下取消旋转过渡，但必须保留最终方向。
- 禁止把 warning、bullish 或 bearish 色用于折叠按钮；按钮表达操作，不表达数据或市场状态。

### 7.6 磨砂玻璃面板

适用：全站顶栏、页面使用指南、tooltip、AI 策略详情抽屉。

```css
background: var(--glass-bg);
border: 1px solid var(--glass-border-outer);
outline: 1px solid var(--glass-edge);
outline-offset: -1px;
box-shadow: var(--glass-shadow);
backdrop-filter: blur(var(--glass-blur));
-webkit-backdrop-filter: blur(var(--glass-blur));
```

当前 token：

| Token | 值 |
|---|---|
| `--glass-bg` | `rgba(255,255,255,0.18)` |
| `--glass-bg-deep` | `rgba(255,255,255,0.32)` |
| `--glass-tint` | `rgba(255,255,255,0.10)` |
| `--glass-blur` | `28px` |

禁止 frosted-on-frosted。玻璃面板内的子区域使用 `--glass-tint` 和 hairline，不再增加 backdrop-filter。必须提供 reduced-transparency 实色降级。

### 7.7 数据治理底栏

黄金配置页是当前标准参考；ETF 与 BTC 衍生品应复用同一结构语义。

```text
左侧标题/就绪度 | 数据源 1 | 数据源 2 | 数据源 3 | 快照时间
```

- 外层是一张紧凑 ledger，不拆成多张悬浮卡。
- 左侧：`minmax(220px, .72fr)`；右侧：等宽数据源网格。
- Header：16×20px padding，`--surface-muted`。
- Item：最小高度 72px，12×14px padding，hairline 左分隔。
- 7px 状态圆点 + 3px 扩散环；fresh/info、degraded/warning、missing/tertiary。
- 1180px 以下上下堆叠，720px 以下两列。
- 新实现应抽取共享 governance 组件，不继续复制 `gold-*`、`etf-*`、`btc-*` 三套样式。

### 7.8 表格

- 表头 sticky 时必须计算顶栏偏移，不允许被 64px 顶栏遮挡。
- 文字列左对齐，数值列右对齐，状态/短代码列居中。
- 数字使用 tabular-nums；单位写在列头或数值旁，不混用。
- 空态占据完整表格区域并说明原因与恢复方式。
- 窄屏优先允许横向滚动；禁止压缩到逐字换行。

### 7.9 图表

- 图表必须有标题、时间范围、数据来源和更新时间。
- tooltip 使用统一数字格式；时间统一 UTC 或明确显示时区。
- 颜色不能作为唯一编码，必要时叠加线型、点型或标签。
- series 颜色集中管理；普通组件色不得直接当图表多序列 palette。
- Canvas 必须有可访问名称，加载前保留稳定高度。

### 7.10 加载、空态与降级

- Skeleton 必须与最终内容结构等高，避免 CLS。
- warming shell 立即渲染稳定页面结构，不使用会被实例检查识别为永久 loading 的通用 class。
- 有 last-known-good 时先显示旧快照并标注 stale，再后台刷新。
- 无数据时说明“为什么没有”和“下一步如何恢复”，不显示伪造的 0。
- 错误状态不覆盖仍可阅读的旧结果。

### 7.11 AI 策略机会矩阵与机会排序

矩阵固定呈现 5 个品种 × 周线、日线、4H 的 15 个**扫描位置**。其中通过完整交易门槛的单元格构成机会发布面；右侧排序只比较这些已成立的机会，不发布待复核的方向倾向。

- 矩阵只高亮后端明确标记为 `qualified` 的可执行机会；前端不得自行根据颜色、方向或置信度推断是否准入。
- 每格的交易方向和计划必须取自该 `instrument × timeframe` 的独立周期决策；周线交易用日线、日线交易用 4H、4H 交易用 1H 确定执行价位。禁止把标的级全局结论复制到三个交易周期。
- 已通过门槛的格子显示做多或做空并可打开对应详情。已完成计算却未通过门槛的格子中性显示“无机会”，可打开对应周期的判断依据，但不得呈现可执行价位或进入机会排序；缺失或过期的输入分别显示“数据准备中”或“数据更新中”，不可点击。方向倾向、等待确认、旧快照均不得伪装成可交易机会。
- 机会排序只接收与矩阵同源、同周期且已通过门槛的项；保留置信度、综合评分和风险收益比以比较已成立机会。没有合格项时明确显示空态。
- 矩阵准入同时验证数据新鲜度、方向、对应执行周期的入场/止损/目标几何、盈亏比、杠杆预算、仓位权限及显式冲突；任一门槛失败时不得显示多空强调色、价位或可点击详情。
- 准入门槛属于后端策略契约，应通过结构化字段和原因码传递；前端不得增加临时字符串匹配或另设一套判断。

---

## 8. 反馈与状态语言

| 系统状态 | UI 表达 | 禁止表达 |
|---|---|---|
| fresh / live | 蓝色圆点 + “已就绪/实时” | “偏多” |
| stale / degraded | 琥珀圆点 + 时间 + 降级说明 | 大面积橙色背景 |
| missing | 灰色圆点 + 缺失来源 | 数值 `0.00` |
| error | 红色小范围提示 + 恢复动作 | 内部异常栈 |
| refreshing | 保留旧数据 + 局部进度 | 整页空白 spinner |

市场方向独立使用 bullish / bearish / neutral。系统可用性绝不改变市场方向 tone。

置信度与数据质量使用紧凑 chip 或一行状态说明。缺失值显示“待评估”，只有后端明确返回低置信度结论时才显示“不足”；两者都使用信息蓝或中性灰，不使用看空红色，也不放大为首屏主标题。

文案应短而具体：

- 好：`快照过期 18 分钟，正在刷新；当前展示上次可用结果。`
- 差：`数据异常。`

---

## 9. 动效与微交互

当前 motion ladder：

| Token | 时长 | 场景 |
|---|---:|---|
| `--dur-press` | 120ms | 按下反馈 |
| `--dur-hover` | 180ms | hover、颜色和小浮层 |
| `--dur-elevate` | 220ms | 卡片轻量抬升 |
| `--dur-drawer` | 240ms | 抽屉与侧栏 |

规则：

- 高频操作不使用进入动画。
- 进入/退出用 ease-out；屏内形态变化用 ease-in-out。
- 只动画 `transform`、`opacity`、颜色、边框和阴影。
- 动画必须可中断；不得使用 bounce / elastic easing。
- `prefers-reduced-motion` 下压缩到 1ms 或 0.01ms，最终状态仍完整。

---

## 10. 可访问性

- 动作用 `<button>`，导航用 `<a>`；禁止 `<div onClick>`。
- 所有控件有可见或程序化 label。
- icon-only 按钮有 `aria-label`，装饰 SVG 有 `aria-hidden="true"`。
- focus 使用 `:focus-visible`，2px `--accent-strong` outline；禁止无替代的 `outline: none`。
- 异步状态区域使用 `aria-live="polite"`，避免每个数值都单独播报。
- 页面提供 skip link 到 `#page-root`。
- 折叠使用 `aria-expanded`，抽屉打开后管理焦点并阻止背景滚动。
- 触控命中区至少 44×44px；紧凑视觉控件可用透明 padding 扩大命中区。
- 文字与背景满足 WCAG AA；不能只通过颜色传达状态。
- 不限制页面缩放，不阻止 paste。

---

## 11. 响应式规范

### 11.1 验证视口

- 主视觉基线：**2560×1440（16:9）**。
- 必测：2560×1440、1280×720、768×1024、390×844。
- 高屏 cross-check 可补充 2560×1600，但不得替代 2560×1440 基线。

### 11.2 关键断点

| 断点 | 行为 |
|---:|---|
| 1599/1500px | 高密度工具栏和图表网格开始收敛 |
| 1180px | 固定侧栏切换为抽屉；隐藏全局质量文字 |
| 1180/1100px | 多列治理区、分析区改为堆叠 |
| 980/900px | 两列内容与参考侧轨变单列 |
| 767/720px | 移动端顶栏、单列卡片、16px gutter |
| 560px | 紧凑工具栏、章节按钮和安全区调整 |

规则：

- Grid 优先，不用 `calc(33% - ...)` 维持列宽。
- 外层用 `min-width: 0`，长文本用 truncation 或合理换行。
- 数据表在窄屏横向滚动；页面本身不得产生横向滚动。
- 高度使用 `100dvh` 或显式 cap，避免移动浏览器地址栏跳动。
- 固定按钮使用 `env(safe-area-inset-*)`。

---

## 12. 页面索引

| 页面 | 路由 | Layout | 关键模式 |
|---|---|---|---|
| 监控总览 | `/monitoring-page` | overview | 宏观概览、分类折叠、缺口说明 |
| 市场事件 | `/market-events-page` | overview | 全宽信息流、解锁日历、翻译状态；事件卡直接呈现完整摘要与关联品种，不使用重复的右侧详情栏 |
| 宏观日历 | `/macro-calendar-page` | overview | 月历、事件明细、状态底栏 |
| 技术指标 | `/indicators-page` | analysis | 标的切换、指标快照、图表网格 |
| 形态结构 | `/structure-page` | analysis | 工具栏、结构图、形态证据 |
| BTC 衍生品 | `/btc-derivatives-page` | analysis | 五列筛选、衍生品图表、数据治理 |
| AI 策略 | `/strategy-page` | workbench | 机会矩阵、决策卡、玻璃详情抽屉 |
| A股 ETF | `/ashare-etf-page` | workbench | 策略模拟、执行计划、数据治理 |
| 黄金配置 | `/gold-allocation-page` | workbench | 今日动作、配置工作台、数据治理 |
| 知识百科 | `/knowledge-page` | reference | 目录轨、搜索、章节折叠、指南 |

---

## 13. 2026-08-20 全面审查结论

### 13.1 已形成的系统优势

- 十个页面已经统一到同一 sidebar + topbar + page-root 外壳。
- 三类主布局和知识参考布局已在路由 metadata 中明确。
- 原生 `<select>` 已清除，十页抽查均使用自定义 dropdown。
- 全站顶栏、页面指南和 AI 抽屉已经形成一致的玻璃材质。
- 状态色已经从主操作紫色中分离出 info / bullish / bearish / warning / danger。
- 主要页面在 1280×720 抽查中未出现横向溢出，知识百科除外。
- 折叠、数据治理和返回顶部均已有明确的共享视觉方向。

### 13.2 需要治理的设计债务

按优先级排序：

1. **双样式源冲突**：`styles.css` 与 `editorial.css` 均声明全局 token 和组件；最终效果依赖加载顺序。应逐步迁移为 primitive → semantic → component 三层文件，保留单一最终定义。
2. **页面标题语义不一致**：应用顶栏已有 H1，但 BTC 衍生品、AI 策略、黄金配置、知识百科内容区仍存在额外 H1。应改为 display class + H2 结构。
3. **治理底栏重复实现**：gold / ETF / BTC 使用三套前缀相近的 CSS。应抽成共享 `data-governance` 组件与少量领域 slot。
4. **图表色散落在 JS**：技术指标、形态结构、衍生品和黄金页面存在大量硬编码 series 色。应统一到 chart palette token，并为每个序列定义用途。
5. **知识百科横向溢出**：1280×720 浏览器抽查发现 document 宽度超过 viewport。优先检查 1279px 下 `knowledge-workspace` 的 220px + `--reading-measure` 组合、工具栏和长内容的 `min-width`。
6. **局部组件仍覆盖全局视觉**：知识章节卡曾使用散落的旧靛蓝色值，无法随主题一起调整。
   *2026-09-08*：已收敛。局部高亮统一使用蓝灰 `--info-*` token，与冷紫主题色分工；详见 §3.2 与 `tests/test_local_component_color_tokens.py`。
7. **断点过多**：当前存在 1500、1279、1180、1100、980、900、780、767、720、700、640、560 等近邻断点。后续应收敛为壳层、内容层和移动层三组，而不是继续新增。
   *2026-08-27 V3.2*：已收敛。17 个 width 值收为 6 组：`560` (mobile-s) / `720` (mobile-l) / `900` (tablet) / `1180` (small-desktop) / 默认 (desktop, 2560×1440 基线) / `1500` (wide-desktop)；`520` 作为 mobile-s 内部 extreme sub-tier 保留作扩展点；详见 §11 与 `tests/test_responsive_breakpoints_consolidated.py`。
8. **文档分叉**：根手册与 `source/docs/design-guidelines.md` 曾出现调色板和 2560×1600/1440 视口冲突。后续应以本手册为视觉基线，并逐步把旧文件收敛为工程检查清单。
   *2026-08-27 V3.2*：已收敛。`source/docs/design-guidelines.md` 重命名为 `source/docs/design-guidelines-legacy.md` 并加废弃 banner；本章末新增 §14.5 列出本轮剩余债务。

已治理：区块级折叠控件已收敛到共享 `disclosure` 组件；知识指南和 AI 详情保留为明确的 `inline` 层级，不再与区块操作混用。2026-08-27 V3.2 同步治理 §13.2 #3（governance ledger 共享基类 + 5 个 variant 修饰符）与 §13.2 #4（chart series token 化，21 个 `--series-*` 加 getSeriesColor/getPatternFill API）。

这些债务是后续迭代清单，不授权一次性全站重构。每次只处理一个共享组件或一个页面家族，并保留全量验证。

### 13.3 2026-09-09 全系统复查

本轮以 3.5 视觉基线检查共享 CSS、模板、十个 SPA 页面和十一条冷启动路由，并对 2560×1440、1280×720、768×1024、390×844 四个视口做实际渲染复核。

- **已修复**：共享样式中残留的暖米色表面、棕色边框和暖色环境光已迁移到冷灰表面与蓝灰信息光；语义 warning 继续保留，但只通过 token 用于小范围状态。
- **已修复**：侧栏副标题、分组标题和普通导航由 tertiary 提升到 `--text-secondary`，解决 `--bg-strong` 上约 4.1:1 的小字对比度不足。
- **已修复**：A 股 ETF 持仓份额与成本价输入补充逐品种可访问名称；审查脚本不再把 `hidden` 控件误报为缺少标签。
- **已修复**：响应式检查的宏观日历真内容选择器同步到当前组件，避免页面已渲染却被记为 `content=N`。
- **通过**：全站没有原生 `<select>`、没有 `transition: all`，四个验收视口没有页面级横向溢出。
- **继续治理**：`styles.css` 仍承担历史页面规则，`editorial.css` 仍是最终 token 权威；页面 JS 仍有 22 个图表序列硬编码颜色。两项按 §13.2 的小批次迁移原则处理，不在本轮扩大为结构重构。

---

## 14.5 V3.2 / V3.3 剩余债务（2026-08-27 状态）

仅记录 V3.2 / V3.3 仍未处理、需在 V3.4+ 推进的债务项；其余债务参见 §13.2。

### V3.3 已收敛（2026-08-27）

- **§13.2 #2 页面标题语义不一致**：`gold_v5.js:157` 的 `.gold-page-h1` 残留类已下线（HTML class 与 2 段 CSS 一并删除，`page-display-title` 接管）；`macro_calendar.js:197/238` 与 `analysis.js:775` 三处 H2 补 `page-display-title` display class；BTC 衍生品 / AI 策略 / 知识百科内容区从 V2.x 起已是 H2 + `page-display-title`。
- **`source/docs/UI_UX_AUDIT_2026-07-31.md` 路径分叉**：10 处引用（7 处代码注释 + 2 处设计手册 prose + 1 处 `UPDATES_V2.1.md`）已 sed 改为 `source/docs/UI_UX_AUDIT_2026-07-31.md`；新增 `tests/test_design_handbook_consolidation.py::test_no_path_split_to_legacy_audit_or_spec` 静态守卫防回归。
- **次生路径分叉**：`dropdown` spec 4 处 + `volatility_research` audit 2 处同样 sed 收敛；新加的路径分叉守卫已覆盖全部 3 类。

### 仍未处理（V3.4+）

- §13.2 #1 双样式源 token 归属：editorial.css 为唯一 token 权威，已验证（2026-08-31 H0，UI2 surface 合同测试持续守护）。
- §13.2 #7 断点收敛为 6 组：已验证（2026-08-31，`test_responsive_breakpoints_consolidated.py`）。
- 2026-09-04 ui-audit 复测仍发现三处残留（下拉局部白底、监控 28px 间距叠加、tertiary 对比度 4.00:1），均已当日修复并以 `test_shared_style_regressions.py` / 对比度 token 值钉住；后续登记按项记录验证视口、状态与日期，不再使用「全部清偿」式汇总声明。

### UI 2.0 首轮（Workbench interaction layer）

- 视觉方向固定为 **Quiet Shell + Living Data**：外壳保持安静，变化、来源与证据关系由语义状态表达。
- `editorial.css :root` 继续作为唯一 canonical token 源；禁止新增第三层全局 override 或新的 palette 文件。
- Surface 仅分为 canvas、section、panel、floating；明显 elevation 与 blur 只允许用于真正浮层。
- 首轮 pilot 为 Monitoring Overview 与 BTC Derivatives，共享 Context Rail、Context Inspector、显式 linked selection 与 semantic motion。
- Market Events 与 Macro Calendar 作为 pilot 稳定后的首批迁移页面，只消费已有事件、指标、来源与时间字段。
- 首轮正式 Workbench 页面限定为 Monitoring Overview、BTC Derivatives、Market Events 与 Macro Calendar；其余页面在具备真实 inspection adapter 前不得挂载空壳 Context Rail 或 Inspector。
- 市场方向、系统可用性与用户选择分别使用独立语义，不得互相借色。
- P1 冻结时不含操作核心；P2 Operator Core 按下方分阶段合同开放 Command Palette、Inspector pin/resize 和 URL selection recovery。跨页内容搜索、任意布局与额外页面迁移仍不在本轮范围。

### P2 Operator Core（不等于完整 P2 页面迁移）

- Command：单一 app registry；十个 canonical 导航页加四页的页面操作；scope 卸载释放。Palette 只搜索 registry，关闭后再导航/聚焦，IME composing 不执行 Enter。
- 浮层：Palette > 最上层 modal/detail/sidebar > responsive Inspector > desktop dock；Escape 一次关闭一层，modal 共享所有者滚动锁。
- Pin：仅当前页面 committed selection，可继续 preview 关联；点击替换、同 ID 刷新保留 pin，clear/失效/unmount 解除。不写存储。
- Resize：仅 >1180px；默认 `clamp(328px, 21vw, 400px)`，用户范围 320px 至 `min(520px, 42vw)`。左拖扩大，键盘 8px/Shift 32px，Home/End 边界。仅持久化 `cis.workbench.inspector.width.v1`，窄屏不覆盖桌面偏好。
- URL：仅 `inspect` 对象 ID；保留 query/hash/history state，preview 不写入，冷读等待，最新 adapter registry/LKG resolve，失效给出轻量提示。上下文切换清除，destroy 不改新路由。
- 视觉延续 canonical surface/token；只增加必要层级、手柄和状态控件，无运行时 `<style>`。

阶段记录（2026-08-30）：Command 的 registry/浏览器/边界 10 passed，11/11 路由 + 10/10 SPA；Pin 的四宽度行为 4 passed + store 合同，全量路由通过；Resize 的合同/浏览器 6 passed，全量路由通过。URL 与同版最终门禁见本手册文末 2026-08-31 验收记录；便携包另做解压空库启动验证。
- 视觉验证以 2560×1440 为主基线；2560×1600 仅作高屏 cross-check。

---

## 14. 新增或修改 UI 的评审清单

### 设计

```text
☐ 已确定页面 layout 家族与单一主任务
☐ 复用了现有 token 和共享组件
☐ 没有新增未经定义的硬编码颜色
☐ 没有重复创建按钮、dropdown、折叠或 governance 变体
☐ 系统可用性与市场方向使用不同语义
☐ 加载、空态、降级和成功态结构稳定
☐ 没有卡片嵌套卡片或 frosted-on-frosted
```

### 交互与可访问性

```text
☐ 按钮/链接语义正确，Tab 顺序可用
☐ focus-visible 清晰，icon-only 有 aria-label
☐ 折叠/抽屉有 aria-expanded、焦点与滚动管理
☐ reduced-motion / reduced-transparency 有降级
☐ 没有原生 select、emoji 图标、transition: all
☐ 触控命中区至少 44×44px
```

### 响应式与验证

```text
☐ 2560×1440 主视口截图确认
☐ 1280×720、768×1024、390×844 无页面级横向溢出
☐ 表格、图表、sticky 元素和抽屉在窄屏可用
☐ node --check / py_compile / pytest 按 AGENTS.md 执行
☐ 架构、工作流、共享依赖改动已跑全量 verify_pages.py
☐ 页面交互改动已做对应 stress_test.py
```

---

## 15. 修订记录

| 日期 | 版本 | 修订 |
|---|---|---|
| 2026-09-09 | 3.5 | 固定冷灰表面、深冷紫主色与蓝灰配套色；新增通用容器禁止暖色晕染、缺失置信度不得告警化的规则；记录全站响应式、对比度、表单标签和审查脚本复查结果。 |
| 2026-08-24 | 3.1 | 新增 disclosure 组件唯一入口、三种层级、完整状态与可访问性规范；统一活动页面的区块级折叠按钮。 |
| 2026-08-20 | 3.0 | 对十个页面、全局外壳、当前生效 token 与共享组件进行审查；纠正旧手册中调色板、卡片圆角、间距、字体层级和视口基线与实际实现不一致的问题；新增设计债务与治理顺序。 |

---

## UI 2.0 P2 Operator Core — ACCEPTED（2026-08-31）

交付状态为 **P1 Accepted/Frozen + P2 Operator Core Complete**，不是完整 P2 页面迁移。
本节记录 Operator Core 初次验收时的四页白名单；最新页面范围由本手册开头的 V2.3 迁移基线覆盖。Strategy、ETF、Gold 不新增 Inspector，Knowledge 保持 reference layout。

- Batch 3B / 续作：URL 冷缓存等待、任务失败、LKG 恢复、上下文清除和恢复中切页已验收；图表选择刷新、pin、resize 重排及拖拽中卸载均有行为守卫。
- 同版最终门禁：18 个改动 JS 语法检查、32 个改动 Python 编译与 Ruff 通过；`python -m pytest tests/ -q -rs --tb=short` 为 **1915 passed、6 skipped、0 failed**。
- `python tests/verify_pages.py`：**11/11 冷启动、10/10 SPA**，无 pageerror、console error、失败响应或慢切页；`python tests/stress_test.py --pages monitoring-overview,btc-derivatives,market-events,macro-calendar` 为 **4 PASS、0 WARN、0 FAIL**。
- 确定性四页行为矩阵覆盖 click/Enter/Space、preview/committed/pin、浮层 Escape 优先级、焦点与滚动锁、同值刷新、失效对象和卸载；Palette 连续开关 20 次与命令 scope 切页已通过。
- 响应式：10 页 × 8 视口共 **80 项通过**。主视口 2560×1440，补充 1500×900、1280×720、1100×800、800×900、768×1024、390×844；2560×1600 仅高屏复核。
- 140 张 Workbench fullPage 状态截图独立留存，覆盖关闭、打开、pin、resize 两端、drawer、bottom sheet、Palette 与 linked highlight；没有更新截图基准。复核 shell、Context Rail、主次层级、surface、Inspector、关联提示、字体及响应式。
- 本轮修复：BTC 刷新失败保留 LKG/selection；延迟保护规划响应遵守页面代际；修复 CSS 媒体查询范围导致的隐藏指南/详情浮层定位；技术指标旧测试改用 canonical 路由和确定性状态，禁止访问 404 后空通过。

验收环境：自建 8002、`WORKER_PROFILE=none`、`LOCAL_BOOTSTRAP_WARMUP_ENABLED=false`，仅 23.4 MiB 精简库（157 份有效已发布快照）。Windows 测试设置 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`，避免子进程 UTF-8/GBK 解码分叉。截图输出使用 `VERIFY_SCREENSHOT_DIR`、`WORKBENCH_SCREENSHOT_DIR`、`RESPONSIVE_OUTPUT_DIR`；报告另存，不作为基准。

已知遗留：全量 Ruff 为 235 项项目问题 + 4893 项内置运行库问题，改动范围为 0；内置 Python `pip check` 无依赖冲突。6 项 skip 分别为 chip_structure 缺少旧导出（1）、旧知识指南用例待迁移至 FAB（2）、缺少可选 pandas-ta（1）/TA-Lib（2），均非后端未启动。5 条 warning 来自旧 Pydantic 用法及测试用短 HMAC key。Eastmoney ETF 现有上游降级告警保留；provider 请求未修改，direct/proxy 门禁不适用。

便携交付须独立验证解压后的 `start.bat`、内置 Python、空库和浏览器加载；包内 `.env` 原样保留，标记“未加密、含密钥、仅限授权内部使用”。数据库、运行缓存、日志、临时截图、`nul` 不入包，`app/cache` 业务源码及随仓库发布的 CFTC 基础数据保留。
