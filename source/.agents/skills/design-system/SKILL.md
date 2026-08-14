---
name: design-system
description: >-
  本仓库的视觉设计系统规范：Editorial Research Terminal 浅色全画布主题 + 语义色矩阵 + 组件约定。
  任何涉及前端视觉改动的任务都必须加载本 skill——改颜色/字体/间距/圆角/阴影、新增或修改组件
  （卡片/按钮/表格/状态chip/下拉/抽屉/图表）、页面布局调整、以及任何前端视觉验证，即使任务
  没有明确提到"设计系统"。本 skill 提供设计决策的边界（什么可以做、什么禁止），并指向验证门禁。
---

# 设计系统规范（Editorial Research Terminal）

本仓库前端是 **vanilla JS + 原生 CSS**（无框架）。所有视觉决策必须遵循本规范。
核心设计语言：**浅色编辑刊物式研究终端 + 低饱和深紫品牌色 + 蓝色信息辅助色**。

## 一、不可违背的设计原则

1. **全画布编辑式终端是方向，不得退回居中卡片墙或深色终端风**。
   - 桌面由 `216px` 侧栏与弹性主画布组成；证据和风险优先放在页面业务上下文内。
   - 普通信息靠留白与分隔线组织；只有重点摘要、抽屉、菜单和弹层使用 elevation。
   - 页面背景不使用装饰光晕、纸张网格或普遍玻璃模糊。
2. **语义色矩阵是硬约束**。见 `references/tokens.md` §语义色矩阵。任何颜色使用必须匹配语义，
   禁止用视觉近似替代语义（如用 Bullish 色表示"数据实时"、用 Warning 色表示"看跌"）。
3. **数字必须 tabular-nums**。金额/数量/比率等数字列用 `font-variant-numeric: tabular-nums`，
   保证纵向对齐。大数字用轻字重（600 以下），不默认 bold。
4. **禁止 emoji 作为系统/状态/控件符号**。状态和方向一律用内嵌 SVG 图标 + 文字冗余
   （色觉安全：颜色永不单独传达信息，必须配文字/图标）。
5. **禁止原生 `<select>`**。全站下拉统一用 `app/static/ui/dropdown.js` 的 `mountDropdown` 组件，
   禁止在模板/JS 中出现 `<select` 字面量。
6. **版面宽度按内容职责选择**。图表、表格和工作台使用剩余宽度；长正文限制在 `760–820px`。
7. **改动必须小而清晰**。每次按 Shell、页面类型或组件域拆分，并跑对应验证。

## 二、触发场景（符合任一即加载本 skill）

- 改 `app/static/styles.css` 或 `styles-v15.css` 的任何规则
- 新增/修改组件（卡片、按钮、状态 chip、表格、下拉、抽屉、图表配色）
- 改页面布局、间距、圆角、阴影、动效
- 跑视觉验证门禁（css_audit / a11y_scan / visual_diff / responsive / perf / motion / verify_pages）
- 用户提到"UI 提升 / 设计 / 视觉 / 样式 / 好看 / 对齐 / 风格"

## 三、token 与组件

- **完整 token 表**（准确的 CSS 变量名与值）→ 读 `references/tokens.md`。
- **组件清单与用法**（.btn / .metric / .status-chip / .card / 表格 / dropdown / 抽屉）→ 读 `references/components.md`。
- **动画设计与配方**（页面切换 / 数字滚动 / stagger / 图表刷新 / 滚动复位）→ 读 `references/animation.md`。
- 改 token 前先查 token 表：能复用 `--` 变量就不要写死颜色/尺寸。

## 四、参考站提取结论

| 参考站 | 借鉴什么 | 不借鉴 |
|---|---|---|
| Mercury | 版式：h 负字距、表格密度、大数字轻字重 + tabular-nums | 深色底、全站 pill 导航 |
| shadcn/ui | 排版层级：h1 48px/600/-2.4px、组件圆角 8px 基线 | 深色 oklch 变量 |
| iA.net | 大正文行距 1.65、内容 max-width 768px 可读性、负字距大标题 | 近黑底 `#070707` |
| Emil Kowalski | 动效曲线：`--ease-drawer: cubic-bezier(0.32,0.72,0,1)`（已采纳） | — |

> 详见 `references/reference-sites.md`（含完整 computed token 对比表）。

## 五、验证工作流（强制，遵循 AGENTS.md §六）

任何视觉改动完成后**必须**跑：

1. **静态门禁**（改动 CSS 时必跑）：
   ```
   python tests/css_audit.py              # 增量门禁：只对新增死类 FAIL（首次跑先 --rebase 建基线）
   python tests/motion_verify.py          # 动效 token 阶梯
   ```
2. **前端静态测试**（pytest，非浏览器）：
   ```
   python -m pytest tests/test_ashare_etf_frontend_static.py tests/test_spa_router_navigation.py -q
   ```
3. **实例检查**（改了 main.js / core/*.js / 模板 / 架构 → 全 9 页；只改单个 pages/*.js → 只跑该页）：
   ```
   python tests/verify_pages.py --pages <受影响页面>
   # 涉及共享依赖必须全量：
   python tests/verify_pages.py
   ```
4. **浏览器实测截图**（视觉改动必须）：用 control-browser 打开受影响页面，
   **`fullPage: true` 全页截图**存档到 `tests/screenshots/`，并检查 `pageerror` = 0。
   注意：**非多模态模型读不了截图**——模型负责结构/几何/computed style 验证，
   最终观感由用户或 vision 模型拍板。
   **禁止只截视口顶部** — 必须截取整个页面（图表 canvas、策略面板、底部区域），
   有抽拉/折叠/抽屉的页面必须先展开再截图。详见证系统 `references/verification.md` §3.2。

> 视觉回归/无障碍/响应式/性能门禁（`tests/a11y_scan.py`、`tests/a11y_visual_diff.py`、
> `tests/responsive_check.py`、`tests/perf_gate.py`）→ 读 `references/verification.md`。

## 六、视口规范

**主开发视口为 2560×1440（16:9）。** 同时必须覆盖 `375×667`、`768×1024`、`1280×800`、`1440×900`：

- **verify_pages.py** 默认 `--viewport 2560x1440`（已从 1366x900 升级）
- **a11y_scan.py / a11y_visual_diff.py / perf_gate.py** — 内部硬编码 `2560×1440`
- **responsive_check.py** — 保留 5 档响应式测试（mobile-s/tablet/laptop/desktop/desktop-2k），
  其中 `desktop-2k = 2560×1440` 是主开发视口
- **control-browser 实测截图** — `setViewportSize({ width: 2560, height: 1440 })` 后截图

响应式断点：`>=1280` 侧栏常驻；`768–1279` 侧栏抽屉；`<768` 单列且核心结论优先。

## 七、多模态处理提示（2026-08-11 决定）

用户会接入多模态 LLM 做具体视觉处理。本 skill 的作用是提供**准确的 token 事实 +
验证门禁 + 设计边界**，让多模态模型拿到后能直接动手：
- 改色 → 改 `:root` 变量，不要散落硬编码色。
- 大改动 → 先在浏览器截图存档 before，改完截 after，让用户/vision 模型对比。
- 每轮改动保持可逆、独立 commit（AGENTS.md §七：`[frontend]` 前缀）。
