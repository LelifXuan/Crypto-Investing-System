# CHANGELOG

## v1.8.1 (2026-07-27)

### 期限矩阵 wall cell 视觉权重分层

- **前端**：`app/static/styles.css` 新增 `.btc-wall-cell` 基础样式 + `.is-effective` / `.is-insufficient` 两个变体。有效墙（`$60,000` 等）字号 16px / ink 色 / 青绿 border-top / 单点·集群百分比用 accent 色；未形成有效墙字号 13px / muted 色 / dashed border / 整体 opacity 0.86，显著弱化。
- **测试**：`tests/test_btc_maturity_wall_visual_weight.py` 静态守卫 3 个：两类选择器都存在、`<b>` 字号差 ≥ 2px、insufficient 必须有 opacity / dashed / muted 之一。
- **验证**：`tests/test_btc_derivatives_*` 31 passed。

### 关键行权价迁移图叠加标准到期日 marker

- **前端**：`app/static/ui/charts.js` 新增 `expiryAnchors` Chart.js 插件；`key_levels_history` 图表配置注入每个标准到期日（4D / 32D / 60D / 151D / 242D / 333D 等）的 marker：垂直虚线 + 3 个圆点（PUT WALL / MAX PAIN / CALL WALL）。让用户在一张图上同时看到 180D 历史 + 期限矩阵 6 行快照。
- **前端**：`app/static/pages/btc_derivatives.js` 新增 `buildMaturityExpiryAnchors(labels)`，从 `dashboard.options.maturity_ladder` 派生 anchor 列表，按 chart x 轴格式（epoch ms / ISO）自适应转换到期日。
- **后端**：`app/services/btc_derivatives/chart_builder.py` 把 `key_levels_history` 的 `span: 6` 改为 `span: 12`，使其在期权结构段单独占满整行，避免和 `options_risk_premium_history` 挤在同一半。
- **测试**：`tests/test_btc_derivatives_chart_expiry_anchors.py` 静态守卫 3 个：插件存在、`maturity_ladder` 被读、`key_levels_history` 配置使用 overlay。
- **验证**：`tests/test_btc_derivatives_*` 38 passed。

### BTC 衍生品证据大卡片 4×2 统一网格

- **前端**：`app/static/pages/btc_derivatives.js` 把"衍生品状态"4 张子项和"推理"4 张子项合并到同一个 `.btc-evidence-grid`（4 列 × 2 行，`grid-auto-rows: 1fr`），共享 `.btc-evidence-tile` 容器，消除原本两行之间的大段空白。
- **设计**：删除原 `.btc-decision-card` 旧包装；衍生品状态子项现在使用与推理子项完全一致的容器与 chip（kind chip + 置信度 chip + 标题 + 影响），并通过新增的 `judgementTone()` 把 `stateLabel` 映射到 bull/bear/neutral 配色。
- **测试**：`tests/test_btc_evidence_grid_unified.py` 静态守卫 4 个：使用统一网格、衍生品子项使用 `.btc-evidence-tile`、CSS 包含 `grid-auto-rows: 1fr` + `repeat(4`、CSS 定义 `.btc-evidence-tile`。
- **验证**：Playwright 实测 8 张子卡等高 304.3px，证据层高度从 ~1100px 降到 750px（-32%），0 console error / 0 page error。

### 结构图"已确认"chip 方向色

- **前端**：`app/static/pages/structure.js` 新增 `chipToneForDirection()` 工具函数，把系统方向（`bullish` / `weak_bullish` / `bearish` / `weak_bearish` / 其它）映射到现有 `.chip-bullish` / `.chip-bearish` / `.chip-neutral` CSS class。右侧 system 卡片（摆动结构 / 经典图形 / 成交量·市场轮廓）标题区"已确认"chip 改为随方向着色。
- **测试**：`tests/test_structure_status_chip_tone.py` 静态守卫 3 个：函数存在、映射规则正确、system 卡片调用点使用派生 class。
- **验证**：`tests/test_structure*.py` 全量 40 passed。

### 形态结构图表延伸到最新 K 线

- **前端**：`app/static/pages/structure.js` 的 `shouldExtendToLatest` 新增 `pattern_region` 与 `region` 角色；`extendOverlayToLatestCandle` 新增 polygon 右角延伸分支，把经典形态矩形 / 通道 / 三角形 / 楔形的多边形右边缘从形态确认时刻拉到最新 K 线 X。
- **前端**：摆动骨架（zigzag / backbone / live_leg）末端 dot 改为锚定到最新 K 线的 high / low，按"与上一个 dot 距离更近"挑选，使蓝色折线在右侧收束到一个明显的活动 dot，而不是留下一段空白 trendline 外推。
- **测试**：新增 `tests/test_structure_overlay_extension.py`，4 个静态断言：region 必须延伸、swing_zigzag 必须延伸、pattern_path 不能延伸、polygon 右角必须移动到 latestX。
- **验证**：`tests/test_structure*.py` 全量 45 passed；Playwright 后端无快照时无法截屏验证视觉，依赖源码 + 静态测试作为回归门禁。

### BTC 衍生品页证据/保护规划上下两层重设计

- **前端**：把“指标状态与多空证据”与“网格与现货保护规划”从并排改为上下两层（`btc-layout-row--evidence` 与 `btc-layout-row--protection` 各自独占一行），4 张证据子卡改为 `repeat(auto-fit, minmax(220px, 1fr))` + `grid-auto-rows: 1fr` 等高排版。
- **设计**：新增 `.btc-confidence-chip` 三档配色（高/中/低）与 `.btc-tone-chip`（bullish/bearish/neutral）；保护规划表单拆 3 段（标的 / 网格区间 / 风控参数）使用 fieldset + legend；按钮带 SVG 箭头，提示文字置于按钮下方。
- **修复**：删除原 `btc-hedge-result` 容器在无数据时输出的小字溢出（`min-height: 220px` 配合右浮小字）改为上下排版与表单同列。
- **测试**：`tests/test_btc_derivatives_frontend_static.py` 更新 CSS class 引用 `.btc-hedge-grid` → `.btc-hedge-form` / `.btc-hedge-section`。
- **验证**：Playwright 实测 4 张证据子卡等高 221.2px、3 段 fieldset、8 个字段、按钮 + 提示文字、0 console error / 0 page error。

### 市场状态卡冷静专业化

- **前端**：技术指标页 `.status-mode-badge` 重新设计，从大面积琥珀色警告框改为冷白半透明、三段式（`.regime-icon` / `.regime-info` / `.regime-action`）的冷静专业风格。左侧 36px 圆角方形图标使用内嵌 SVG（range: 趋势柱线 / transition: 折线）+ 青绿色调；中部眉题 `市场状态 · RANGE|TRANSITION` + 主结论；右侧圆角幽灵按钮，内嵌 SVG 箭头替代文本字符 `→`，hover 时箭头右移。
- **设计**：删除 emoji 风格不一致（📊 / ⚡），统一 SVG；删除文本下划线和黄色警告色；保留 RANGE / TRANSITION 模式结构，仅通过图标和强调色区分。
- **响应式**：720px 以下允许操作按钮换行到下一行并右对齐。
- **测试**：`tests/test_analysis_mode_badge.py` 新增 `test_mode_badge_markup_has_no_emoji_or_text_arrow` 静态断言，约束新结构。
- **验证**：Playwright 实测 cold-load 0 错误、状态卡 bbox `{w:1368, h:64}`、hover 态箭头右移生效。

## v1.8.0 (2026-07-23)

### 知识百科 chip 压缩

- **前端**：术语卡"出现在 X 个页面"的多 chip 簇改为单行 `i N 页可用 ▾` 触发器 + hover/focus 弹出 popover（每页 + 一句话用途）。`app/static/pages/knowledge.js` 的 `renderPageRefsBadge()` 重写；CSS-only 交互；新增 `KNOWLEDGE_PAGE_NOTE` 映射。`app/static/styles.css` 新增 `.knowledge-page-refs*` 块。
- **测试**：`tests/test_knowledge_catalog.py` 新增 3 个静态断言（compact trigger、无 SPA 链接泄漏、per-page notes）。
- **验证**：`python tests/verify_pages.py` 11/11 cold-load + 10/10 SPA switch 通过，0 console/page errors。

### 版本号统一

- **架构**：以 `app/__version__ = "1.8.0"` 为单一来源；`config.py` / `paths.py` 改为 import 而非硬编码；`pyproject.toml` 作为 packaging release authority，由 `tests/test_version_consistency.py` 钉住与 `app.__version__` 一致。
- **文档**：`.env.example` / `README.md` / `CHANGELOG.md` 全部对齐到 1.8.0。

## v1.7.1 (2026-07-07)

### 黄金配置页 V2 升级

- **多空标签**：核心/派生指标卡右上角标签从"可用/偏低"改为 5 档多空判断（强势看多 / 看多 / 中性 / 看空 / 强势看空）。新增 `_bias_for_indicator()` 后端函数 + 5 档 CSS 类。
- **宏观指标**：新增 4 个核心宏观卡（real_yield_10y / DXY / CPI YoY / VIX）。每个卡显示多空标签 + bias_reason + 数据源。后端新增 `_gold_macro_snapshot()` 函数实现黄金视角的多空判断（含 CPI 二维表 / VIX 流动性冲击例外 / DXY 危机例外）。
- **设计语言**：页面从 4 段并列升级到 9 段递进（Hero 决策 → 4 宏观 → 7 模块 → 图表 → XAUT/黄金坑 → 执行 → 核心/派生指标 → 数据治理）。新增 `.gold-bottom-group` 二级容器（沿用 BTC bottom-group 模式）与 `.gold-decision-card[data-tone]` 4 色状态。

### 后端

- `app/services/gold_dca_dip.py`: `_indicator_card()` 新增 `bias` 字段；新增 `_bias_for_indicator()` 函数
- `app/services/gold_macro_adapter.py`: 新增 `_gold_macro_snapshot()` 函数
- `app/services/gold_allocation_engine.py`: `AllocationPlan` 新增 `macro_payload` 字段；`to_dict()` 暴露 `gold_macro_snapshot`
- `app/schemas/gold_allocation.py`: `GoldAllocationPlanResponse` 新增 `gold_macro_snapshot` 字段

### 前端

- `app/static/pages/gold_allocation.js`: 9 段递进重写（hero / decision / macro / modules / charts / xaut / execution / indicators / governance）；新增 `biasLabel` / `renderMacroStrip` / `renderMacroCard` / `renderDecisionGrid` / `renderModuleSection` / `renderChartSection` / `renderGovernanceSection` / `renderModuleCard` 函数；`loadExecutionPlan` 拉取 `/gold/allocation`
- `app/static/styles.css`: 新增 ~122 行 CSS（7 个多空 chip + 二级容器 + 4 宏观卡 + 流动性冲击警告）

### 测试

- `tests/test_gold_dca_dip_engine.py`: 新增 6 个 `_bias_for_indicator` 测试
- `tests/test_gold_macro_adapter.py`: 新建文件，6 个 `_gold_macro_snapshot` 测试
- `tests/test_gold_allocation_engine.py`: 新增 1 个 `gold_macro_snapshot` 集成测试
- `tests/test_gold_frontend_static.py`: 新增 7 个 V2 DOM 结构断言

### 已知问题 / Follow-up

- 强档阈值在 spec 文本"lower*0.7 / upper*1.3"对 negative lower 存在语义歧义。Implementer 做了语义化解读（lower≥0 时 *0.7，lower<0 时 *1.3，向 strong 方向延伸 30%）。建议未来 spec 修订时明确化。
- 图表区（5 段）目前是占位卡，真实图表实现可在 v1.7.2 实施。
- `_gold_macro_snapshot` 中 `bias_reason` 中文长字符串与流动性冲击阈值 (25/105/2.0) 硬编码在函数体内。可在未来 Task 提取为常量以减少漂移风险。