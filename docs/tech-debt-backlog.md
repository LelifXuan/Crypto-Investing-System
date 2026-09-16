# 技术债清单（Tech Debt Backlog）

维护人：接手开发维护的工程负责人。基线日期：2026-09-04。
本文件是**待办清单**，不记录已偿事项（已偿项见各 commit 与 `docs/ui2-page-migration-acceptance.md` / `docs/ui23-release-hygiene.md`）。
每项标注：来源审计、优先级（P0 阻塞发布 / P1 高 / P2 中 / P3 低）、验证方式。

## 一、业务语义债（高优先级，影响决策正确性）

| # | 债项 | 来源 | 优先级 | 说明与验收 |
|---|---|---|---|---|
| B1 | chip_structure 无数据被编码为 `risk_score=100 / extreme` | `docs/chip-structure-availability-audit.md`（2026-08-31） | **P1** | **已偿（2026-09-16，见下方本轮已偿摘要）**。新增 `availability_state` 枚举 + `availability_reason`，missing/unavailable 分支 `risk_score=null` / `risk_label=null` / `conflict_level=0` / `recommended_action_v2='unavailable'`。FinalDecision `_conflicts` 删 `risk_score_extreme` 假冲突；`_final_action` / `_trade_permission` 新增 `unavailable` 显式态（区别于 `observe`）。前端 chip Tonal 按 `availability_state` 分支渲染：missing 时 chip_risk 显示「数据不可用」chip-neutral 灰（不再叠加「风险极高」chip-bearish 红）。 |
| B2 | `market_context.py` 把 chip 依赖标记为 fresh 而不检查 `chip.state=missing` | 同上 | **P1** | **已偿（与 B1 同 commit）**。`_dependency_meta("chip_structure", ...)` 跟随 `chip.availability_state`：`missing/unavailable` → `cache_state='missing'`、`source_updated_at=None`；`stale_lkg` → `stale`；其余走 fresh。 |
| B3 | ETF 历史数据缺失时后台刷新链路未验证 | `reports/ui-style-20260904`（技术指标刷新压力测试失败记录） | **P2** | worker 禁用的隔离环境无法完成强制刷新 + 最后标的日线为空 → 等待超时。需在启用 worker 的环境验证后台刷新闭环，或给「目标快照为空」提供明确终止语义。前端操作可恢复已用固定样本回放验证。 |

## 二、测试与工程债

| # | 债项 | 来源 | 优先级 | 说明与验收 |
|---|---|---|---|---|
| T1 | 全量 Ruff 存量 ~247-248 项 | 各轮验证报告 | **P2** | 全部位于既有后端/脚本/测试；改动范围必须保持 0。建议按模块分批清偿，每批独立 commit，不与功能改动混合。 |
| T2 | 4 个 skip：筹码结构旧模块 1 / pandas-ta 缺失 1 / TA-Lib 缺失 2 | ui23-release-hygiene | **P3** | pandas-ta/TA-Lib 在 Python 3.14 下不可装；等上游支持或固定 CI Python 版本后解除。筹码结构 skip 等 B1 修复后用新合同重写。 |
| T3 | 测试可移植性：subprocess 文本管道隐式依赖 UTF-8（GBK 环境 reader thread 崩） | ui23-release-hygiene | **P3** | 已用 `PYTHONUTF8=1 + PYTHONIOENCODING=utf-8` 统一环境绕过；根因（测试子进程未显式 encoding）留待清偿。 |
| T4 | ETF 真实缓存回归检查相对 runtime 路径、却从隔离目录读 | ui23-release-hygiene | **P3** | 已通过复制 6 份历史 JSON 绕过；路径分叉登记为可移植性债务。 |
| T5 | 历史硬编码动画时长警告 4 项 | V2.2 CHANGELOG | **P3** | 不阻塞页面交接；清偿时统一走 semanticMotion token。 |

## 三、UI 审计未尽项（P2/P3，2026-09-04 audit 遗留）

| # | 债项 | 优先级 | 说明 |
|---|---|---|---|
| U1 | AI 审计详情直接显示实现标识（`legacy-cross-horizon-v2`、`auditable-rules-v3-shadow`、`gateio:futures.contracts`、微秒 ISO 时间） | **P2** | §1.3 不暴露实现术语。技术 ID 转可理解标签，精确 ID 留在按需审计详情；时间统一 UTC 无微秒格式。**已偿（见下方 2026-09-16 已偿摘要）** |
| U2 | 黄金成交量轴 `128,882,313.00000001` 浮点尾数 | **P2** | §4 数字排版。后端 Decimal 序列化或前端量级格式化（亿/万）二选一。**已偿（见下方 2026-09-16 已偿摘要）** |
| U3 | 监控宏观分组每条约 109.6px 高、完整卡片嵌套在明细卡内 | **P2** | §1 高密度/§7.1 不嵌套。改为紧凑横栏 + 分隔线；同组独立卡则 16px gap。**已偿（见下方 2026-09-16 已偿摘要）** |
| U4 | 触屏命中区：手机按钮多 38-40px（ETF 策略模拟 32px） | **P2** | §10 至少 44×44。coarse pointer 下扩大 hit-box，桌面保持紧凑；以实际 hit-test 证明。**已偿（见下方 2026-09-16 已偿摘要）** |
| U5 | 监控冷启动骨架只覆盖顶部状态块 + 三行，与最终结构不等高（CLS） | **P2** | §7.10 结构稳定。在现有 warming shell 基础上补双列摘要/宏观分组/治理底栏占位。**已偿（见下方 2026-09-16 已偿摘要）** |
| U6 | 事件信息流真实满载态、BTC 衍生品完整行情满载态未在审计中复核 | **P3** | 空态审计过，满载留待有真实数据时复核。 |
| U7 | 手册 §3.1 其余三级文字背景组合的对比度矩阵 | **P3** | tertiary 主 token 已达 4.85:1（P2#9）；剩余小字体/透明背景组合按需逐个测量。 |

## 四、基础设施与流程债

| # | 债项 | 优先级 | 说明 |
|---|---|---|---|
| I1 | SQLite 单写队列仅进程内有效；多进程部署前必须迁移 PostgreSQL | AGENTS.md §9.4 | **P2**（部署前必办） |
| I2 | stash 工作流风险：长命 stash（9/1）被遗漏 4 天，141 项测试失败 | 本轮复盘 | **P1（流程）** | 规则建议：①重要阶段结束当天 pop stash；②stash message 记录所含功能域；③每日开工先 `git stash list` 核对。本轮 5 个历史 stash 已确认 4 个为废弃 WIP（旧分支基线），仅 stash@{0} 为有效增量且已全部合入。清偿建议：确认后 `git stash drop` 逐个清理。 |
| I3 | 验证实例残留：本轮已删 `runtime/ui_audit_verify`(75MB)/`ui_style_verify`(24MB)/`monitoring_cold_verify`(7.5MB) 与根目录 `nul` | 2026-09-04 audit 尾注 | 已完成 |
| I4 | `runtime/techdebt_verify` 精简库（22MB）用后须删（含 -wal/-shm） | 本轮验证 | 验证结束后清理。 |

## 本轮已偿（摘要，防回退）

- **stash@{0} V2.3 接线恢复**：9/1 的工作被 stash 后，9/4 的样式修复在丢失接线的底座上进行，造成 141 项 V2.3 测试失败。已通过「先分域提交 9/4 工作 → 恢复 stash → 三路合并」修复；monitoring 冷启动反馈与 workbench shell 已融合。
- **P1 五项**：AI 策略手机单列（单元格 41→133px）；详情抽屉顶栏避让 + 焦点圈 + 溢出收敛；形态图 SVG 三视口 1:1（轴标签 3.3px→12px）；报价卡 stale 语义（2 天旧缓存标「缓存 · 2 天前」非「实时」）；ETF 缺历史数据待态卡（不再假零）。
- **P2 六项**：下拉白底、监控 52px 叠加间距、tertiary 对比度 4.00→4.85:1、10 个 canvas aria-label、宏日历空态卡、手册三处矛盾。
- **守卫**：新增 10 个静态守卫测试文件共 24 项断言钉住以上修复。

## 建议下一步顺序

1. T1 Ruff 分批清偿（每模块一 commit，约 247 项存量）。
2. I1 PostgreSQL 迁移评估（仅当多进程部署提上日程）。
3. U6 / U7 P3 复核（满载态审计 + 手册对比度矩阵）——留待有真实数据时触发。

## 本轮已偿（2026-09-16,UI 审计 P2 一次性清偿）

- **U1** AI 审计详情脱术语化：`renderDecisionAudit.js` 新增 `humanizeModelVersion` / `humanizePriceSource` 把 `legacy-cross-horizon-v2` / `auditable-rules-v3-shadow` / `gateio:futures.contracts` 等映射为人类可读标签；`dom.js::formatDateTime` 入口加微秒正则拍平；`renderEventWatch.js` 旁路改走统一 `formatDateTime`。
- **U2** 黄金成交量轴整数格式化：`charts.js::buildAdaptiveAxisOptions` 给 volume profile 加 `ticks.value_format = "integer"`，沿用 `formatChartValue` 现有 integer 分支，避免 `128,882,313.00000001` 类尾数。
- **U3+U5** 监控冷启动骨架补占位：`monitoring.js::renderShellFallback` 在 pending=true 时给 `#monitoring-macro-panel` / `#monitoring-macro-grid` / `#monitoring-governance` / `monitoring-topbar-grid` 注入 `monitoring-cold-placeholder`；`styles.css` 合并重复 `.macro-indicator-group` 声明并把 `gap` 从 14px 改为 16px（同组独立卡要求），消除冷启动期 109.6px 高度坍塌。
- **U4** ETF 触屏命中区：`editorial.css` 现有 `@media (pointer: coarse)` 块扩 ETF selector（`.etf-equity-mode-btn` / `.etf-equity-freq-btn` / `#etf-equity-generate` / `.etf-equity-from input` / `.etf-equity-offset input` → 44×44 + padding-block 8px）；`styles.css` 给 `.primary-action` 加默认 40px / 8px 16px 规则（避免原生 button 形态塌陷）；桌面 `.etf-equity-mode-btn` padding 从 6×14 调到 8×16。
- **守卫**：新增 `tests/test_ui_audit_p2_unreleased_fixes.py` 共 14 项静态断言钉住以上修复。

## 仍遗留（U6-U7，P3）

| 债项 | 优先级 | 说明 |
|---|---|---|
| U6 | **P3** | 事件信息流真实满载态、BTC 衍生品完整行情满载态未在审计中复核。空态审计过，满载留待有真实数据时复核。 |
| U7 | **P3** | 手册 §3.1 其余三级文字背景组合的对比度矩阵。tertiary 主 token 已达 4.85:1（P2#9）；剩余小字体/透明背景组合按需逐个测量。 |

## 本轮已偿（2026-09-16,B1+B2 chip_structure availability 业务语义）

- **后端 schema + service**：`ChipStructureRead` 新增 `availability_state` 枚举（`ready | low_confidence | missing | unavailable | stale_lkg`）和 `availability_reason`；`risk_score` / `risk_label` 改 `Optional`（可空），默认不再是 `100/extreme`。`chip_structure.py` 三分支（real_structure / candles≥20 / missing）都显式设 `availability_state`；missing 分支输出 `risk_score=None` / `conflict_level=0` / `recommended_action_v2='unavailable'`。
- **FinalDecision 权限优先级**：`_conflicts` 删除 `risk_score >= 80 → risk_score_extreme` 假冲突分支（历史根因：missing 同时输出 100 → 假冲突）。`_final_action` / `_trade_permission` 新增 `unavailable` 显式态，缺数据时 `trade_permission='unavailable'`（不再误为 `observe`），且权限先于 conflicts 短路。
- **market_context freshness**：`_dependency_meta("chip_structure", ...)` 按 `chip.availability_state` 决定 `cache_state`：`missing/unavailable → missing + source_updated_at=None`，`stale_lkg → stale`，其余 fresh。修复了「缺失数据被标记为 fresh 的假新鲜度」污染 strategy_unified 元数据的链路。
- **前端 chip Tonal**：`alerts.js` `chipStateMarkup` 新增 `unavailable` / `stale_lkg` 枚举映射；`chipRiskMarkup` 增加 `chipAvailabilityGuards(availability)` 守卫，`availability_state in {missing, unavailable, stale_lkg}` 时直接渲染「数据不可用」`chip-neutral` 灰色 chip（不再叠 `chip-bearish` 红色）；`renderChipStructureCard` 风险分数值守卫时显示「—」。
- **守卫**：新增 `tests/test_chip_structure_availability.py` 6 fixture（missing 直返、missing 经 FinalDecision、stale_lkg、low_confidence 保留真实 risk_score、`_conflicts` 不再触发 risk_score_extreme、analyzer 异常 → unavailable）；新增 `tests/test_chip_availability_static.py` 7 项静态守卫（schema availability_state 字段、risk_score Optional、chipRiskMarkup availability 守卫、chipStateMarkup unavailable/stale_lkg 枚举、_conflicts 不含 risk_score_extreme append、market_context 按 availability 分支、_missing_payload availability_state='missing'）；旧 `test_market_context_builder.py::test_market_context_cache_meta_tracks_source_pages_and_freshness` 的 `fake_analyze` 补 `availability_state='ready'`，接受新契约（旧契约假设 chip_structure 永远 fresh，本身就是审计指出的 bug）。
- **验证门禁**：全量 pytest 2078 passed / 3 skipped（排除旧 skip-everything 模块）；改动范围 Ruff 0；verify_pages 11/11 + 10/10；真实 API 烟测 `instrument_id=BTCUSDT&timeframe=1h` 返回 `action='unavailable'` + `trade_permission='unavailable'` + `risk_score=None` + `conflicts=[]`（修复前 `no_trade / observe / 100/extreme / [risk_score_extreme]`）。
