# 设计纪律 — Crypto Investing Terminal

> 历史工程检查附录。视觉 token、共享组件和页面布局的唯一规范以仓库根目录 `docs/design-guidelines.md` 为准；本文件只保留尚未迁移的工程细则，冲突时不得覆盖根手册。

## 0. 文件性质

- **根目录 `docs/design-guidelines.md` 是设计系统事实源**。`AGENTS.md` §六.3「错误教训」表格是已发生的反面教材；本文件是历史工程附录。
- 改动需在 PR 描述里说明新增/删除/修改了哪几条；改动前后必须跑 `python tests/verify_pages.py --baseline` 做截图对照。
- 与现有 token（`source/app/static/styles.css` `:root` 区）的冲突一律以本文件为准；token 是实现层，本文件是规范层。

## 1. 资料来源

| 来源 | 定位 | 本文件取其 |
|---|---|---|
| [`anthropics/skills/skills/frontend-design/SKILL.md`](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | "design lead at a small studio" 设计方法论 | §2 设计原则 / §3 决策流程 |
| [`vercel-labs/web-interface-guidelines/command.md`](https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md) | UI 编码规范（按 file:line 静态扫描） | §5 可访问性 / §6 动效 / §7 排版 / §8 反模式 |
| [`nextlevelbuilder/ui-ux-pro-max-skill/SKILL.md`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 10 类 UX 规则优先级 + 行业 reasoning | §2 优先级 |
| [`Leonxlnx/taste-skill/SKILL.md`](https://github.com/Leonxlnx/taste-skill) | Anti-slop 系统级规范 | §3 决策三旋钮 / §9 颜色 / §10 字体 |
| [`pbakaus/impeccable/README.md`](https://github.com/pbakaus/impeccable) | `frontend-design` 续作 + 23 命令 + 59 静态规则 | §12 上线前自检清单 |
| [`emilkowalski/skills/skills/emil-design-eng/SKILL.md`](https://github.com/emilkowalski/skills) | Design Engineering 哲学 + 微交互细节 | §6 动效时长 / §13 按钮 / §14 弹层 |

本仓库已有 `source/docs/UI_UX_AUDIT_2026-07-31.md` 记录 token 补齐历史；本文件不重复 token 列表，只引用其约束。

## 2. 优先级（1→10 决定设计冲突时谁赢）

| 优先级 | 类别 | 影响 | 本仓库具体落地 |
|---|---|---|---|
| 1 | 可访问性 | CRITICAL | `tests/test_a11y_*.py`；a11y 守卫已写入 CI 必经 |
| 2 | 触屏 / 交互反馈 | CRITICAL | 终端主要在桌面；保留 44×44 命中区作未来触屏 fallback |
| 3 | 性能（首屏 / SPA 切页） | HIGH | §六.2「按改动类别分级的测试要求」 + `tests/stress_test.py` |
| 4 | 风格选择（避免 LLM 默认） | HIGH | §9 颜色 / §10 字体 反默认清单 |
| 5 | 布局与响应式 | HIGH | **视口统一 2560×1600**（`verify_pages.py --viewport` 默认；2560×1440 仍可作为 cross-check 视口，详见 `tests/responsive_check.py` `desktop-2k`） |
| 6 | 排版与颜色 | MEDIUM | 字号基线 12.5px / 行高 1.5（沿用 `editorial.css`） |
| 7 | 动效 | MEDIUM | §6 / §13；不动关键操作链 |
| 8 | 表单与反馈 | MEDIUM | 错误贴近字段；提交按钮在请求发起前保持可点 |
| 9 | 导航与状态 | HIGH | URL 反映状态；过滤/分页进 query params |
| 10 | 图表与数据可视化 | LOW | 图例 + tooltip + 颜色不止一种编码 |

**冲突仲裁规则**：高级别胜出。同一级别内冲突 → `AGENTS.md` §六.3 历史教训 > 本文件 §9/10 反默认 > 风格自由发挥。

## 3. 决策流程（来自 frontend-design + taste-skill）

每次接到 UI 任务，**先做完 5 步再动代码**：

1. **读简报**：把目标产品/页面/受众/单条核心任务一句话写出来；如 AGENTS.md §一.1 缺失，自己补。
2. **选设计读数（Design Read）**：用一句话声明方向——"Reading this as: <页面类型> for <受众>, with <vibe> language, leaning toward <设计语言>."。比如本次 BTC 数据源底栏：`Reading this as: 高频量化研究终端的合规底栏，for 专业交易员, with 安静克制 language, leaning toward 冷白半透明 + 青绿 chip`.
3. **设三旋钮（taste-skill VARIANCE / MOTION / DENSITY）**：默认 `8 / 6 / 4`；本仓库是「数据密 / 安静 / 实用型」，**实际取值 `5 / 4 / 7`**（低 variance、高 density）。把旋钮值写到 PR 描述里。
4. **挑地基**：本仓库不是 SaaS 营销页，无须 `frontend-design` §3.A 的「真设计系统」（Fluent / Carbon / Polaris）。地基就是 `styles.css :root` 里的 50+ token；不要 import 外部 CSS。
5. **完成 → 自检 → 上线**：§12 自检清单必须 100% 通过。

## 4. 项目定位（不让设计跑偏）

- **终端定位**：加密市场研究 / 行情 / 衍生品 / 信号辅助。
- **明确不做的**（设计边界）：
  - 不执行下单（`AGENTS.md §六.3` "naked_sell" 静态守卫已设）。
  - 不做营销/品牌叙事（无 hero 大标语、无渐变彩条、无"立刻试用" CTA）。
  - 不做社交/UGC 渲染（无表情符号、不做评论流）。
- **明确要做的**：
  - 数据正确到达比好看重要（`AGENTS.md §六` "修复代码只是手段，数据正确到达前端才是目标"）。
  - 终端用户能立刻看到数字、状态、归属、时间。
  - 留缓存降级路径（`AGENTS.md §九.1` 冷缓存不渲染为高风险）。

## 5. 可访问性（最高优先级）

| 规则 | 本仓库具体做法 |
|---|---|
| Icon-only 按钮必须有 `aria-label` | 已有静态守卫 `tests/test_a11y_icon_button_aria_label.py` |
| `<button>` 做动作，`<a>` 做导航；不用 `<div onClick>` | 静态扫描 `tests/test_a11y_button_semantics.py` |
| `<img>` 显式 `width` + `height` 防 CLS | Chart.js canvas 已统一在 `app/static/ui/charts.js` 设尺寸 |
| 装饰性图标 `aria-hidden="true"` | 写自定义 SVG 时强制；emoji 字符也视作装饰性 |
| 异步更新用 `aria-live="polite"` | 已有 `tests/test_a11y_aria_live.py` |
| 表单控件要 `<label>` 或 `aria-label` | `tests/test_a11y_label_for_*.py` |
| 不阻止 paste（`onPaste + preventDefault` 禁用） | 全站不写 `onpaste` |
| `prefers-reduced-motion` 必须尊重 | 已有 commit `05a80d9`；动效 token 在 `--dur-press / --dur-rise`，reduced-motion 下整体缩短到 1ms |
| Focus 必须可见：`:focus-visible` 而非裸 `:focus` | 全站不写 `outline:none`（除非有 `focus-visible` 兜底） |
| Sticky / overlay 元素不能遮挡焦点 | 表头 sticky 时检查 `scroll-margin-top` |
| Skip link 跳到主内容 | 已有 `#main` 锚点；首屏 `<a href="#main" class="skip-link">` |
| 媒体控件可键盘操作；装饰媒体对辅助技术隐藏 | 视频/音频极少用；图表 canvas 已 `role="img"` + `aria-label` |
| `color-scheme: dark` / `theme-color` 跟随主题 | `:root` 已有 `--bg`；`<meta name="theme-color">` 跟随 |
| 不要 `user-scalable=no` / `maximum-scale=1` | 不写 viewport meta 这类限制 |

## 6. 动效（emil-design-eng 频率决策表）

**先回答：这次动效用户一天看几次？**

### 6.1 页面切换：终端式 Fade-through

- 应用外壳（侧栏、顶栏、全局状态）保持静止，只切换 `#page-root`；顶栏标题文字可在更新后做一次 `160ms / 2px` 的局部淡入。
- 路由点击后导航选中态必须在同一帧响应；旧页先用 `72ms` 淡出并上移 `2px`，再执行卸载。
- 卸载后立即挂载稳定骨架；骨架仅做 `120ms` 透明度过渡，不等待接口或图表完成。
- 新页面框架就绪后用 `180ms` 淡入并从下方 `4px` 归位。数据卡片和图表继续使用各自骨架，不得重播整页动画。
- 首次页面加载不播放路由入场动画；`prefers-reduced-motion` 下沿用全局 `0.01ms` 时长钳制。
- 快速连续导航只保留最后一个目标；等待中的目标用导航圆点表达，不允许重复卸载或让旧响应覆盖新页面。
- 禁止整页横向滑动、缩放、动态 `backdrop-filter`、高度动画和无限级联错峰。路由动画只使用 `opacity` 与 `transform`。

| 频率 | 决定 |
|---|---|
| 100+ 次/天（键盘快捷键 / 命令面板开关） | **0 动画** |
| 数十次/天（hover / 列表切换） | 移除或压缩到 ≤ 100ms |
| 偶尔（modal / drawer / toast） | 标准动画（150-300ms） |
| 罕见 / 首次（onboarding / 反馈表单 / 庆祝） | 可加意图性细节 |

### 时长

| 元素 | 时长 |
|---|---|
| 按钮按下反馈 | 100–160ms |
| Tooltip / 小 popover | 125–200ms |
| Dropdown / select | 150–250ms |
| Modal / drawer | 200–500ms |
| 营销解释性动画 | 可长（但本终端不做营销） |

### 缓动

- **进入 / 退出 → ease-out**（开始快，立即响应）。本仓库 token `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`。
- **屏内形态变化 → ease-in-out**。`--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)`。
- **hover / 颜色变化 → `ease`**。
- **匀速（marquee / 进度条） → `linear`**。
- **禁用 `ease-in` 进入动画**：它开始慢，让 UI 显得迟钝。`AGENTS.md §六.3` "横栏点击 lag 100-300ms" 即此问题。
- **禁用 `transition: all`**：按 Vercel 规则逐属性列出。

### 性能

- 仅动 `transform` / `opacity`（合成层友好）。本仓库 token 严格遵守。
- 不改 CSS 变量去触发全树重算；直接改 `transform` / `opacity`。
- prefers-reduced-motion 下所有动效时长压到 1ms，但仍保留最终态。

### 中断性

- 用 CSS `transition` 不用 `@keyframes`（除非是循环动画）。原因：transition 可中断、keyframes 重启从零。
- 长动效用 spring（Motion / Framer Motion 的 `useSpring`），让手势中断平滑反转。本仓库目前未引入 Motion，但保留升级通道。

## 7. 排版

- **省略号**：`…`（U+2026）非三连点 `...`。
- **引号**：弯引号 `" "` `' '`。
- **不可断空格**：数字 + 单位 `10&nbsp;MB`、`⌘&nbsp;K`、品牌名。
- **Loading 状态**：`"加载中…"`、`"保存中…"`（句末省略号）。
- **数字列**：`font-variant-numeric: tabular-nums`；小数位对齐。
- **标题**：`text-wrap: balance` 防孤行；标题长度 > 4 字时不强制一行。

字号基线（沿用 `editorial.css`）：

| 角色 | 字号 | 用途 |
|---|---|---|
| Display | 32-44px | 极少用；本终端以数据为主，不放大字号 |
| H1 | 22-26px | 页面 hero 标题 |
| H2 | 18-20px | 区块标题 |
| H3 | 15-16px | 卡片标题 |
| Body | 13-14px | 正文 |
| Caption / eyebrow | 11.5-12.5px | 元信息 / 标签 |
| Mono | 12-13px | 数字 / 时间戳 |

行高：1.5（正文）/ 1.3（标题）/ 1.2（display）。

## 8. 表单

- 输入有 `autocomplete` + 语义化 `name`。
- 正确 `type` + `inputmode`（`email`/`tel`/`url`/`number`）。
- 不阻止 paste。
- label 与控件同一点击命中区（无 dead zone）。
- email / code / username 关 spellcheck。
- 提交按钮到请求发起前保持可点；请求中显示 spinner。
- 错误内联 + 提交时把焦点移到第一个错误。
- placeholder 以 `…` 结尾展示示例。
- 不在非认证字段触发密码填充（`autocomplete="off"`）。
- 离开未保存 → `beforeunload` 守卫或路由守卫。
- 现货价格等浮点字段 `<input type="number" step="any">`（`AGENTS.md §六.3` 已记）。

## 9. 颜色反默认（taste-skill + 本仓库 `styles.css`）

### 必须不做的（AI / LLM 默认）

- **AI 紫 / 蓝渐变**：`#6366F1 → #3B82F6` 这类 background-image 渐变一律禁用。
- **Premium-consumer 米色 + 铜锈**：本仓库是研究终端非消费品，避不开这条但要意识到这是 AI tell；本仓库选冷白半透明 + 青绿就是反默认。
- **状态卡大面积琥珀背景**：把它当 error 是错的（`AGENTS.md §六.3` 第 5 条）。
- **emoji 当图标**：跨平台渲染不一致。统一用 SVG icon（已有 `app/static/ui/icon.js`）。
- **pure black `#000`**：始终 tint 一点点（`--ink: #1d2b3a`）。

### 本仓库 `:root` 主色板（直接复用，不重复定义）

```
--ink          #1d2b3a    文本
--muted        #6e7c8e    次要文本
--muted-strong #5e6a78    标题辅助
--accent       #14b8a6    青绿（确认 / 成功）
--accent-strong #0f766e   深青绿（强调）
--warning      #f97316    琥珀（警告 / 受限）
--danger       #a46850    砖红（不可用 / 错误）
--border       rgba(160,140,108,0.22)  描边
--bg           #fbfaf6   页面底色
```

- **主色 ≤ 1 个**（青绿）。所有 status chip 都在青绿 / 琥珀 / 砖红 / 中性 四档内，不引入第四个主色。
- **Color Consistency Lock**：页面选定 accent 后全页统一；不在某节突然换色（`taste-skill` 强制规则）。
- **饱和度 < 80%**：所有 chip / badge 背景用 `rgba` 8-10% 透明叠，不写实心高饱和块。

## 10. 字体反默认

- **不默认 Inter / Arial / 系统默认**。本仓库使用既有 `editorial.css` 的衬线 display + sans body 组合；**不要擅自换字体**，换字体前先看 `AGENTS.md §三` 工程风格是否允许。
- **不用 Serif 当默认**：除非页面定位是 editorial / luxury / publication（`taste-skill` §4.1 强调）。本仓库是研究终端，默认 sans display，仅在「法币符号 / 币种名称」处可用 serif 显差异。
- **不要把 Fraunces / Instrument_Serif 当 display 默认**（`taste-skill` 明列 AI tell）。
- **强调字用同字体的 italic / bold**，不要 sans 标题里塞 serif 单词。
- **斜体下伸字母（y g j p q）+ `leading-none` 会切下伸**，使用 `leading: 1.1` 起步 + 包裹元素预留 `pb-1`。

## 11. 布局与响应式

- **视口统一 2560×1600**（用户实际设备分辨率，16:10），2560×1440 保留作为 cross-check 视口；所有 Playwright / control-browser 截图前 `setViewportSize({ width: 2560, height: 1600 })`。所有 `vh`-based 容器必须显式 cap（参考 `.btc-table-wrap { max-height: min(60vh, 960px); }`），避免在更高 viewport 上让表格 / 卡片"占据满屏"。
- **断点**：`sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536`（与 taste-skill §3.E 对齐）。终端桌面优先，触屏布局为兜底。
- **`min-h-[100dvh]` 不用 `h-screen`**：iOS Safari 地址栏伸缩不会跳。
- **Grid 优先于 flex 算术**：不要 `w-[calc(33%-1rem)]`，用 `grid-cols-3 gap-6`。
- **`overflow-x-hidden`** 在外层容器上避免横向滚动条。
- **安全区**：`env(safe-area-inset-*)` 在全屏布局（未来移动端兜底）。
- **导航**：URL 反映状态（filter / tab / pagination 进 query params）；`<a>` 而不是 `<div onClick>` 支持 cmd-click。
- **破坏性动作**：永远要确认 modal 或 undo 窗口，**不立即执行**。

### 间距系统（Spacing）

页面内多个卡片 / 区块之间的间距统一使用 CSS 自定义属性，避免硬编码 `margin`：

| Token | 值 | 用途 |
|---|---|---|
| `--content-gap` | `24px` | **卡片与卡片之间的间距**（页面级多卡片布局） |
| `--section-gap` | `28px` | 大区块之间的间距（如 page-root 的 grid gap） |

**规则**：
- 同一页面内多个并列卡片容器，父容器用 `display: grid; gap: var(--content-gap)` 统一控制间距，**禁止**给每个卡片单独加 `margin-bottom`。
- 卡片内部的元素间距用 `gap` 或 `padding` 控制，不借用 `--content-gap`。
- 例外：当卡片之间需要视觉分隔（如分割线）时，可用 `border-top` 替代 gap，但需全文一致。

**反模式**：
- ❌ `.card + .card { margin-top: 24px; }` — 选择器耦合，新增卡片需记得加
- ❌ 每个卡片各自 `margin-bottom: 16px` — 间距不统一，底部卡片多余 margin
- ✅ `#container { display: grid; gap: var(--content-gap); }` — 父控子，间距一致

## 12. 上线前自检清单（impeccable + 本仓库加项）

每次写完 UI 必须逐条勾选；任何一条失败即视为未完成：

```
☐ ruff / pytest / node --check 通过（AGENTS.md §六）
☐ 视口 2560×1600 截图存档（verify_pages.py 或 control-browser）
☐ pageerror = 0（JS 控制台无未捕获错误）
☐ 至少一次 SPA 切页走过新模块
☐ 鼠标 hover 有视觉反馈；按钮 :active 有 scale(0.97) 反馈（emil-design-eng §13）
☐ Tab 键能走到所有可交互元素；focus-visible 可见
☐ prefers-reduced-motion 下动效压到 1ms 但状态完整
☐ 至少 768 / 1024 / 2560 三个断点无横向滚动 / 内容溢出
☐ icon-only 按钮有 aria-label
☐ 表单字段有 label + autocomplete + 正确 type
☐ 数字列 tabular-nums；时间用 Intl.DateTimeFormat
☐ 没有 emoji 当图标；没有 native <select>（用 app/static/ui/dropdown.js mountDropdown）
☐ 没有 transition: all；没有 outline:none（除非有 focus-visible）
☐ 没有 AI 默认紫蓝渐变 / 米色 + 铜锈 premium palette
☐ 没有 "naked_sell / sell_call / sell_put / ratio_spread" 终端页面字面量
☐ CSS 变量名都在 :root 声明的 token 列表内（tests/test_undeclared_token_visual_regression.py）
☐ 缓存 / 数据缺失时不渲染为高风险（AGENTS.md §九.1）
```

## 13. 按钮微交互（emil-design-eng）

- `:active` 给 `transform: scale(0.97)` + 160ms ease-out；scale 范围 0.95–0.98。
- `:hover` 比常态对比度更高（不只换颜色，加深或提亮）。
- 任何 pressable 元素都按这条规则：卡片、chip、icon 按钮、tab。
- 按钮内容变化时（如 "保存" → "保存中…" → "已保存"），中间过渡加 `filter: blur(2px); opacity: 0.7` 掩盖跳变（保持 < 20px blur，Safari 性能考虑）。

## 14. 弹层 / Popover / Drawer

- `transform-origin: var(--transform-origin)` 跟随触发器。**Modal 例外**（无锚点，居中放大）。
- 不从 `scale(0)` 开始；从 `scale(0.9)` + `opacity: 0` 进入（"现实世界没有从无到有的东西"）。
- Tooltip：首次 hover 延迟 200ms 出；之后相邻 hover 即时无动画（`data-instant` 关闭 transition-duration）。
- Drawer：`clip-path: inset(...)` 或 `translateY(100%)` 用百分比，跟元素实际尺寸无关。
- 拖拽手势：velocity > ~0.11 即关闭（与拖距无关）；边界阻尼不硬停；多点触控用第一个 touch。
- 拖拽时禁用文本选择 + `inert` 拖动元素。
- 全屏 modal/drawer 加 `overscroll-behavior: contain` 防止滚动穿透。

## 15. 反模式清单（Vercel + taste-skill + 本仓库沉淀）

按发现即标 FAIL：

- `transition: all`
- `outline: none` 无 `focus-visible` 替代
- `onPaste + preventDefault`
- `<div onClick>` 触发导航
- `<img>` 无 width / height
- 长列表 `.map()` 无虚拟化（> 50 项用 `content-visibility: auto` 或 virtua）
- 表单字段无 label
- icon-only 按钮无 `aria-label`
- 硬编码日期 / 数字格式（不用 Intl.*）
- 无理由的 `autoFocus`
- 动图 GIF 该用视频替代时还在用 GIF
- 仅手势可触发且无键盘替代的动作
- `user-scalable=no` / `maximum-scale=1`
- 原生 `<select>`（本仓库 `tests/test_no_native_select_remaining.py` 已守卫）
- emoji 当图标
- AI 默认紫蓝渐变 / 米色 + 铜锈 premium palette
- 大面积琥珀背景当 error（应仅在 RANGE / TRANSITION 模式低饱和度微调）
- Inter / Arial / 系统字体当默认（除非 AGENTS.md §三明示允许）
- Fraunces / Instrument_Serif 当 display 默认
- "naked_sell" / "sell_call" / "sell_put" / "ratio_spread" 字面量进终端页面
- 卡片嵌套卡片（`taste-skill` 明确反）
- gray text on colored backgrounds（`taste-skill` 明确反）
- 弹性 / bounce easing（emil-design-eng 明确反）
- 终端页面渲染错误代码 / HTTP 状态 / 内部 URL 给用户（AGENTS.md §六 "修复代码只是手段"）

## 16. 与 AGENTS.md 的边界

- AGENTS.md 是**工程总规**（验证流程 / SQLite 边界 / 复盘门禁 / workbench 规则等），位于仓库根 `AGENTS.md`。
- 本文件是**设计分支**，位于 `docs/design-guidelines.md`。
- 冲突时：工程总规胜出。本文件不得改写工程总规约束，只能在该方向上强化。

## 17. 修订记录

| 日期 | 修订 |
|---|---|
| 2026-08-18 | 初版。基于 6 份外部指南 + 本仓库 AGENTS.md §六.3 历史教训合并。 |
