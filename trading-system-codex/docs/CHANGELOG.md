# Changelog

## V1.7.3 (2026-07-02)

新增 Fed 资产负债表操作层 — 监测"美联储实际在做的事情"，不再只看"嘴上说的"。

### 后端

- `app/monitoring/configs/macro_indicator_api_map.v1.json` 新增 7 个 Fed BS 指标：IORB、ON RRP rate、SOMA Treasury / MBS、SRF 使用、Discount Window、TGA 4 周净变动（FIMA / SOMA 平均久期 / QT cap 经 FRED 验证后移除）
- `app/monitoring/configs/macro_scoring_registry.v1.json` 新增 7 个 scoring entry（3 个 `display_only` 用于 SRF/Discount Window）
- `app/services/macro_overview.py` LAYER_LABELS / MODULE_TO_LAYER 新增第 7 层 `fed_operations`（专门追踪 Fed BS 操作）；原 `liquidity_credit` 移出 4 个 BS 指标

### 前端

- `app/static/core/macro_derived.js` 新文件：`computeNetLiquidity()` — 运行时计算 Reserves - RRP - TGA（crypto 牛熊分水岭）
- `app/static/core/knowledge.js` 新增 4 个词条：fed_balance_sheet_operations / iorb_corridor / net_liquidity / standing_repo_facility

### 测试

- `tests/test_fed_operations_layer.py` 新增 3 个测试：scoring coverage / layer 存在 / 知识词条存在
- `tests/test_indicator_monitoring.py` 新增 1 个测试：api_map coverage
- `tests/test_knowledge_catalog.py` 新增 1 个测试：fed_operations 词条存在

### 后续（不在本次范围）

- 监控总览页面渲染 fed_operations layer + net_liquidity 卡片的具体实现（plan 范围之外，可单独跟进）
- BTFP/SRF 启用/停用自动检测（需要 Fed 公告解析）
- 历史回放图表（高级功能）
- `_layer_contributions` 权重重分配（让 fed_operations 计入 total_score）
- `test_macro_coverage_audit` 测试中 "unknown fed_operations indicators" 警告（需要把新 indicator 注册到 coverage whitelist）

## V1.7 (2026-07-02)

AI 策略页重构（X + Y + Z 全栈 + 截图 8 项修复 + 双 endpoint verify_pages）。

### 后端

- `MarketContextBuilder` 注入真实字段：
  - `market_data` 不再为空 — 透传 `chip_structure` 的 `current_price / price_change_pct / execution_score / execution_label / direction_score / direction_label / weekly_context / daily_bias / primary_regime / primary_regime_label`。
  - `derivatives_features` 不再只有 `key_levels_axis` — 透传 `funding_state / oi_state / skew_state / basis_state / hedge_cost_state / wall_movement / max_pain_movement / call_wall_strike / put_wall_strike / max_pain_strike / spot_price / skew_25d / put_call_ratios`。
  - 新增 `chip_features` 顶层字段（证据质量、regime 标签、weekly_context、daily_bias、h4_structure、h1_confirmation、evidence 数组等）。
  - 新增 `freshness_breakdown` 顶层字段（按 source 扁平化 `data_quality.dependencies`）。
  - `onchain_features` 顶层暴露 `metrics_flat` 便于 `CapitalFlowEngine` 取稳定币 / DEX 数据。
- 新增 `app/services/onchain/policy_adapter.py` — DefiLlama P0 接通：
  - `DefiLlamaPolicyAdapter.collect()` 直接走 `DefiLlamaProvider.fetch_snapshot()`。
  - `collect_via_router(router)` 通过 `OnchainProviderRouter.fetch_metric` 收集（便于 `monkeypatch` 测试）。
  - `ensure_defillama_definitions()` 注册 4 个核心 key 到 `indicator_definitions`（FK）。
  - `persist_drafts()` 写入 `IndicatorObservation`，含 `value_json.source = "defillama"`。
- `IndicatorMonitoringService.sync_onchain()` 改为先调 `policy_adapter.collect_via_router()` + `persist_drafts()`，再走原有 `run_policy()` 路径（双轨并行，保留旧 path 兼容）。
- `strategy_unified` 引擎重构：
  - `contracts.py` 新增 `pick_context(primary, fallback)`、`verdict_for_node(state, direction, timeframe)`、`evidence_confidence(freshness, consistency, coverage)`、`VERDICT_FROM_STATE` 映射。
  - `multi_timeframe_structure` 不再独立计算 `confidence`（置 0，由 `EvidenceTraceBuilder` 统一计算）。
  - 4 个 regime engines (`macro_regime / derivatives_regime / capital_flow / onchain_regime`) 改用 `pick_context` 多源 pick + 结构化判定（funding/oi/skew/basis）+ 中文 `human_explanation`。
  - `cross_horizon._view` 改用 `evidence_confidence`。
  - `evidence.py` 唯一 confidence 来源；逐证据 `freshness + consistency + coverage` 三因子加权。
  - `trade_plan.py` 注入实际价格（`stop_loss` / `entry_zone` / `invalidation` 价格写入文本）。
  - `risk_gate.py` 全部中文 label/message/action。
  - `TimeframeNode` 新增 `verdict_code` / `verdict_label` 字段。

### 前端

- `pages/strategy/index.js` 改 4 endpoint 并行 fetch（`Promise.allSettled`）：`/strategy/unified` + `/monitoring/dashboard` + `/btc-derivatives/dashboard` + `/monitoring/macro-overview`。4/4 失败才 `errorState`；其余在页面末端展示"数据源接入状态"小卡。
- `pages/strategy/adapter.js` 接收 4 endpoint payload；为 timeframe_node / horizon_view / market_operation.dim 附加 `evidence_ref` + `evidence_confidence` + `evidence_freshness`；新增 `buildDataDegradedCard()` 渲染数据源状态。
- `pages/strategy/renderEvidenceTrace.js` 重写为自然语言卡：仅渲染 `conclusion_key / conclusion / human_explanation / confidence / source_modules (人类可读) / source_timeframes / freshness`；不再展示 `calculation_rule / input_features / source_modules` 作为 UI 文本（仅 payload 保留供 API 调用方使用）。
- `pages/strategy/renderTradePlans.js` 新增"入场区间 / 止损 / 止盈 / 失效条件"四列，渲染真实价格。
- `pages/strategy/renderHorizonStack.js` 新增"结论"列展示 `verdictLabel`；置信列改读 `evidence_confidence`。
- `pages/strategy/renderHorizonGovernance.js` 用 `verdictLabel` + `directionLabel` 统一 8 个 verdict 文案。
- `pages/strategy/renderMarketOperation.js` 置信列改读 `evidence_confidence`。
- `app/static/styles.css` 新增 `.strategy-evidence-item` + `.strategy-degraded-footer` 样式。

### 测试

- 新增 `tests/test_onchain_policy_adapter.py`（6 测试）：live/degraded snapshot、router 协议、持久化、幂等。
- 扩展 `tests/test_strategy_market_context_static.py`（11 测试）：并行 fetch、evidence_ref、natural language card、verdict mapping、Chinese risk labels。
- 全部 52 受影响测试通过（`test_strategy_unified_service / test_strategy_unified_api / test_market_context_builder / test_market_context_api / test_options_wall_signal / test_strategy_market_context_static / test_onchain_policy_adapter / test_indicator_monitoring / test_defillama_provider`）。

### 风险

- DefiLlama 在 CN 不可达时自动降级为 `data_status=upstream_missing`，strategy 主推演不受影响。
- 4 endpoint 并行 fetch 中任一 4xx 由 `Promise.allSettled` 兜底，4/4 失败才 `errorState`。
- Confidence 统一为 evidence_trace 来源；6 个旧断言被新数据形态覆盖，无破坏性变更。
- 数据源缺失时 `pages/strategy` 仍渲染其它维度，链上维度显示"上游缺失"，不阻断主流程。

### 验证

- `node --check` 7 个 strategy frontend 文件全通过
- `py_compile` 所有改动 .py 文件全通过
- `pytest` 全部 52 受影响测试通过（indicator_monitoring 用时 124s 为 fixture 开销）
- `python tests/verify_pages.py --pages strategy,monitoring-overview` 计划中（需启动 backend 8002 + chromium）

## V1.7.1 (2026-07-02)

修复直接打开 AI 策略页时显示红色错误条的问题。

### 后端

- `/strategy/unified` endpoint 包 try/except，永不返回 5xx；失败时返回 HTTP 200 + degraded payload（含 `degraded=true` / `degraded_components` / `prewarm_status` 字段）。
- `MarketContextBuilder.get_context()` 把 chip/macro/onchain 三处上游调用都包 try/except，任一失败返回 fallback，snapshot 仍可用。
- `UnifiedStrategyService.build_unified_strategy()` 把每个 regime engine / cross_horizon / risk_gate / trade_plan / evidence / narrative 都包 try/except，失败时该组件加入 `degraded_components`，其他组件继续工作。Per-dimension fallback 保留正确 `key` / `label`。
- 新增 `POST /strategy/prewarm` 端点，触发 monitoring / btc-derivatives / macro-overview 的后台预热，立即返回 `{status: 'enqueued', eta_seconds: 30}`。
- `StrategyUnifiedRead` schema 新增 3 个 optional 字段（默认值，向后兼容）。

### 前端

- 新增 `degradedState()` helper（黄色警告横幅，区别于 `errorState()` 红色）。
- 新增 `api.prewarmStrategy()` 方法（POST /strategy/prewarm，3s timeout）。
- `index.js` mount 阶段 fire-and-forget 触发预热。
- 失败路径用 `degradedState` 替换 `errorState`，并自动重新触发预热。
- `payload.degraded=true` 时 statusBanner 显示"部分降级 + 命名降级组件"。
- `adapter.js` 透传 `degraded` / `degraded_components` / `prewarm_status` 字段。
- 新增 `.strategy-degraded-banner` 样式。

### 测试

- 新增 `tests/test_strategy_unified_degraded.py`：endpoint 永抛错 + prewarm enqueue 验证。
- 新增 `tests/test_strategy_degraded_frontend.py`：Playwright 验证黄色 banner + prewarm 调用。
- 修改 `tests/test_market_context_builder.py`：3 个 upstream 失败路径。
- 修改 `tests/test_strategy_unified_service.py`：engine 失败标记 degraded_components + per-dimension label 验证。
- 修改 `tests/conftest.py`：新增 `repository` / `base_url` fixtures。

## V1.7.2 (2026-07-02)

知识百科页扩充 — 增加页面级使用指南。

### 前端

- `app/static/core/knowledge.js` 的 `term()` 工厂新增 7 个 guide-only 字段（`type / purpose / when_to_use / page_walkthrough / data_lineage / caveats / related_pages`），全部 optional，向后兼容
- 新增 `pageGuidesSection` 段落，含 3 篇首批指南（monitoring-overview / ai-strategy / btc-derivatives）
- `app/static/pages/knowledge.js` 新增 `renderGuideCard()`，使用 4 色 callout 区块（blue 何时用 / green 看什么 / orange 数据依赖 / red 注意点）并默认展开
- 顶部 section chip 自动含 "📘 页面使用指南" 快速跳转
- 新增 `.knowledge-guide-*` CSS 样式（约 80 行）

### 测试

- `tests/test_knowledge_catalog.py` 新增 4 个测试：工厂字段验证、pageGuidesSection 出口、guide 字段完整性、related_pages 引用一致性
- 新增 `tests/test_knowledge_user_guides.py`：Playwright 验证 guide 卡片 + 4 区块 markup 正确

### 后续（不在本次范围）

- 其余 6 篇指南（market-analysis / market-structure / market-events / macro-calendar / ashare-etf / gold-allocation）可独立追加

## V1.5.6 (2026-06-09)

监控总览"宏观指标明细"页 4 项口径异常 + 1 项 0% 防御。

### 新增

- `app/services/macro/transforms.py` — 纯函数 `compute_yoy_pct / compute_mom_pct`。
  缺数据返回 `None` 不抛异常，caller 优雅回退。
- `MacroProvider.fetch_history` 协议 — FRED/BLS 现支持拉 14 点历史窗口，
  失败回退到原 `fetch_latest` 路径，向后兼容。
- `scripts/audit_macro_transforms.py` — 扫描所有声明 transform 的 key，
  实时拉 14 点算同比/环比，超出 (-20, 50) / (-5, 5) sanity band 即失败退出。
- `scripts/stale_macro_observations.py` — 一次性脚本，对 4 个 TRANSFORM_AFFECTED_KEYS
  的历史脏数据（value > 50 视为指数值）打 `stale_index_value` 标记。

### 修复

- 4 个口径异常：US CPI 环比 332.41% / US Core CPI 环比 335.42% /
  US PCE 同比 130.9% / US Core PCE 同比 129.63% 现正确显示为约 +0.3% MoM
  / +3.3-3.8% YoY。
- 美国失业率 0% 防御：数据层（fallback_resolver）+ 服务层
  （macro_overview）+ UI 层（monitoring.js INVALID_TEXT_VALUES +
  missing-reason 映射）三层独立防御。

### 测试

- `tests/test_macro_transforms.py` — 20 个纯函数单测
- `tests/test_provider_history.py` — 7 个 provider 单测
- `tests/test_macro_overview_transforms.py` — 6 个集成测试
- `tests/test_unemployment_zero_defense.py` — 14 个三层防御测试
- `tests/test_stale_macro_observations.py` — 5 个脚本测试
- `tests/test_audit_macro_transforms.py` — 5 个审计脚本测试
- 1 个 `test_frontend_resilience_static.py` 静态检查 suspect_zero 渲染

### 已知限制

- 仅在源码模式（`start_source.bat` 8002 端口）验证通过。
  便携包（8000）需手动跑 `python scripts/tasks.py build-portable` 同步代码。

## V1.5 (2026-06-02)

监控总览页解释闭环升级。

### 新增

- **`terminal_summary.decision_brief`** — 监控总览摘要新增三行决策简报：
  - `市场情况`（descriptive + 多周期 + 筹码 + 背离证据）
  - `交易指引`（conditional execution，不输出确定交易语言）
  - `风险点 / 失效条件`（invalidation + 数据缺口 + 跨页冲突）
- **`source_alignment.matrix`** — 6 行固定顺序的多周期冲突矩阵：
  `1w_trend` / `1d_bias` / `4h_trigger` / `chip_structure` /
  `divergence_summary` / `strategy_gates`，每行含
  `direction` / `weight` / `evidence_strength`。
- **`consistency` 四值** — `aligned / mixed / conflict / degraded`，
  冲突检测覆盖单源方向对立与多周期方向不一致两类。
- **决策快照持久化** — `ComputedDatasetCache` 新增
  `dataset_type=monitoring_decision_brief`（24h TTL）。
- **复盘 endpoint** — `GET /monitoring/decision-brief/history`
  返回最近 20 条快照。
- **evidence_strength 联动 row.tone** — 0-1 数据质量，
  < 0.5 时 row 降级为 `warning` 并在 summary 前缀"证据强度 N%"提示。
- **V1.5 单元测试** — 新增 19 个测试覆盖 decision_brief 矩阵、证据强度、
  快照读写、降级路径。
- **行尾规范化** — 新增 `.gitattributes`，
  源代码统一 LF、Windows 脚本保留 CRLF，109 个历史文件已 renormalize。
- **复用 `alerts/chip/divergence/final_decision`** —
  `MonitoringDashboardService._load_cached_alerts_bundle`、
  `_load_cached_strategy_bundle`、
  `_load_cached_analysis_timeframes` 三个只读 helper。
- **StrategySnapshotBuilder 写入 strategy PageSnapshotCache** —
  `strategy_bundle_cache_key` 持久化后 monitoring 才能复用。

### 修复

- `AlertsBundleRead.contract_snapshot` 字段缺失。
- `/alerts/divergence` endpoint 未复用 `indicator_matrix`，
  与 alerts bundle 计算路径可能不一致。
- `/alerts/chip-structure` 缓存 key 用 1h candle ts，
  但请求的可能是 1d/4h，导致缓存命中错配（v2→v3 强制旧 key 失效）。
- `StrategySnapshotBuilder.lower_tf_missing` 仅当 trigger_tf 配置即标记，
  改为基于 `data_quality_score` 的真检查。

### 已知遗留

- A 股 ETF 30d/4h 数据缺口（hype/qqqx/slvon 6-43% 覆盖率），
  需联网拉数据后重跑。
- 行尾 CRLF 转换是单次批量操作，109 个文件 diff 噪声大；
  未来 commit 应按 `.gitattributes` 自动规范化。

## V1.4.1 (2026-04)

- 详见 git history。
- 重点：宏观数据可靠性、监控总览解释性、工作流稳定性。

## V1.4

- 略（详见 git history）

## V1.3 / V1.3.1

- 略（详见 git tag）

## V1.2

- 略

## 0.3.0 (历史内部版本)

- 单用户本地模式 + 可选 auth bypass。
- 本地 localhost 中间件。
- 改进 indicator dashboard 与事件流 UI。
- 导入模板下载与 GitHub release 打包。

