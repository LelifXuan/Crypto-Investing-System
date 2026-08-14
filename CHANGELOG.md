# CHANGELOG

## Unreleased (2026-07-30)

### 全站自定义 Dropdown 统一

- **前端**: 新建 `app/static/ui/dropdown.js`,导出 `mountDropdown(root, options) -> { setValue, destroy, refresh }`,替换全站 6 个页面 21 处原生 `<select>`(analysis × 2、structure × 5、knowledge × 4、btc-derivatives × 8、ashare-etf × 1、market-events × 1)
- **设计**: 控件主体 40px / 圆角 12 / 冷白半透明;弹层 item 44px;Click 展开 + Click 选中(零误触);固定 280px max-height + 8px fade-out;视觉态用现有 token,内嵌 SVG icon,不引入新颜色,不引入 backdrop-filter
- **键盘**: Tab 焦点(3px 青绿 focus-ring)/ Enter|Space|↓ 展开 / ↑↓ Home End 移动焦点 / Enter 选中 / Esc 关闭 / Type-ahead 输入字母跳转(前缀优先,短 buffer 退化为 substring 匹配,适配中英混合 label)
- **a11y**: ARIA listbox / role=option / aria-selected / aria-haspopup / aria-expanded / aria-controls
- **样式**: 新增 `.dropdown-*` 命名空间;沿用现有 :root token,不引入新颜色;不放 backdrop-filter;z-index 1000
- **btc-derivatives 表单兼容**: chart toolbar + hedge form 各放 hidden `<input type="hidden" name="...">`,dropdown onChange 写入 hidden,FormData 读取不变(避免改动现有 form submit 流程)
- **测试**: 新增 `tests/test_dropdown_component.py`(CSS 契约 5 项 + size 变体 + 颜色 token 约束) + `tests/test_no_native_select_remaining.py`(页面 JS 静态守卫 12 项);Playwright 烟雾测试 3 个文件,覆盖 cold-load + 键盘交互 + Esc 关闭 + Type-ahead
- **验证**: 19 个测试全部 PASS(改动范围 0 fail);Playwright 全 6 页 cold + 1 个交互用例,0 console error / 0 page error;`node --check` 7 个 JS 文件全部通过

## Unreleased (2026-07-29)

### SQLite 冷启动并发与页面超时治理（2026-07-30）

- SQLite 写路径统一进入支持优先级、FIFO、取消安全与同任务重入的单写协调器；锁覆盖写入、flush、commit/rollback 完整事务，PostgreSQL 自动旁路。
- candle upsert 在 SQLite 下按 400 行短事务分批提交，批间释放 writer slot，允许交互刷新优先插队；复合幂等键保证失败后可安全重试。
- precompute 在 SQLite 下强制单并发，启动预热按 BTC、ETH、HYPE、BNB、OKB 串行入队并等待完成；周期扫描增加启动宽限、积压退让及近过期过滤。
- Workbench 六周期依赖在 SQLite 下串行读取，PostgreSQL 保持并发 3；纯读 session 退出时 rollback/close，readiness 使用 1 秒内部 deadline。
- `stale_revalidating` 且存在 last-known-good 时立即渲染旧快照并后台刷新；只有 `queued/running` 冷启动壳同步展示进度，避免页面等待刷新任务超时。
- 健康检查新增兼容性的 SQLite writer 队列诊断；业务 API 契约、旧 Workbench/缓存接口和独立 `refresh_jobs.sqlite3` 保持不变。
- 验证：`1363 passed, 7 skipped`；Playwright 11/11 冷启动、10/10 SPA 切换通过；改动范围 Ruff、Python 编译及改动 JS 语法检查通过。

### AI 策略 Workbench 冷启动闭环

- `StrategyWorkbenchRead` 升级至 `3.0.0`，新增 `build_state`、`system_availability`、`last_known_good`、`progress` 与 `source_manifest_hash`。构建中不再伪造方向、市场风险或 `0.00` 价格。
- 冷缓存 `GET /api/v1/strategy/workbench` 现在直接创建带 instrument dedupe key 的 targeted refresh job；相同资产并发请求复用同一任务。
- 新增 `StrategyWorkbenchBuildCoordinator`：检查六周期依赖、使用独立 session 与并发上限 3、合成 canonical decision、应用供给门禁并原子发布 Workbench。
- 过期缓存保留完整 last-known-good，返回 `stale_revalidating` 并收紧新增仓位权限；不再用空 `DATA_BLOCKED` 内容覆盖旧分析。
- `RefreshReceipt` 增加 phase、进度、message 与 error code；前端共享 `waitForRefreshJob()` 会自动轮询、成功后 bypass 客户端缓存重读，面板关闭时通过 AbortController 中断。
- 策略统一加载器改为只读领域快照；缺少依赖时返回 dependency gap，不再在请求合成阶段同步执行六次 uncached rebuild。

### HYPE 供给事件与解锁风险

- 新增通用 `supply_events` 模块，包含 contracts、Tokenomist/Hyperliquid providers、reconciler、snapshot builder、risk engine 与 history study。
- 供给状态固定为 `SCHEDULED / COMMITTED / CLAIMED / UNSTAKING / SELLABLE / ABSORBED / EXPIRED`，计划量、承诺量、实际领取、解质押、可售量和已吸收量分别记录。
- 只有可售供给、交易所或做市商流入、主动卖压、衍生品多头拥挤及结构破位同时成立，供给证据才允许贡献 `BEARISH`；计划或单纯领取保持 `NEUTRAL`。
- 供给门禁只允许收紧仓位、杠杆及交易权限，不能放宽 canonical decision，也不能仅凭计划解锁生成做空方向。
- 新增 `/api/v1/supply-events/snapshot`、`calendar`、`history-study` 与 `refresh`。缺少 Tokenomist/Nansen Key 或 verified 地址时返回明确 `source_unavailable`，不生成模拟事实。
- 历史研究按事件锚点输出 T-7 至 T+30 的描述性窗口；样本不足时固定为 `insufficient_sample`，不输出概率。

### 数据模型、SQLite 与前端

- Migration `0013_hype_supply_events` 新增 append-only domain snapshot、供给事件快照及未来日历节点；金额和数量使用 Numeric/Decimal，时间统一 UTC。
- 新增进程内单写协调器。page cache、领域快照、策略审计和黄金 OI 的写锁覆盖完整 commit/rollback 边界，避免“锁只包 flush、commit 已出锁”的伪串行。
- AI 详情页在执行计划后增加“供给事件与解锁风险”卡；市场作战图增加 `supply_event_regime` 第六维。
- Crypto 市场事件页增加未来供给日历、节点类型筛选和明确空态。
- 策略 SPA 冷启动使用可识别的 warming shell，避免通用 loading class 让页面实例检查误判为未完成。

### 验证

- Alembic 隔离升级和运行库版本均为 `0013_hype_supply_events`。
- 全量 pytest：`1349 passed, 7 skipped`。
- 完整 Playwright：11/11 冷启动、10/10 SPA 切换通过，HTTP、console error 与 pageerror 均为 0。
- Hyperliquid direct/proxy 均返回 200；Tokenomist 无 Key 时 direct/proxy 均明确返回 401。
- 最新验证日志中 `database is locked=0`、`PendingRollback=0`。
- 参考审计脚本结果：0 个 P0、0 个 P1。

### 已知限制

- 当前未配置 Tokenomist/Nansen 凭据，也没有 verified HYPE 地址，因此生产结果使用真实适配器的明确降级路径；不会猜测地址或伪造解锁事实。
- 当前供给事件历史样本不足，不自动晋级研究阈值。
- 仓库全量 Ruff 仍有历史遗留问题；本次改动范围 Ruff 已全部通过。

## v1.8.1 (2026-07-28)

### 通道多边形左边缘扩展到历史 pivot

- **后端**：`app/services/structure/classic.py` 的 `detect_channels` 改为贪心扩展历史 pivot 窗口：在已有 4 个最新 pivot 的拟合基础上，向左逐一加入更老的 pivot 并重做线性回归，只要上下边界的 mean error 都仍在 `tol * 2.0` 之内就保留。`left_idx = min(hs[0].index, ls[0].index)` 现在反映真实通道起点，而不是固定截断到第 4 根 pivot。
- **测试**：`tests/test_classic_pattern_detection.py::test_channel_polygon_left_edge_includes_older_pivots_in_tolerance` 用 10 根 pivot 的水平通道验证 `region.points[0].index ≤ 12`，而旧逻辑会落在 56 附近。
- **验证**：`tests/test_classic_pattern_detection.py` 9 passed、`tests/test_structure*.py` 27 passed。

### 保护规划表单现价输入 step='any'

- **前端**：`app/static/pages/btc_derivatives.js` 在 `<input name="spot_price">` 上增加 `step="any"`。`hedge_context.spot_price` 是浮点数（如 65226.17），HTML5 `<input type="number">` 默认 step=1 会触发"请输入有效值。两个最接近的有效值分别为 N 和 M"原生校验提示，让用户误以为系统导入的现价是错误的。
- **测试**：`tests/test_btc_hedge_form_input_step.py` 静态守卫：`name="spot_price"` 输入必须包含 `step="any"`。
- **验证**：`tests/test_btc_derivatives_*` 29 passed。

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
