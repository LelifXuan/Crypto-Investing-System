# 交易系统研究终端设计手册

> 版本 3.1 · 2026-08-24 组件治理基线  
> 适用范围：`source/app/templates/page.html`、`source/app/static/styles.css`、`source/app/static/editorial.css`、`source/app/static/ui/` 与 `source/app/static/pages/`。

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

**面向专业研究与配置决策的高密度市场终端，采用克制的编辑部式信息层级、暖灰纸面和低饱和紫色操作语言，重点突出数据状态、时间、来源和可执行边界。**

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
Primitive：原始值，如暖灰、紫色、间距 8px
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
| `--bg` | `#f2efea` | 应用画布 |
| `--bg-strong` | `#e8e3dd` | 左侧导航背景 |
| `--surface` | `#f7f5f1` | 普通表面 |
| `--surface-elevated` | `#fcfbf8` | 卡片与实色浮层 |
| `--surface-muted` | `#f0edf3` | 弱化区、锁定态、标签背景 |
| `--ink` | `#211d2b` | 主文字 |
| `--text-secondary` | `#5f5968` | 描述、辅助标签 |
| `--text-tertiary` | `#817a88` | 时间、缺失和低优先级信息 |
| `--border` | `#d9d3ca` | 标准边框 |
| `--border-strong` | `#c8c0b6` | 强分隔 |

这是“暖灰纸面 + 冷紫操作色”的编辑部终端，不是米金奢侈品风格，也不是高饱和 SaaS 蓝紫渐变。

### 3.2 操作色与状态色

| 语义 | Token | 当前值 | 使用规则 |
|---|---|---|---|
| 主操作 | `--accent` | `#66548e` | 选中、强调、轻量交互 |
| 主操作加强 | `--accent-strong` | `#4d3b73` | 主要按钮、焦点、章节标识 |
| 按下 | `--accent-pressed` | `#413161` | active / 强 hover |
| 信息 | `--info` | `#3e6f9f` | 数据在线、快照、说明 |
| 看多 | `--bullish` | `#34745f` | 明确的市场方向 |
| 看空 | `--bearish` | `#a34f5f` | 明确的市场方向 |
| 警告 | `--warning` | `#9b6a25` | stale、degraded、受限 |
| 错误 | `--danger` | `#9d3f48` | 不可用、失败、阻断 |
| 中性 | `--neutral` | `#746e79` | 无方向或不适用 |

强制规则：

- 紫色只表达操作、选中和产品识别，不替代看多/看空。
- 看多、看空不能用同一紫色色阶区分。
- `warning` 不是“市场风险高”的默认颜色，仅表达系统或执行层面的注意状态。
- K 线涨跌可使用更清晰的 `--direction-up` / `--direction-down`，但只限密集价格图。

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
- 1279px 及以下切换为离屏抽屉，配套 scrim 和滚动锁定。

### 5.2 全站顶栏

- 高度固定为 `--topbar-height: 64px`。
- `position: sticky; top: 0; z-index: 1000`，任何页面内容不得覆盖它。
- 结构顺序：移动端导航按钮 → 面包屑/页面标题 → 页面上下文 chip → 全局数据质量。
- 当前材质：`--glass-bg-deep` + `blur(28px)` + 轻量底部阴影。
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

机会矩阵是严格准入后的**机会发布面**，机会排序是仍在比较和复核中的**候选分析面**，两者不能重复表达同一组信息。

- 矩阵只高亮后端明确标记为 `qualified` 的高确定性机会；前端不得自行根据颜色、方向或置信度推断是否准入。
- 每个格子的方向、置信度与摘要必须取自对应周期节点，禁止把标的级全局结论复制到周线、日线和 4H。
- 矩阵只展示方向，不展示置信度。未通过门禁的格子保持中性，显示“等待确认”，但仍可进入详情复核。
- 机会排序保留置信度、综合评分和风险收益比，用于比较候选机会以及说明未晋级原因。
- 矩阵准入必须同时验证数据新鲜度、方向置信度、综合评分、风险收益比、方向分差、多模块一致性、仓位权限和显式冲突；任何一项失败都不得使用多空强调色。
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
| 1279px | 固定侧栏切换为抽屉；隐藏全局质量文字 |
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
| 市场事件 | `/market-events-page` | overview | 信息流、解锁日历、翻译状态 |
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
6. **局部组件仍覆盖全局视觉**：知识章节卡仍使用旧 `rgba(99,102,241,...)` 色值，与当前 `#66548e` editorial accent 不完全一致，应改用 token。
   *2026-08-27 V3.2*：已收敛。`styles.css` 中 91 处 `rgba(99,102,241,α)` 全部迁入 `editorial.css :root` 的 20 个 `--info-*` token（base + sub-tier），保留 indigo hue 不变；详见 §3.2 与 `tests/test_local_component_color_tokens.py`。
7. **断点过多**：当前存在 1500、1279、1180、1100、980、900、780、767、720、700、640、560 等近邻断点。后续应收敛为壳层、内容层和移动层三组，而不是继续新增。
   *2026-08-27 V3.2*：已收敛。17 个 width 值收为 6 组：`560` (mobile-s) / `720` (mobile-l) / `900` (tablet) / `1180` (small-desktop) / 默认 (desktop, 2560×1440 基线) / `1500` (wide-desktop)；`520` 作为 mobile-s 内部 extreme sub-tier 保留作扩展点；详见 §11 与 `tests/test_responsive_breakpoints_consolidated.py`。
8. **文档分叉**：根手册与 `source/docs/design-guidelines.md` 曾出现调色板和 2560×1600/1440 视口冲突。后续应以本手册为视觉基线，并逐步把旧文件收敛为工程检查清单。
   *2026-08-27 V3.2*：已收敛。`source/docs/design-guidelines.md` 重命名为 `source/docs/design-guidelines-legacy.md` 并加废弃 banner；本章末新增 §14.5 列出本轮剩余债务。

已治理：区块级折叠控件已收敛到共享 `disclosure` 组件；知识指南和 AI 详情保留为明确的 `inline` 层级，不再与区块操作混用。2026-08-27 V3.2 同步治理 §13.2 #3（governance ledger 共享基类 + 5 个 variant 修饰符）与 §13.2 #4（chart series token 化，21 个 `--series-*` 加 getSeriesColor/getPatternFill API）。

这些债务是后续迭代清单，不授权一次性全站重构。每次只处理一个共享组件或一个页面家族，并保留全量验证。

---

## 14.5 V3.2 本轮剩余债务（2026-08-27 状态）

仅记录 V3.2 仍未处理、需在 V3.3 推进的债务项；其余债务参见 §13.2。

- **§13.2 #2 页面标题语义不一致**：`gold_v5.js:156` 的 `.gold-page-h1` 残留类，以及 BTC 衍生品 / AI 策略 / 知识百科内容区仍存在的额外 H1 结构。需统一为 display class + H2。
- **`source/docs/UI_UX_AUDIT_2026-07-31.md` 路径分叉**：8 处代码注释指向 `docs/UI_UX_AUDIT_2026-07-31.md`（根路径），但文件实际位于 `source/docs/UI_UX_AUDIT_2026-07-31.md`。属于 #8 文档分叉的同类问题，V3.2 范围内未处理；建议要么复制一份到根 `docs/`，要么批量改 8 处引用指向 `source/docs/`。

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
| 2026-08-24 | 3.1 | 新增 disclosure 组件唯一入口、三种层级、完整状态与可访问性规范；统一活动页面的区块级折叠按钮。 |
| 2026-08-20 | 3.0 | 对十个页面、全局外壳、当前生效 token 与共享组件进行审查；纠正旧手册中调色板、卡片圆角、间距、字体层级和视口基线与实际实现不一致的问题；新增设计债务与治理顺序。 |
