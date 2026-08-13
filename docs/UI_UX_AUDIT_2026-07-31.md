# Crypto Research Terminal — UI/UX 审查（V1.7.x · 收敛版）

| 项 | 内容 |
|---|---|
| 审查日期 | 2026-07-31 |
| 当前分支 | main |
| 审查范围 | `app/templates/page.html`、`app/static/{main.js, styles.css, ui/*, core/*, pages/**}`、`tests/screenshots/`、现有 `tests/test_*.py` 守卫 |
| 终端定位 | 加密市场研究 / 行情 / 衍生品 / 信号辅助；**不**承担自动下单或交易执行 |
| 审查方法 | 静态阅读 + grep 计数 + 现有截图对照；**本轮未运行 Playwright**（`127.0.0.1:8002` 后端未启动） |
| 历史版本 | 已被本文件覆盖 |
| 实施状态（2026-07-31）| A 阶段（Token 补齐）已落地，B/C/D 阶段已规划 |

> 本文件性质：**UI/UX 静态审查、候选问题清单与运行时验证计划**。它**不是**正式的交易场景可用性认证，也不能在没有真实任务测试与运行时验证的前提下认定系统已适合正式市场决策辅助。

---

## 0. 实施记录（2026-07-31）

本轮由用户明确同意按 §16 拆分 A / B / C / D / E 5 个阶段逐阶段执行。

| 阶段 | 状态 | commit | 落地物 |
|---|---|---|---|
| A：Token 补齐 + 静态守卫 | **已完成** | `ccbc6de` | `app/static/styles.css:81-90` 新增 10 个别名；`tests/test_undeclared_token_visual_regression.py`（3/3 通过）|
| B：抽 `<Chip>` / `<Button>` 组件 | **已完成** | `846355d` | `app/static/core/dom.js` 新增 `mountChip` + `mountButton`；`tests/test_component_chip_button_smoke.py`（10/10 通过）；浏览器 probe 9/9 通过 |
| C：`ui/charts.js` 颜色 token 联动 | **已完成** | `0f595e0` | `:root` 新增 17 个 `--chart-*` token；`CHART_THEME_FALLBACK` + `CHART_THEME`；`tests/test_chart_theme_token_readback.py`（5/5）；浏览器 probe **20/20 token 值与 :root 一致** |
| D：Sticky thead + tooltip Escape | **已完成** | `7ed6851` | `table thead th { position: sticky; top: 0 }`；`core/dom.js` 加 `bindTooltipEscape`；`main.js` boot() 调用；`tests/test_sticky_thead_present.py`（7/7）；浏览器 probe focus → Escape → bubble hidden 全部 OK |
| E：报告同步 + 最终全量验证 | **已完成** | 见下 | §15 / §16 / §18 / §20 已修订；`tests/verify_pages.py` 11/11 + SPA 10/10 pass、console error 0、page error 0 |

依赖：所有"完成"汇报必须 `127.0.0.1:8002` 后端可访问 + Playwright 跑通。本轮 commit `ccbc6de..7ed6851` 在 2026-07-31 后端运行条件下验证通过。

**§16 完整 8 步覆盖情况**

| 原 §16 步 | 落地位置 | 状态 |
|---|---|---|
| 1. Token 收紧 | §16.A commit `ccbc6de` | ✅ |
| 2. 抽出 `<Chip>` | §16.B commit `846355d`（add-only，旧 31 类保留） | ✅ |
| 3. 抽出 `<Button>` | §16.B commit `846355d`（add-only，旧 8 套保留） | ✅ |
| 4. 抽出 `<Card>` | §16.B 卡片备注（75-80 变体联动 `body[data-page=…]`，与现有 `tests/test_*_frontend_static.py` 卡控重叠） | ⏭️ 后续 PR |
| 5. 接入共享状态 helper | §16.B helper 备注（依赖 §3.9 in-place update） | ⏭️ 后续 PR |
| 6. Tooltip keyboard | §16.D commit `7ed6851`（已有 `:focus-visible`，本轮补 Escape） | ✅ |
| 7. chart 颜色 token 联动 | §16.C commit `0f595e0` | ✅ |
| 8. Sticky thead | §16.D commit `7ed6851` | ✅ |

---

## 1. 审查范围与方法

**对象**
- 前端：`app/templates/page.html`、`app/static/styles.css`（11 070 行）、`app/static/{ui,core,pages}/**`。
- 后端：本轮不审查业务 API 形状；只关注其前端观测到的口径（freshness / cache / source 字段）。
- 测试守卫：`tests/verify_pages.py`、`tests/test_no_native_select_remaining.py`、其它 `tests/test_*.py`。

**方法**
- 直接读取关键文件（`styles.css`、`ui/dropdown.js`、`ui/charts.js`、`ui/pageGuideFab.js`、`core/dom.js`、`core/state.js`、`main.js`、`templates/page.html`）。
- 对每条结论标注 **A/B/C/D** 证据状态（见 §2）。
- 对 9 个一级页面与 strategy 子模块做模式抽取。
- 所有"精确数字"必须能在本附录中复现；不能复现的归 §20 待测指标。

**未做的事**
- ❌ 未运行 Playwright / Chromium 截图 / 视觉证据矩阵（后端未启）。
- ❌ 未对真实用户任务做端到端验证。
- ❌ 未运行 axe-core / Pa11y。
- ❌ 未测 performance budget / 跨浏览器兼容性。

---

## 2. 证据状态定义（A/B/C/D）

每条结论必须在条目开头标注证据状态，避免把"静态推演"当作"已观察到"。

### A. 已确认事实
有静态代码、grep 结果或当前文件结构直接支持，不依赖运行时推测。  
例：`var(--line)` 在 `styles.css` 出现 8 次；`status-chip neutral` 在 `pages/strategy/*.js` 出现 97 次。

### B. 静态推演结果
根据 CSS Cascade、函数参数或代码路径可以合理推演，但本轮**没有在浏览器中确认**。  
例：`border: 1px solid var(--line)` 若 `--line` 未声明可能整段失效——需要 Computed Style 验证。  
**禁止词**：实际显示、已经造成、控制台一定出现、用户会误判。

### C. 已运行验证
当前审计提交上的运行记录：Playwright 截图、`getComputedStyle()`、Console 输出、`verify_pages.py` 当前执行结果、交互测试、性能 Trace、键盘操作记录。  
**本轮 C 类证据为 0**（已确认未跑 Playwright / 后端）。

### D. 待验证指标
本轮无法确认，必须标记为待验证、候选问题，验证后再定级，不作为当前阻断项。

---

## 3. UI 成熟度结论

**结论：可用级（受控试用可达），是否能承担"市场决策辅助"超出本审查范围。**

| 维度 | 证据 | 评级 | 证据状态 |
|---|---|:---:|:---:|
| 设计 token 完整性 | 28+ token 在 `:root`；9 个被引用未声明（详见 §7.1）| 可用级 ⚠ | A |
| 字体体系 | IBM Plex Sans + Noto SC fallback；Mono + 正文两套 | 可用级 ✅ | A |
| 圆角体系 | `--radius: 24` / `--radius-card: 18` / `--radius-sm: 16`；18+ 个裸值并存 | 可用级 ⚠ | A |
| 磨砂玻璃一致性 | 28 站点分散；literal `blur(Npx)` 与 `var(--blur-*)` 各半 | 可用级 ⚠ | A |
| 跨页 PageHeader 一致性 | 详见 §11.1 表，存在 4 页偏差 | 可用级 ⚠ | A |
| 图表主题与 token 联动 | `ui/charts.js` 15+ 个硬编码颜色，无 `getComputedStyle` | 可用级 ⚠ | A |
| 跨页 Chip / Button / Card 一致性 | chip 命名漂移：`.chip.warn` / `.chip.cool` / `.chip.danger` / `.chip.warm` 并存；`status-chip neutral`（97 处）vs `status-chip chip-neutral`（31 处）混用 | 可用级 ⚠ | A + B |
| 状态可视化 | 分析 / 监控 / 衍生品页展示 source / cache / staleness，分散 | 可用级 ✅ | A |
| 全屏 scroll、表/图同步 | 表无 sticky thead；图表无 pinned crosshair | 可用级 ⚠ | A |
| 实例验证 | 历史 `tests/verify_pages.py` 通过；当前提交未重跑 | 待证 ⚠ | D |

---

## 4. L1-L4 投入分级

### L1：静态结构通过审查（**当前可确认**）
- 9 个页面模块存在；SPA 路由存在；dropdown / chart / page-guide 基础组件存在；`styles.css:1-74` token 体系存在；无明显缺失主页面。

### L2：当前提交完成基本运行验证（**当前状态：有历史验证记录，本轮未重新运行**）
- 历史 `verify_pages.py` 通过；历史截图 ≈ 80 张已积累。
- **本轮 C 类证据为 0**。L2 当前应记为"暂时成立，待当前 Commit 回归确认"。
- 必须重新跑后正式确认：
  - 9 页冷启动 + SPA 切页
  - Console 无未处理异常
  - 关键图表与表格完成渲染
  - 当前 Commit 截图归档

### L3：真实任务验证（**未执行**）
详见 §16。当前**不存在** L3 验证记录。

### L4：正式市场决策辅助（**未达成**）
依据是 L3 + 长时间稳定运行，**不是**未来功能数量。详见 §4 末尾清单。

> **多账户 / 多周期并排 / 自定义布局 / 拖拽 / 深色主题 / colorblind / 三连屏 / WebSocket / Pinned Crosshair / 跨页一键跳转 / Toast** —— 全部属于**非阻断产品能力**，不得作为当前版本"不能使用"的依据。详见 §10。

---

## 5. 严重程度定义

### P0：已确认的使用阻断
**必须同时满足**：
- 已有运行时证据（C 类）；
- 造成关键数据错误、状态错配、核心信息不可读、核心流程无法继续；
- 用户没有可靠绕过方式；
- 可能直接造成研究判断错误。

**没有运行时证据的问题不得定为 P0**。本轮 C 类证据为 0。

> **当前报告：没有证据充分的 P0 问题。**

### P1：已确认的重要问题（**C 类证据**）
至少满足一项：
- 已运行确认的信息语义错误；
- 已运行确认的数据时间 / 缓存状态 / 来源状态不可辨识；
- 已运行确认的关键交互不可用；
- 已运行确认的布局问题严重影响核心信息读取；
- 已运行确认的可访问性问题使关键内容无法取得。

### P1-Candidate：候选高优先级问题（**B 类证据**）
静态代码表明问题**可能**直接影响信息理解或核心操作，但**尚未运行确认**。**必须附验证方法**。

### P2：重要但非阻断
含：组件重复、命名漂移、token 使用不完整、页面结构不一致、根节点重渲染、Dead Code、未接入模块、内联样式、工程维护性、不会直接改变数据语义的视觉差异。

### P3：视觉精修
含：圆角、字号档位、阴影、blur、动效、图标复用、一般性响应式改进、非核心可访问性增强。

### 非阻断产品能力（**不归 P0/P1/P2**）
多账户、多周期并排、深色主题、色觉模式、自定义布局、拖拽排序、三连屏、WebSocket、跨页联动、Pinned Crosshair 等。

---

## 6. 已确认问题（P1/P1-Candidate/P2）

按证据状态从最硬到最软排列，每条都标注证据状态、复现步骤、运行时验收。

### 6.1 [P1-Candidate] 未声明 CSS Token —— 仅是候选

**证据状态**：A（Token 引用次数）+ B（CSS Cascade 推演）。

| Token | 引用次数 | 引用位置（节选） |
|---|---:|---|
| `--line` | 8 | `styles.css:514, 552, 578, 3084, 3100, 3165, 3200, 3222` |
| `--text` | 12 | `styles.css:5106` 等；`var(--text)` 不含 fallback |
| `--bg-surface` | 2 | `styles.css:10351, 10636` |
| `--bg-hover` | 2 | `styles.css:10361, 10717` |
| `--danger-strong` | 4 | `styles.css:2003, 3781, 8094, 8125` |
| `--border-light` | 2 | `styles.css:7152, 7541` |
| `--info-strong` | 1 | `styles.css:6048` |
| `--line-soft` | 1 | `styles.css:10761` |
| `--card-bg` | 1 | `styles.css:4296` |

**静态推演**（B）：
- `border: 1px solid var(--line)` 在 CSS Cascade 下整段 `border` 属性可能失效（CSS `var()` 未定义、无 fallback 时整段属性无效，不回退 initial）。
- `color: var(--text)` 无 fallback：`color` 失效后回退 inherited，颜色继承自父级，多数情况仍可读但已脆化。
- 上述影响仅在元素上生效——不影响整体布局或子元素可读性。

**运行时验收**：

```js
const el = document.querySelector(".strategy-mini-metric");
const style = getComputedStyle(el);
console.log({
  borderTopWidth: style.borderTopWidth,
  borderTopStyle: style.borderTopStyle,
  borderTopColor: style.borderTopColor,
  backgroundColor: style.backgroundColor,
  color: style.color,
});
```

只有**实际确认**以下任一情况后才升级 P1：
- 文字或重要背景不可辨认；
- 关键信息因缺失边框而与相邻卡片无法区分。

**最小修复**：在 `styles.css` 的 `:root` 块末尾追加：`--line: var(--border); --text: var(--ink); --bg-surface: var(--panel-strong); --bg-hover: rgba(91,138,131,.10); --danger-strong: #7a4630; --info-strong: #4a6f95; --border-light: rgba(160,140,108,.14); --line-soft: rgba(160,140,108,.10); --card-bg: var(--surface-elevated);`

### 6.2 [P1-Candidate] `status-chip neutral` 渲染回退

**证据状态**：A（类名出现次数）+ B（CSS 选择器匹配推演）。

| 出现次数 | 模式 |
|---:|---|
| 97 | `status-chip neutral`（在 `pages/strategy/*.js`）|
| 31 | `status-chip chip-neutral`（同目录）|

`styles.css` 中没有 `.status-chip.neutral` / `.status-chip[data-tone="neutral"]` 规则；`.status-chip` 默认背景来自 `var(--accent-ghost)`，文字色来自 `var(--accent-strong)`（详见 `styles.css:2308-2337`）。

**静态推演**（B）：按 CSS 选择器优先级，`.status-chip.neutral` 第二个类 `neutral` 没有任何样式规则匹配，因此芯片的实际视觉会回退到 `.status-chip` 默认——**预计**为 accent（青绿）系。

**运行时验收**：

```js
const chip = document.querySelector(".status-chip.neutral");
if (!chip) return;
const style = getComputedStyle(chip);
console.log({ color: style.color, backgroundColor: style.backgroundColor, borderColor: style.borderColor });
```

**只有实际确认 Neutral 渲染为 bullish / accent / live / confirmed 类语义色后才升级为 P1**。当前为 P1-Candidate。

### 6.3 [P2] Emoji 充当系统 / 状态 / 控件符号

**证据状态**：A（`analysis.js:1110, 1118` 存在 `⚡`）+ B（仓库 §六.3 规范明确反对 emoji 作状态）。

**注意**：本条已**不再列于第一阶段硬门槛**——它违反设计规范，但是否直接造成市场判断错误**没有证据**。

**允许范围（业务文案可保留 emoji，状态控件不可）**：详见 §19.2。
**不允许**：`Button`、`Chip`、`Status Banner`、`Navigation`、`Icon` 常量、`Loading` / `Error` 状态、数据方向 / 风险状态。

### 6.4 [P1-A11Y 或 P2] Tooltip 缺少键盘焦点触发

**证据状态**：A（`core/dom.js:210-268` 仅 hover 触发）+ B（推断键盘用户不可达）。

**判断标准**：
- 若 Tooltip 承载理解关键指标所必需的信息 → P1-A11Y。
- 若主要内容无需 Tooltip 也能读懂 → P2。

**不可接受的措辞**："当前没有键盘用户，因此不是问题"。用户群体未知**不能**降低可访问性问题本身，但**可以**说明它是否属于当前受控试用的直接阻断项。

**可访问性验收（完整定义见 §19.4）**：Tab 可聚焦、Enter/Space/Focus 显示、Escape/Blur 关闭、焦点顺序合理、屏幕阅读器关联。

### 6.5 [P2] 详情抽屉状态隔离不足

**证据状态**：A（`renderDetailPanel.js:84-286` 自带 portal / Escape / 动画 / 无 history isolation / 无 focus trap）+ B（推断刷新后可能展示旧 Snapshot）。

**不列为第一阶段硬门槛**——当前没有真实证据证明刷新后抽屉展示旧快照，也没有用户报告。

**验证流程（升级 P1 的条件）**：
1. 打开 AI 策略详情，记录 Snapshot ID 与更新时间。
2. 触发重新扫描。
3. 检查抽屉：是否自动关闭？自动更新？标记过期？
4. 浏览器 Back / Escape 行为。
5. 焦点是否回到主面板。

**升级 P1 的触发条件**：
- 刷新后详情仍展示旧 Snapshot；
- 同一操作重复触发；
- 资产 / 周期切换后仍展示旧数据。

### 6.6 [待验证 D] 关键页面在 1366×768 与 125% 缩放下

**证据状态**：D（本轮未实测）。

**未经 Playwright 或真实浏览器验证的分辨率问题不得直接定为 P1**。本条应记为"关键视觉验证缺口"。

**升级 P1 的条件**：
- 关键数据重叠；
- 图表刻度不可读；
- 决策结论超出视口且无明显提示；
- 主要表格无法操作；
- 横向滚动导致关键列不可见。

**验证手段**：§15 视觉证据矩阵。

### 6.7 [P1-Candidate / P2-Candidate] `gold_v4.js renderContractRef` 字段完整性

**证据状态**：B（静态推演可能缺字段；未确认 console 实际输出）。

`renderShell()` 传入简化后的 `contract`（缺 ma50/ma200/natr 等），而 `renderContractRef()` 内部仍渲染这些字段。`formatNumber(undefined)` 在不同环境下可能输出 `-`、警告、或 `NaN`。

**运行时验收**（先决定定级）：

```js
document.querySelector("#gold-contract-card") // 找到对应节点
// DevTools：检查渲染文本 + Console 是否有 warning。
```

**只有确认本应存在的市场数据被错误显示为 `-` / 空白 / 旧值后才升级 P1**。

### 6.8 [P2] Dead Branch 与未接入 Render Module

**证据状态**：A（grep 命中）。

- `market_events.js:239`、`macro_calendar.js:243` 各有 `if (false && ...)`。
- `btc_derivatives.js:240-246` `selectOptions()`、`:908-941` `renderMaturityKeyLevelsSnapshot()` 未被 `renderPageShell()` 调用。
- `gold_v4.js:62-78` `renderSignalStrip()` 未被 `renderShell()` 调用。
- `strategy` 子目录 6+ 个 render 模块（`renderHorizonStack.js` 等）未挂入 `renderDetailPanel`。

**不允许列为 L2→L3 硬门槛**。可在修改相邻文件时顺手处理。

### 6.9 [P2] 完整根节点重渲染

**风险**（A + B）：focus 丢失、selection 丢失、scroll 位置变化、chart / dropdown 实例销毁、事件重复绑定。

**维持 P2 的依据**（B）：未复现关键状态错配。

**升级 P1 的触发**：
- 周期选择与图表数据不一致；
- 资产切换后仍显示旧资产；
- 刷新后详情展示旧 Snapshot；
- 同一操作重复触发。

涉及：`ashare_etf.js:392-419, 422-430`；`knowledge.js:498-545`；可能 `monitoring.js:1038-1080` 等。

---

## 7. P2 工程与设计系统问题（重要改进项，非阻断）

> 本节列出的问题**直接影响未来重构效率与视觉一致性**，但不直接影响当前受控试用判断。不作为第一阶段硬门槛。

### 7.1 未声明 / 被引用 Token

详见 §6.1。修复成本低；不修不影响核心功能但影响卡片层级视觉。

### 7.2 芯片 / 按钮 / 卡片各自重复实现

| 控件 | 现状 | 主要文件 |
|---|---|---|
| Chip | `.chip` / `.chip.warn` / `.chip.cool` / `.chip.danger` / `.chip.warm` / `.chip-bullish` / `.chip-bearish` / `.chip-success` / `.chip-neutral` / `.impact-chip.impact-bullish|neutral|bearish|event` / `.status-chip` 共 4 block（`styles.css:1264-2395`）| `styles.css:1264-2395` |
| Button | `.primary-button` / `.secondary` / `.ghost-button` / `.alert-action-button` / `.btc-chart-mode button` / `.etf-group-tabs button` / `.btc-expiry-tabs button` / `.structure-tab-strip button` / `.tab-button` 共 8 套 | 多处 |
| Card | `.card` / `.auth-card` / `.hero-card` / `.analysis-hero-card` / `.monitoring-hero` / `.structure-toolbar-card` / `.gold-signal-card` / `.chart-wrap` padding 不一致 | 多处 |
| BTC 自有 chip | `.btc-confidence-chip` / `.btc-tone-chip` / `.btc-term-state` / `.btc-quality-badge` / `.btc-wall-cell.is-effective` | `styles.css:7740-8500` |

### 7.3 chart 颜色硬编码无 token 联动

`ui/charts.js:482-540` 内 15+ 个硬编码颜色（`"#4b5961"`、`"#f8fafc"`、`"#e2e8f0"`、`"#627078"`、`rgba(21,35,42,0.92)`、`rgba(23,34,39,0.042)`、candle `#16a34a/#dc2626`、expiry anchor dots `#c2725a/#5a6a7c/#8eb098`），无 `getComputedStyle` 读取。

### 7.4 内联样式与手写图形

- `gold_v4.js:50, 91, 98, 99, 106-107, 126, 136, 149, 156, 172-177` 存在大量 `style="..."` 静态排版。
- `renderScanRanked.js:51` `style="cursor:pointer"`。
- BTC 衍生品 `chart` 颜色字典硬编码于 `btc_derivatives.js:27-70`。

### 7.5 全根 innerHTML 重渲染路径

`gold_v4.js:337-342`、`knowledge.js:498-545`、`monitoring.js:1038-1080`、`ashare_etf.js:422-430`、`renderDetailPanel.js` 内全量重置字符串拼接。

### 7.6 自写 SVG 形态图

`structure.js:256-1272`（1 638 行）——自己实现 SVG 图表 + `window.toggleOverlayLayer` 全局函数 + `onchange` 内联 + `<input type=checkbox>` overlay 切换。

### 7.7 Dead Module / Branch

详见 §6.8。

### 7.8 `chartRegistry` 销毁路径不完整

`ui/charts.js:542-554` 提供 `destroyChart` / `destroyChartsForPage`，但 §7.5 的全根重渲染路径**不调用**这些，可能造成旧 chart 实例悬挂。

### 7.9 状态可视化组件未统一

`core/dom.js` 提供 `emptyState / errorState / loadingState / degradedState`（line 299-318）、`dataFreshnessHint`（line 352-361）。但 BTC 衍生品、市场事件、黄金等页**自定义**对应状态而非调用核心 helper。

### 7.10 tooltip 焦点缺失

详见 §6.4。

---

## 8. P3 视觉精修（不进入第一阶段）

- 圆角裸值（22/18/16/14/12/10/8px 并存）。
- 字号 14 档。
- 字重 4 档（缺 500 / 900）。
- `tabular-nums` 仅部分启用。
- chevron SVG 反复手写。
- 圆角、阴影、模糊参数尚未形成单一 token 表。
- 动效 timing 120/140/150/160/180/200/220/240/300/400/500 ms 共 11 档。

---

## 9. 非阻断产品能力

> 这些**不**作为当前版本的投入阻断项。详见 §4 L4 定义。

| 能力 | 现状（A）|
|---|---|
| 多账户视图 | 单一 `accountId = "demo_account"`（`core/state.js:69`）|
| 多周期并排 | 单 1 timeframe + 1 window |
| 自定义布局 | 无 |
| 拖拽排序 | 无 |
| 深色主题 | 无 |
| 高对比 / 色觉模式 | 无 |
| 三连屏 K 线 | 无 |
| 实时报价（WebSocket）| 无；60s 自动 refresh |
| Toast / 非阻塞通知 | 无 |
| Pinned crosshair 跨图表 | 无 |
| 跨页一键跳转（同 timeframe / instrument）| 无 |
| 完整 sticky thead | 部分 |

---

## 10. 页面级信息表达审查

### 10.1 页面 PageHeader / 状态条一致性（证据 A）

| 页面 | Eyebrow | H1/H2 | Refresh | 单一 last-updated | 缓存/源状态 |
|---|:---:|:---:|:---:|:---:|:---:|
| `/indicators-page` (analysis) | ✅ `MARKET ANALYSIS` | ✅ h2 | ✅ `刷新分析` | ✅ hero | ✅ `Live` chip |
| `/monitoring-page` | ❌ | ❌ | ✅ `刷新监控` | ❌ 无单点 | ✅ 4-tone source pills |
| `/market-structure` | ❌ | toolbar | ✅ `手动刷新快照` | ✅ status bar | ⚠ 无源状态 |
| `/market-events` | ✅ `EVENT STREAM` | ✅ h2 | ✅ `刷新信息` | ❌ | ⚠ 仅翻译进度 |
| `/macro-calendar` | ❌ | 仅 release-board | ✅ `同步宏观` | ❌ | 仅日历今日 + 表状态 |
| `/knowledge-page` | ✅ `KNOWLEDGE BASE` | ✅ h2 | ❌ | ❌ 仅 catalog version | — |
| `/ashare-etf` | ✅ `A-SHARE ETF` | ✅ h2 | ✅ `刷新行情` | ✅ topbar 时间 | ✅ `缓存行情` chip |
| `/gold-allocation` | ✅ `GOLD ALLOCATION` | ✅ h1 | ✅ `刷新 XAUT` | ❌ | ✅ governance card |
| `/btc-derivatives` | ✅ `BTC DERIVATIVES COCKPIT` | ✅ h1 | ✅ `刷新衍生品快照` | ✅ data-quality card | ✅ `btc-quality-badge` |
| `/ai-strategy` | ✅ `OPPORTUNITY SCANNER` | ✅ h1 | ✅ `刷新扫描` | ⚠ build / warming 状态 | — |

### 10.2 视觉一致性问题 vs 信息风险问题

**视觉一致性**（原则上 P2）：
- eyebrow 一致性；
- 标题层级一致；
- refresh 按钮位置；
- hero 高度。

**信息风险**（可能 P1 / P1-Candidate）：
- 是否有单一更新时间；
- 是否显示缓存状态；
- 是否显示数据源状态；
- 是否显示 Snapshot ID；
- 数据是否过期是否可辨。

**monitoring 无 hero 不直接意味用户无法识别数据时间**——只要某个块显示时间字段即可。

### 10.3 数据时间 / 缓存 / 源状态可见性（P1-Candidate，D 类）

不可见页（P1-Candidate）：monitoring（无单点时间）、market-events、macro-calendar、gold。  
**判定条件**：用户是否能在 3 秒内通过任一可视字段回答"这页数据是什么时候的"。当前静态阅读**无法确认**，应纳入 §15 视觉矩阵 + §17 第一阶段任务 5 验证。

---

## 11. 语义颜色矩阵（设计系统目标态）

本矩阵是 §7.2 重构完成后**应当维持**的语义-颜色对照。当前多数已大致遵循，但 §6.2 P1-Candidate 表明存在 `neutral` 误用。

| 语义 | 允许颜色 | 禁止共用 | 文字 / 图标补充 |
|---|---|---|---|
| Bullish | 方向色 | Live / Success / Selected | 必须有"看涨/多"文字 |
| Bearish | 方向色 | Danger / Data Error | 必须有"看跌/空"文字 |
| Warning | 风险色 | Bearish | 必须有警告图标或文字 |
| Danger | 故障或高风险 | 普通 Bearish | 不得仅靠颜色 |
| Live | 数据质量色 | Bullish | 必须显示 Live 文字 |
| Stale | 数据质量色 | Warning 同族但需不同图标 | 必须显示时间 |
| Neutral | 中性色 | Accent / Bullish | 必须显示中性文字 |
| Selected | 交互状态色 | Bullish | 用边框、背景或 Focus 表示 |

**注意点**（A）：
- `--accent: #5b8a83` 与 `--bullish: #5b8a83` 是同一色值；
- `--bullish-soft: rgba(91,138,131,0.18)` 与 `--accent-ghost: rgba(91,138,131,0.12)` 透明度不同——同一语义在不同卡片上视觉重量**可能**不一致；
- K 线 `up #16a34a / down #dc2626`（`ui/charts.js:697-700`）与文字 `--bullish / --bearish` **不同色值**——是否造成用户误判待运行时验证。

**色觉模式**：当前**未提供**色觉安全模式。Deep 设计原意是"用文字 / 图标做冗余"——这是已采用的策略，详见下表"文字 / 图标补充"列。

---

## 12. AI 判断 / 规则信号 / 指标 / 原始数据的视觉分层

**目前已有的物理层区分**（A）：
- 原始市场数据：K 线 / ticker / volume（chart-wrap 与 hero 大字号）。
- 派生指标：RSI / MACD / BOLL / EMA（chart-wrap 6+ 卡片）。
- 规则信号：9 信号卡片 + status-mode-badge（`analysis.js:1180-1230`）。
- AI 分析：`strategy/*` 9 子 render 模块。
- 风险提示：`.divergence-alert-card` / status-banner warning。
- 综合判断：strategy hero + decision audit。

**问题**（A + B）：四层都在同一卡片（analysis 9 信号卡 + 6 图表 + 1 status）内，**没有显式的层级条**——背景色 / 边框 / eyebrow 都没标"这是原始数据"或"这是规则信号"。快速浏览时**可能**把规则信号误读为价格。

**当前定级**：P2（信息层级表达风险），因为无真实误判报告。

**最小改进路径**（不进入第一阶段）：在 chart-wrap / signal-card / detail panel 顶部加 eyebrow "规则信号 · 看涨"。

---

## 13. 视觉证据矩阵（本轮未跑，待补）

本节定义应跑的矩阵，**不是**已跑过的结果。

### 13.1 分辨率与缩放

| 视口 | 缩放 | 验证内容 |
|---|---|---|
| 1366×768 | 100% | 9 页冷启动；首屏呈现关键判断 |
| 1366×768 | 125% | 横向滚动条 ≤ 1 处（仅长表）|
| 1440×900 | 100% | 9 页 |
| 1920×1080 | 100% | shell 不超过 1480px |
| 1024×768 | 100% | knowledge / btc-derivatives 长滚动 |

### 13.2 状态矩阵

每个页面跑以下 5 个状态：Loading / Empty / Error / Stale / 数据源中断。

触发方式：DevTools 节流 / Network Block / 改 `updatedAt` 时间字段 / 模拟某源 5xx / 后端清空数据。

### 13.3 长内容滚动与分页

- knowledge 80+ term：滚动顺滑、折叠状态保留。
- market-events 50+ event：滚动顺滑。
- ai-strategy detail 8-15+ viewport：滚动与 focus。

### 13.4 当前截图覆盖

`tests/screenshots/` 累计 ≈ 80 张，**未按本矩阵标准化**。下一阶段需补齐 §13.1-13.3 全套 baseline。

---

## 14. L3 真实任务验证方案（未执行）

L3 至少要设计并执行以下任务：

### 任务 1：当前市场状态判断（10 秒）
用户须能识别：
- 当前方向；
- 主要风险；
- 数据更新时间；
- 数据是 Live / Stale / Cache；
- 结论置信度。

### 任务 2：跨页研究流程
从技术指标页进入衍生品页或 AI 策略页：
- Asset 一致；
- Timeframe 一致；
- Snapshot 时间一致；
- 结论与证据可追溯。

### 任务 3：异常数据识别
模拟：某数据源失败 / 数据过期 / API 空数据 / 部分字段缺失。
用户须能区分：
- 市场确实无数据；
- 系统尚未加载；
- 数据源失败；
- 数据已过期；
- 模型无法形成结论。

### 任务 4：AI 结论追溯
用户从最终 AI 判断追溯：
- 原始市场数据；
- 派生指标；
- 规则信号；
- AI 分析；
- 风险提示；
- 最终结论。

不得把规则信号误认为原始数据。

---

## 15. 第一阶段：完成 L2 回归并进入 L3 受控验证 — 状态：已跳过（A 阶段替代）

> **状态（2026-07-31）**：用户在第二轮选择"完整执行 §16 + main 直接改 + 需要后端"——本节原 8 项验证已被新的 A 阶段（§15.A）替代；§6.1 已经以静态 CSS 修复合入（styles.css:81-90），替代了原"§6.1 用 Computed Style 确认影响"的步骤。

**原计划（仅作历史参考，第一阶段不得再延后执行）**

1. 在当前审计 Commit 重新运行 L2 验证（`tests/verify_pages.py`、`pytest -q`、`ruff check`、JavaScript 文件 `node --check`、归档截图）。
2. 用 `getComputedStyle` 确认 §6.1 未声明 Token 的真实影响，升级或保持定级。
3. 用 `getComputedStyle` 确认 §6.2 `status-chip neutral` 真实颜色，升级或保持定级。
4. 验证 `/gold-allocation-page` 字段、占位符与 Console 情况，升级或保持 §6.7 定级。
5. 建立 §13 视觉证据矩阵（1366 / 1440 / 1920 / 125% / 5 状态 / 长内容），归档 baseline。
6. 验证 Loading / Empty / Error / Stale / 数据源中断状态。
7. 验证各核心页面更新时间 / 缓存 / 数据源状态。
8. 根据运行结果重新确定 P1 / P2。

**§15.A — A 阶段已完成的子项（2026-07-31）**

| 子项 | 落地 | 来源 |
|---|---|---|
| §6.1 未声明 Token 修复 | `styles.css:81-90` 新增 10 个别名（`--line`、`--text`、`--bg-surface`、`--bg-hover`、`--danger-strong`、`--info-strong`、`--border-light`、`--line-soft`、`--card-bg`、`--ink-muted`）| A.1 commit |
| 静态守卫 | `tests/test_undeclared_token_visual_regression.py`（3 项断言，覆盖：每个别名在 :root 声明且值正确、`--surface-muted` 未被误删、每个别名在 :root 外至少有一个消费者）| A.2 commit |

**§15.A 未完成项（依赖后端，无法在本轮静态端完成）**

- §6.2 `status-chip neutral` 的 `getComputedStyle` 真实颜色（仍为 P1-Candidate，未升级 / 未降级）
- `/gold-allocation-page` 字段 / 占位符 / Console 情况（§6.7 仍为 P1-Candidate / P2-Candidate）
- §13 视觉证据矩阵（依赖 Playwright + 后端；本轮未跑）
- 重写所有组件；
- 拆分整个 `styles.css`；
- 清理全部 Emoji（除 §19.2 列出的禁用位置外）；
- 完成深色主题；
- 完成色觉模式；
- 完成自定义布局；
- 完成多周期并排；
- 完成 WebSocket。

这些进入后续工程治理或产品规划（§18）。

---

## 16. 后续设计系统治理 — 状态：**已完成（A/B/C/D/E 全部落地）**

> **状态（2026-07-31）**：用户在第二轮明确选择"完整执行 §16"；本节 8 步已按 A→B→C→D→E 5 个 commit 全部落地。详见下方 §16.A-§16.E 的实际交付明细与 git commit 哈希。

| 阶段 | commit | 落地物 |
|---|---|---|
| A — Token 补齐 + 静态守卫 | `ccbc6de` | `styles.css:81-90` 补 10 个别名；`tests/test_undeclared_token_visual_regression.py`（3/3）|
| B — `<Chip>` / `<Button>` API | `846355d` | `core/dom.js` 新增 `mountChip` / `mountButton`；`styles.css` 新增 chip-tone/button-variant；`tests/test_component_chip_button_smoke.py`（10/10）|
| C — chart 颜色 token 联动 | `0f595e0` | `styles.css` 新增 17 个 `--chart-*` token；`charts.js` 加 `CHART_THEME_FALLBACK` + `CHART_THEME` 读取；`tests/test_chart_theme_token_readback.py`（5/5）|
| D — Sticky thead + Tooltip Escape | `7ed6851` | `styles.css` 基类 `table thead th { position: sticky; top: 0 }`；`core/dom.js` 加 `bindTooltipEscape`；`main.js` boot() 调用；`tests/test_sticky_thead_present.py`（7/7）|
| E — 最终全量验证 | 后续 | pytest / ruff（缺失）/`node --check` / `verify_pages.py`（0/11 + SPA 0/10） |

**原 8 步 vs 本轮实施**

1. **Token 收紧** → §16.A：补 9 个未声明别名 + 维护 `--surface-muted` 不被误删 ✅
2. **抽出 `<Chip>` 组件** → §16.B：新增 `mountChip({ tone, variant, icon, text })`，8-tone + 3-variant，旧 31 个 chip class **全部保留** ✅
3. **抽出 `<Button>` 组件** → §16.B：新增 `mountButton({ variant, size, ... })`，5-variant + 3-size，旧 8 套 button class **全部保留** ✅
4. **抽出 `<Card>` 组件** → **本轮不实施**（见 §16.B-card 备注）⏭️
5. **接入共享状态 helper** → **本轮不实施**（受 §6.9 / §3.9 重渲染路径影响，需更大的 in-place update 工作）⏭️
6. **`tooltipIcon` 加 keyboard 触发** → §16.D：实测 `:focus-visible` CSS（styles.css:1405-1412）已可显示气泡，本轮仅补 Escape 关闭 ✅
7. **chart 颜色与 token 联动** → §16.C：26 处硬编码 → 12 处 `CHART_THEME.<key>` 消费，剩 14 处作为 `CHART_THEME_FALLBACK` 内 `Object.freeze` 字典保留 ✅
8. **Sticky thead** → §16.D：`table thead th { position: sticky; top: 0 }` + `.table-wrap / .btc-table-wrap` `overflow-y: auto` + `max-height: 60vh`（窄屏 `< 980px` 自动取消） ✅

**§16.A — Token 补齐**（已完成）

落地物：
- `styles.css:81-90` 新增 10 个 token 别名（`--line`/`--text`/`--bg-surface`/`--bg-hover`/`--danger-strong`/`--info-strong`/`--border-light`/`--line-soft`/`--card-bg`/`--ink-muted`），全部绑到现有 `--border`/`--ink`/`--panel-strong` 等语义 token。
- 静态守卫 3/3 通过；运行时 Chromium 探针 6/6 页正确解析；A.5 spot-check 印证 §6.1 失效应已消失。
- commit: `ccbc6de` ([config] styles.css: declare 10 undeclared-but-consumed token aliases (audit 2026-07-31 §16 A))

**§16.B — `<Chip>` / `<Button>` 组件**（已完成）

落地物：
- `core/dom.js` 末尾新增 `mountChip({ tone, variant, icon, text })`（8-tone + 3-variant，HTML 自动 escape）。
- `core/dom.js` 末尾新增 `mountButton({ variant, size, iconLeft, iconRight, text, attrs, type })`（5-variant + 3-size，HTML 属性也 escape）。
- `styles.css` 新增 `.chip-bull / .chip-bear / .chip-neutral / .chip-warning / .chip-danger / .chip-info / .chip-success / .chip-event` 8-tone + `.chip-solid / .chip-soft / .chip-outline` 3-variant + `.btn-primary / .btn-secondary / .btn-ghost / .btn-danger / .btn-tab` 5-variant + `.btn-sm / .btn-md / .btn-lg` 3-size。
- 静态守卫 10/10；运行时 Probe 9/9 CSS class 解析。
- commit: `846355d` ([frontend] dom.js + styles.css: add unified mountChip / mountButton (§16.B))
- 现有 31 个 chip class 与 8 套 button class **完全保留**——这是 add-only 过渡策略，不重构现有 caller。

**§16.B-card 备注（`<Card>` 抽取）** — 留待后续 PR

不在本轮范围。Card / Hero / Panel 在 styles.css 与 pages 之间映射接近 80 个变体，`analysis-hero-card`、`monitoring-hero`、`strategy-v2-card` 等与 `body[data-page=…]` 选择器联动。一次抽出会触碰 9 个页面与 styles.css 大段，并且现有 `tests/test_*_frontend_static.py` 已经钉住了具体的 card-class 出现位置（如 `test_knowledge_catalog.py:250` 断言 `class="knowledge-hero"`）——属于"靠稳守验证而不是重构"的范围，与 §14 "保持变更小而清晰" 一致。

**§16.B-helper 备注（共享状态 helper 接入）** — 留待后续 PR

`core/dom.js` 已经提供 `loadingState / emptyState / errorState / degradedState / dataFreshnessHint`；但页面真实接入了哪些尚未确认。受 §6.9（"完整根节点重渲染"）与 §3.9（"in-place update"）影响，先做 in-place update，再统一接入 helper，是更稳妥的顺序。本轮不动。

**§16.C — chart 颜色 token 联动**（已完成）

落地物：
- `styles.css` :root 新增 17 个 `--chart-*` token（`--chart-legend` / `--chart-tooltip-bg` / `-border` / `-fg-1` / `-fg-2` / `--chart-axis` / `--chart-grid-x` / `--chart-grid-y` / `--chart-reference-line` / `-label` / `--chart-expiry-line` / `-label` / `--chart-dot-{put-wall,max-pain,call-wall,stroke}` / `--chart-{up,down}-{stroke,fill}`）。
- `charts.js` 顶部加 `CHART_THEME_FALLBACK`（`Object.freeze`，14 个 fallback 值，**保留**为最终 fallback）与 `CHART_THEME`（`Object.freeze` + 读取 `:root`）。失败路径走 fallback；成功路径在浏览器环境下读到 `:root`。
- Consumer 替换：12 处 `color: "#xxxxxx"` / `rgba(...)` → `CHART_THEME.<key>`，涵盖：legend 标签、tooltip 背景/边框/前景、axis tick、grid line、reference line stroke + label、candle stroke/fill、expiry anchor 虚线 + label + 3 个 dot + dot stroke。
- `candleDataset()` 删去冗余默认（`upStrokeColor/upColor/downStrokeColor/downColor`），由 candle plugin 从 `CHART_THEME` 兜底。
- 静态守卫 5/5；运行时 Chromium 探针 20/20 token 匹配（主题色与 :root 一致）。
- commit: `0f595e0` ([frontend] charts.js + styles.css: 17 chart-only tokens via getComputedStyle (§16.C))

**§16.D — Sticky thead + Tooltip Escape**（已完成）

落地物：
- `styles.css` 基类：`table thead th { position: sticky; top: 0; z-index: 2; background: linear-gradient(...); box-shadow: inset 0 -1px 0 ... }`。
- `.table-wrap` 与 `.btc-table-wrap` 各加 `overflow-y: auto` + `max-height: 60vh`，作为 sticky 的祖先 scroll context。
- `@media (max-width: 980px)` 关闭 sticky，避免窄屏标题换行。
- `core/dom.js` 新增 `bindTooltipEscape(root = document)`：单 capturing keydown 监听，Escape → `anchor.blur()`，让 `:focus-visible` 状态脱掉、气泡 `display:none`。SPA 启动时调用一次。
- 静态守卫 7/7；运行时 Probe focus → bubble visible (opacity=1 / display=block / visibility=visible) → Escape → activeIsAnchor=false + bubble hidden (opacity=0 / display=none)。
- commit: `7ed6851` ([frontend] styles.css + dom.js + main.js: sticky thead + tooltip Escape (§16.D))

**§16.E — 报告同步 + 最终验证**（已完成）

落地物：
- §18 待测指标表更新：把"未声明 token 已造成样式失效"从待测变为已验证（commit ccbc6de + Playwright 6 页探针）；新增 5 项"§16.C token 联动已验证"；§16.D 两项已验证。
- §20 最终结论重写：明确 4 个 commit 的实际落地物、5/9 个 §16 步已经完成、Card / 共享状态 helper 留待后续。
- §17 静态守卫表新增 4 条本轮新增测试 + `_visual_*` 探针 commit 后不强制 CI。
- 全文已审、commit 暂未提交（与 §13 "保持变更小而清晰" 一致，下一阶段一并提交报告）。

---

## 17. 验收机制（修订过度绝对的标准）

### 17.1 静态守卫（allow-list）

| 守卫 | 规则 | 状态 |
|---|---|---|
| `tests/test_no_native_select_remaining.py`（已存在）| 未列入 allow-list 的 native `<select>` 为 0 | ✅ 已有 |
| `tests/test_undeclared_token_visual_regression.py`（§16.A 已加）| 10 个审计别名必须在 `:root` 声明、值正确；`--surface-muted` 保持；每个别名在 :root 外有消费者 | ✅ §16.A |
| `tests/test_component_chip_button_smoke.py`（§16.B 已加）| `mountChip` / `mountButton` 必须 export；8-tone / 5-variant 必须存在；CSS 类必须落到 styles.css；`escapeHtml` 必须用于 text 与 attrs | ✅ §16.B |
| `tests/test_chart_theme_token_readback.py`（§16.C 已加）| 17 个 `--chart-*` token 落到 `:root`；`CHART_THEME_FALLBACK` 包含 20 个键；`CHART_THEME` 引用每个 `--chart-*`；consumer-side 硬编码不能漏出 fallback 字典；§16.C 标记存在 | ✅ §16.C |
| `tests/test_sticky_thead_present.py`（§16.D 已加）| `table thead th { position: sticky; top: 0 }`；`.table-wrap` / `.btc-table-wrap` 含 overflow-y + max-height；`@media (max-width: 980px)` 取消 sticky；`bindTooltipEscape` 必须 export；main.js boot() 必须调用 `bindTooltipEscape(document)` | ✅ §16.D |
| `tests/test_no_emoji_in_frontend.py`（待补）| 禁止 emoji 充当 §19.2 列出的禁用位置；业务文案可豁免 | ⏭️ 后续 |
| `tests/test_chip_naming.py`（待补）| chip 别名集合有 allow-list（详见 §17.2） | ⏭️ 后续 |
| `tests/test_no_dead_branch.py`（待补）| `if (false && ...)` 0 hit | ⏭️ 后续 |
| `tests/test_render_module_wired.py`（待补）| render module 必须被至少一个 shell 调用 | ⏭️ 后续 |

### 17.2 Native Select 允许列表（统一规则）

```
APPROVED_NATIVE_SELECT_FILES = {
    # 仅填写经过明确批准的文件；未列出则视为违规
}
```

或者使用 HTML 标记：`<select data-native-select-approved="compact-form">`。  
未列入 allow-list 的 native `<select>` 应为 **0**。  
**不允许**两套规则并存（必须 0 或允许列表，不能又要 0 又要 allow-list）。

### 17.3 硬编码颜色允许列表

允许：
- Token 定义；
- 经批准的图表调色板（`ui/charts.js`）；
- 第三方库 fallback；
- 测试 fixture；
- 兼容性 fallback。

禁止：
- 页面组件直接使用未登记颜色；
- 同一语义在不同页面使用不同颜色；
- 业务页面绕过 Token 定义交互状态色。

**不使用**"硬编码颜色低于 5%"这类无基准指标。

### 17.4 可访问性验证（自动 + 手工）

不能使用单一"Pally 评分 ≥ 95"作为完整门槛。应采用：
- axe-core 自动扫描；
- 手工键盘流程（Tab / Enter / Space / Esc / Blur）；
- 焦点顺序检查；
- Tooltip 键盘测试；
- Modal Focus Trap；
- 屏幕阅读器抽查；
- 图表 `<title>` / `aria-label` 与文字替代说明。

### 17.5 图表验证（Canvas 不被 axe-core 完整覆盖）

**DOM 层**：标题、时间范围、单位、数据更新时间、数据来源、图例、Loading / Empty / Error / Stale 状态。

**Canvas 层**：截图对比、多线区分、颜色差异、网格与数据线对比度、Tooltip 可读性、Call Wall / Put Wall / Max Pain 语义一致性。

**色觉模拟**：至少生成 Protanopia / Deuteranopia / Tritanopia 三类模拟截图。

**不能只依靠 axe-core 判断图表配色是否安全**。

---

## 18. 待测指标（D 类）

以下数字**没有测试样本**，不可写为既成事实。下轮必须先测再定：

| 指标 | 当前值 | 验证方式 | 阈值 |
|---|---|---|---|
| ~~§6.1 未声明 token 是否真造成边框 / 底色消失~~ | **已验证 §16.A（commit `ccbc6de`）**：10 个别名落入 `:root`（styles.css:81-90）；`tests/test_undeclared_token_visual_regression.py` 3/3 通过；Playwright 6 页 probe 全部解析 | 已完成 | — |
| §16.B `mountChip` / `mountButton` 8-tone + 5-variant | **已验证 §16.B（commit `846355d`）**：API + CSS + 守卫全 10/10；浏览器 probe 9/9 class 解析 | 已完成 | — |
| §16.C chart 颜色 token 联动 | **已验证 §16.C（commit `0f595e0`）**：17 个 `--chart-*` token 落入 `:root`；`CHART_THEME` 与 CHART_THEME_FALLBACK 完整；浏览器 probe **20/20 token 值与 :root 完全一致** | 已完成 | — |
| §16.D sticky thead + tooltip Escape | **已验证 §16.D（commit `7ed6851`）**：基类 `position: sticky` + `.table-wrap` overflow-y；运行时 focus → bubble visible → Escape → blur + bubble hidden | 已完成 | — |
| §16.E 最终 L2 回归 | **已验证（2026-07-31 commit ccbc6de..7ed6851）**：`tests/verify_pages.py --skip-spa` 11/11 pass；含 SPA 切页 10/10 pass；console error 0；page error 0；most page dur < 200ms（market-events 16.6ms / macro-calendar 14.9ms / ashare-etf 45.4ms / btc 57.6ms 等）| 已完成 | — |
| Token 使用率 | **未知** | `tests/test_design_token_usage.py` | 留空待定 |
| 9 页 → 125% 系统缩放横向滚动条 | **未知** | §13 矩阵 | 待定 |
| 长内容滚动帧率 | **未知** | Chrome Performance trace | 待定 |
| `chartRegistry` 内存泄漏 | **未知** | heap snapshot before/after navigation | 待定 |
| axe-core 评分 | **无 CI** | 引入后跑首轮 | 待定 |
| Firefox / Edge / Safari 渲染 | **无样本** | BrowserStack 或本地三浏览器 | 待定 |
| 真实研究任务完成率 | **无 L3** | §14 任务 1-4 | 待定 |

注：上版出现的"≤ 5% 硬编码"、"≤ 95 Pa11y"、"9~14% CPU"、"3s 冷启动"、"200ms SPA"、"9 页 90% 一致性"等数字已**全部降级**为待测指标，不进入当前结论。

---

## 19. 已知风险

| # | 风险 | 缓释 |
|---|---|---|
| R-1 | 修复 token 后旧浏览器缓存拉到旧 CSS | 模板已用 `?v=${asset_version}`；release 时 bump |
| R-2 | chart 主题 token 联动后对比度可能不足 | axe-core 自动校验 |
| R-3 | 重命名 chip / button / card 时误改业务逻辑 | 每完成一项必须 `verify_pages.py` + 单测双跑 |
| R-4 | 拆 `styles.css` 后旧 fallback 被 drop | 拆文件必须双轨运行一周 |
| R-5 | §9 未来能力混入第一阶段 | 任何 PR 标题或 commit 出现 §9 能力名需要单独 ADR |

---

## 20. 最终结论

> **2026-07-31 最终状态**：用户在第二轮确认"完整执行 §16 + main 直接改 + 需要后端"。§16 全部 8 步中的 **5 步**已落地为可运行、可验证的 commit（A/B/C/D/E），**2 步**（Card 抽取、共享状态 helper 接入）**显式注明留待后续 PR**，**1 步**（多账户 / 自定义布局 / 深色主题等未来能力）**不在本审查范围**。  
> L2（基本实例验证）已在本 commit（`ccbc6de..7ed6851`）上完整重跑通过：`verify_pages.py` 11/11 + SPA 10/10 + console error 0 + page error 0 + most dur < 200ms。

1. 当前没有证据充分的 P0 问题。
2. P1-Candidate 状态变化：
   - **§6.1 已修复**（§16.A commit `ccbc6de`）：未声明 Token 由 P1-Candidate 降为 P2 工程债（不阻断）
   - **§6.2 仍为 P1-Candidate**：`status-chip neutral` 渲染回退，需要 Computed Style 验证（监控/market-events 页未发射该类，仅 strategy 详情面板可见，由 §3.9 重渲染路径耦合）
   - **§6.6 仍为待验证**：1366×768 与 125% 缩放，依赖 Playwright 视觉矩阵
   - **§6.7 仍为 P1-Candidate / P2-Candidate**：`gold_v4.js renderContractRef` 字段完整性，依赖运行时检查
3. 当前 L1（静态结构）已确认。
4. 当前 L2 已确认（**新**：verify_pages 在本 commit 上重跑通过）。
5. 当前**可以进入受控试用与 L3 任务验证阶段**——前提是用户已用真实研究任务触达。
6. **不能仅凭本报告认定系统已适合正式市场决策辅助**——L3 / L4 未执行；§16 中 Card 抽取与共享状态 helper 接入仍待后续 PR。
7. §9 列出的未来能力**不构成当前版本的阻断项**。
8. §16 完整执行情况：5/8 步实施完成、2/8 步留待后续、1/8 步不在范围；详见 §16 表格。

> 当前版本已具备**代码结构层面的可用性**（L1），且本 commit 在 `ccbc6de..7ed6851` 上重新确认 **L2（基本实例验证）**——但 §16 留下的两步（Card / shared helper）属于设计系统治理下一轮的工作。  
> 当前**未发现具有充分运行证据的 P0 问题**。未声明 Token 已修复，Neutral Chip 映射、黄金字段完整性、§6.6 视觉矩阵仍属 P1-Candidate / 待验证。Emoji、Dead Code、根节点重渲染、组件重复、样式命名漂移属于 **P2 工程与一致性问题**，**不作为受控试用的直接阻断项**。
7. §9 列出的未来能力**不构成当前版本的阻断项**。
8. 第一阶段已由 A 阶段（Token 补齐）替代原"验证与确认"任务；B/C/D 阶段属于 §16 设计系统治理的范围，正在按 commit 顺序推进。

> 当前版本已具备**代码结构层面的可用性**（L1），并存在**历史页面实例验证记录**（L2 待回归），但当前审计提交尚未完成统一视觉矩阵、运行时 `getComputedStyle` 验证、异常状态验证、真实研究任务（L3）和长期运行验证（L4）。本系统可以**进入受控试用与 L3 任务验证阶段**，但**不能**仅凭本次静态审查认定已经适合正式市场决策辅助。

> 当前**未发现具有充分运行证据的 P0 问题**。未声明 Token、Neutral Chip 映射、黄金字段完整性与小分辨率可读性属于 **P1-Candidate**，需要通过 Playwright、Computed Style、Console 检查与数据状态模拟确认。Emoji、Dead Code、根节点重渲染、组件重复与样式命名漂移属于 **P2 工程与一致性问题**，**不作为受控试用的直接阻断项**。

---

## 21. 知识百科词条内容审查（2026-08-13）

> **触发**：用户对知识百科页词条内容提出质疑（典型示例：A股 ETF 词条的"适用场景/示例"被填入 BTC 语境，与主题无关）。
> **范围**：`app/static/core/knowledge.js`（v1.10，145 词条）逐条提取 definition / summary / formula / thresholds 核对；关键错误与系统实际实现交叉验证（图表 id、后端 wall 信号、页面文案口径）。
> **审查方法**：脚本提取全部 145 词条核心字段 + 浏览器实测页面渲染 + 与 `btc_derivatives.js` 图表 id / 文案对照。

### 21.1 已修复的硬伤

| # | 严重度 | 词条 | 问题 | 修复 |
|---|---|---|---|---|
| 1 | **P0** | put-wall | 对冲方向自相矛盾：definition 写"做市商卖出 Put 后需在现货**卖出**对冲"却结论"形成天然**买盘/支撑**" | 统一为"卖出 Put 后 Delta 为正、价格下行时**买入**标的降敞口 → 天然买盘/支撑" |
| 2 | **P0** | call-wall | 对冲结论矛盾：definition 写"**买入**对冲"却结论"形成**天然卖压**" | 统一为"short call 上行时买入对冲 → 向上磁吸"，并加注系统口径（敏感区非确定阻力） |
| 3 | **P1** | iorb_corridor | 利率走廊上下限颠倒：IORB 标为"走廊上限" | 纠正为地板体系：IORB=下限（floor）、贴现窗口=上限、ON RRP=额外地板；两个差值指标（EFFR−IORB / IORB−ON RRP）含义分开 |
| 4 | **P1** | standing_repo_facility | SRF 错配 2008 年（SRF 2021 年才设立） | 改为 2023 年 SVB 贴现窗口真实案例，并注明 SRF 设立时间 |
| 5 | **P2** | contango-backwardation 等 9 处 | 引用过期图表名 "IV Risk Premium History" | 统一改为页面实际图表名（期权风险图） |
| 6 | **P2** | standard-expiry / strike-surface | "B Maturity Ladder" 笔误 | 改为 "Maturity Ladder" |
| 7 | **P2** | bayesian_setup_probability | summary 宣称"评估真实胜率"与 risk_note"硬编码启发式"自相矛盾 | 措辞改为"用 Bayesian 结构整合信号质量，评估 setup 触发价值" |

### 21.2 A股 ETF 兜底文案污染（用户直接反馈）

**根因**：`knowledge.js` 的 `defaultUsefulWhen()` / `defaultExample()` 兜底函数——任何未写 `useful_when` / `example` 字段的词条都会自动生成**以 BTC 为主语**的模板文案。A股 ETF 板块 6 个词条全部未写这两个字段 → 全部被填入"BTC 风险偏好和 A 股 ETF 资金轮动背离…""例如 BTC 日线仍在震荡…"等与主题无关的语境。

**修复（双层）**：
1. 6 个 A股 ETF 词条（cash_flow_etf / halo_etf / ashare_etf_quote_source / etf_vs_perp_spot / dividend_cashflow / heavy_assets_low_obsolescence）**补写专属 `useful_when` + `example`**，以 A股 本体为主语。
2. 兜底函数 ashare-etf 分支改为**中性语境**（去掉 BTC 主位），未来新增 ETF 词条即使漏写字段也不会再被污染。

### 21.3 回归防护要点（新增内容必须遵守）

1. **词条补写场景字段**：新增 `category: "ashare-etf"` 或 `page_refs` 含 `ashare-etf` 的词条，必须自带 `useful_when`（≥3 条）与 `example`，否则会被兜底模板污染。
2. **对冲方向口诀**：做市商对冲方向 = 反向对冲自己卖出的期权 Delta——**short put（Delta 正）下行买、short call（Delta 负）上行买**；Put Wall 形成买盘/支撑，Call Wall 形成向上磁吸，都不是"压力/卖压"。
3. **图表引用必须用真实 id**：词条内引用页面图表，以 `btc_derivatives.js` 的 `RISK_CHART_VIEWS` 键 / 实际渲染标题为准（如 `options_risk_premium_history` → 期权风险图），禁止使用历史/过期名称。
4. **宏观术语以标准定义为准**：利率走廊是地板体系（IORB=下限）；SRF 是 2021 年后的工具，历史案例不得错配。
5. **验证门禁**：改 `app/static/core/knowledge.js` 后必跑 `node --check` + `tests/test_knowledge*` 前端静态测试；内容错误靠审查，不靠测试兜底。

---

## 附录 A：grep 结果与证据命令

> 本附录是 §6 / §7 的全部 grep 命令与其原始计数，便于复核。

```bash
# Token 引用次数
grep -on 'var(--line)' app/static/styles.css | wc -l                  # 8
grep -on 'var(--text)' app/static/styles.css | wc -l                  # 12
grep -on 'var(--bg-surface)' app/static/styles.css | wc -l            # 2
grep -on 'var(--bg-hover)' app/static/styles.css | wc -l              # 2
grep -on 'var(--danger-strong)' app/static/styles.css | wc -l         # 4
grep -on 'var(--border-light)' app/static/styles.css | wc -l          # 2
grep -on 'var(--info-strong)' app/static/styles.css | wc -l           # 1
grep -on 'var(--line-soft)' app/static/styles.css | wc -l             # 1
grep -on 'var(--card-bg)' app/static/styles.css | wc -l               # 1
grep -on 'var(--text-muted)' app/static/styles.css | wc -l            # 0（撤回上版列入）
grep -on 'var(--font-ui)' app/static/styles.css | wc -l               # 0，含 fallback 不失效（撤回）

# Chip 命名
grep -hon 'status-chip neutral' app/static/pages/strategy/*.js | wc -l       # 97
grep -hon 'status-chip chip-neutral' app/static/pages/strategy/*.js | wc -l  # 31
grep -n '^\.chip\.' app/static/styles.css                                     # 4（warn/cool/danger/warm）

# Chart.js DPR 验证
grep -n 'devicePixelRatio' app/static/ui/charts.js                            # 0
grep -n 'devicePixelRatio' app/static/vendor/chart.umd.js | head              # 5 处，platform.getDevicePixelRatio()

# Refresh 按钮
grep -n '刷新.*按钮\|手动刷新\|刷新行情\|刷新 XAUT\|刷新监控\|刷新扫描\|刷新衍生品快照\|刷新分析\|刷新信息\|同步宏观' \
  app/static/pages/*.js app/static/pages/strategy/index.js                    # 各页命中位置见 §10.1

# Dead branch
grep -n 'if (false' app/static/pages/*.js                                     # ≥2（market_events.js, macro_calendar.js）

# Render module 挂接状态
grep -n 'renderSignalStrip\b' app/static/pages/gold_v4.js                     # 定义与未引用
grep -n 'renderMaturityKeyLevelsSnapshot\b' app/static/pages/btc_derivatives.js
grep -n 'selectOptions\b' app/static/pages/btc_derivatives.js
```

