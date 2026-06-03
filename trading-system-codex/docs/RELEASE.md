# 发布流程

## 前置条件

1. `python scripts/tasks.py check` 全部通过。
2. 工作区改动已按功能域分组，避免混入运行时文件或构建产物。
3. `.env.example` 与 `portable.env.example` 不包含 secret，并覆盖必要配置说明。

## 发布步骤

```powershell
# 1. 质量门禁
python scripts/tasks.py check

# 2. 构建源码发布包
python scripts/tasks.py release-zip

# 3. 构建便携包
python scripts/tasks.py build-portable

# 4. 便携包预检
python scripts/tasks.py portable-preflight
```

## 产物

| 文件 | 说明 |
| --- | --- |
| `dist/trading-system-fastapi-github.zip` | GitHub 源码发布包 |
| `dist/trading-system-fastapi-github.zip.sha256` | 源码包校验文件 |
| `dist/portable_bundle.zip` | Windows 便携包 |
| `dist/portable_bundle.zip.sha256` | 便携包校验文件 |
| `dist/release_manifest.json` | 发布清单 |

## 便携包内容

便携包应包含：

- 嵌入式 Python 运行时：`runtime_env/`
- 应用源码和配置
- `TradingSystemLauncher.exe`
- `start_portable.bat`
- `portable.env.example`
- `README_PORTABLE.md`
- `portable_runtime.lock.json`
- `requirements-portable.txt`
- `release_manifest.json`

## 不应进入发布包的内容

- `runtime_dev/`
- `archive_old/`
- `TradingSystemPortable/` 本地镜像
- `.env`、secret、key、pem
- SQLite 数据库、日志、缓存、pytest/ruff 缓存
- `dist/` 内旧产物

## 提交策略

- 每个功能域独立提交，例如 `[macro]`、`[frontend]`、`[network]`、`[release]`。
- 不提交 `.db`、`.log`、cache、runtime 用户数据。
- 不提交 API key 或 secret。
- 发布前确认 `TradingSystemLauncher.exe` 存在；若无法构建 launcher，必须在发布说明中标注 `start_portable.bat` 为官方 fallback。

## V1.5 发布前验收清单（监控总览改造）

V1.5 在 V1.4.1 Portable 基础上新增监控总览页 `decision_brief`、
多周期冲突矩阵、决策快照持久化与 4 项 P2 风险修复。发布前需要确认：

- [ ] `python scripts/tasks.py check` 21/21 通过
- [ ] `python -m pytest tests/test_terminal_summary_engine.py tests/test_monitoring_dashboard_summary_sources.py tests/test_monitoring_decision_review.py tests/test_monitoring_frontend_static.py -q` 全绿
- [ ] `python -m ruff check .` All checks passed
- [ ] `python scripts/cross_check_and_retry.py` 9/9 PASS
- [ ] `python scripts/audit_user_facing_text.py` 0 failures
- [ ] `python scripts/audit_mojibake.py` 无新增 warn/block（既有 6 个 sanitizer 已知）
- [ ] `node --check app/static/**/*.js` 0 error
- [ ] 监控总览页 UI：终端摘要渲染为三行（市场情况 / 交易指引 / 风险点 / 失效条件）
- [ ] 当 alerts / strategy cache 缺失，`source_alignment.consistency = "degraded"` 且无方向伪造
- [ ] 当 4h/1d/1w 方向冲突，`trading_guidance` 文案降级为"等待确认"
- [ ] `ComputedDatasetCache` 表存在 `dataset_type=monitoring_decision_brief` 的历史快照
- [ ] `GET /monitoring/decision-brief/history` 可返回最近 20 条
- [ ] 每个 row 的 `evidence_strength >= 0.5`，否则 tone=warning 且 summary 前缀"证据强度"
- [ ] dist/ 产物（release-zip / build-portable / portable-preflight）通过且含 V1.5 内容
- [ ] `git tag v1.5` 已打
- [ ] 工作树无 CRLF/LF 混合（`.gitattributes` 已生效）

## V1.5.1 发布前验收清单（long/short reasoning 修复）

V1.5.1 在 V1.5 基础上完成 long/short reasoning 审查的 7 项修复 + V1.5.2
监控总览 4 项问题修复：

- [P0] `normalize_direction_metrics(score, *, scale)` 强制显式声明 signed / legacy_0_100
  - [ ] 0 / +20 / -20 / +40 / -40 / +80 / +100 / -100 八个边界用例通过
  - [ ] `scale="legacy_0_100"` 收到 0..100 范围外输入会抛 `ValueError`
  - [ ] `chip_structure.direction_score_scale == "signed"` 且 `evidence_quality_label` 非空
- [P0] `next_trigger` 兼容 str / list / dict 三种形态
  - [ ] 字符串触发器在 trading row 出现 "下一触发器：..." 文案
  - [ ] list 触发器以 "；" 拼接，empty 项被过滤
  - [ ] dict 触发器沿用旧的 label/price/timeframe 渲染
- [P0] Gates 统一解析为 `GateDiagnostic`
  - [ ] 严重度 `block` 在 trading row 前缀"执行前必须通过的策略门槛"
  - [ ] `severity=warning` 在 trading row 前缀"策略门槛状态"
  - [ ] `_decision_build_risk_row` 真正把 `blocking_gates` 渲染到 risk row
  - [ ] pass / info gate 被折叠，不占用 bullet 配额
- [P1] 5 个独立 feature 来源（trend / structure / regime / momentum / flow）
  - [ ] 改 EMA/ADX 输入只影响 `mtf_trend_*`
  - [ ] 改 `structure_overall.bias_score` 只影响 `*_structure`
  - [ ] 改 `market_regime` 只影响 `regime_fit_*`
  - [ ] snapshot 增加 `mtf_trend_source / structure_source / regime_source / momentum_source / flow_source` 标签
- [P1] 真实加载 lower_tf snapshot
  - [ ] snapshot 出现 `lower_tf_payload`（cache 命中时）或 `lower_tf_missing=True`（未命中）
  - [ ] `lower_tf_alignment.status` ∈ {aligned, conflict, neutral, missing}
  - [ ] 旧的 `data_quality_score < 60` 启发式已被删除
- [P1] ATR × leverage 合约保证金压力
  - [ ] snapshot 出现 `futures_risk.long` / `futures_risk.short` + `atr_pct` + `default_leverage`
  - [ ] 10x 杠杆 + ATR 3% → downsize / ATR 8% → block
  - [ ] 止损离强平线 < 1.5% 时强制 block
  - [ ] 风险行出现"合约保证金压力=block"等表述
- [P1] monitoring dashboard 不再硬覆盖 caller 入参
  - [ ] `get_bundle("eth-usdt-perp", "4h")` 返回的 bundle 是 eth/4h 而非 btc/1d
  - [ ] 空字符串入参仍 fallback 到 btc/1d 默认（API 层 `Query(default=...)` 行为不变）

### V1.5.2 监控总览页修复（用户实地反馈）

V1.5.2 在 V1.5.1 基础上修复 4 项监控总览页问题（用户用 playwright
实地核查发现）：

- [V1.5.2-T08] 结构模块从 "待确认" 占位升级到真实数据
  - [ ] `MonitoringDashboardService._load_cached_structure_payload` 优先读
    `structure_bundle_cache_key` 的结构页 cache
  - [ ] fallback 读 `strategy_bundle.decision.structure_overall`
  - [ ] 最终 fallback 用 `alerts_bundle.chip_structure`（带"证据不足（仅 K 线涨跌 proxy）" 标签）
  - [ ] `terminal_summary_engine.StructureSummaryAdapter` 把结构 payload
    翻译成 ModuleScore（regime/bias → score/impact/reason）
  - [ ] `module_scores.structure.state` 不再永远是"待确认"——若 3 个 cache
    全部为空才回到占位文案

- [V1.5.2-T09] 总览页 row 重构成"汇总层"
  - [ ] 删除 `trading_guidance` 行（不再重渲 strategy page 的 next_trigger /
    gates / plan levels / no_trade_reasons / permission）
  - [ ] 重命名 `risk_invalidation` → `key_risk`，只显示数据缺口 + 单条关键
    失效条件（从 chip / structure / divergence 中选优先级最高的 1 条）
  - [ ] 新增 `mtf_breakdown` 行——只在多周期方向冲突时出现，列出
    "1w 偏多(score 70) / 1d 偏空(score 35) / 4h 偏空(score 28)"
  - [ ] `market_situation` 的 headline 在多周期冲突时直接显示
    "高周期与短周期方向冲突：<breakdown>。请按你的交易周期判断。"

- [V1.5.2-T10] 期货保证金矛盾修复
  - [ ] `_decision_should_show_futures_pressure(decision)` 只对 actionable
    状态返回 True（*_TRIGGERED / *_BIAS / SETUP_DETECTED）
  - [ ] 观测页 risk row 在 OBSERVE / NO_EDGE / WAIT_* / EVENT_WAIT /
    RISK_OFF / INVALID_PLAN_LEVELS / 全部 terminal 状态下隐藏
    期货保证金 bullet
  - [ ] 策略页的 GateDiagnostic 行为不变——用户仍能在 strategy page
    看到仓位建议

- [V1.5.2-T11] 真正调用 refresh
  - [ ] `MonitoringDashboardService.get_bundle` 在 `allow_refresh=True`
    且 cache 缺失 / stale / error / updating / 实质为空时真正调用
    `refresh_bundle`，不再只 log "refresh is needed"
  - [ ] refresh 失败时 fallback 到 stale cache（带 warning log）

- [V1.5.2-T08 follow-up] primary_sources 真实反映数据来源
  - [ ] `source_alignment.primary_sources` 不再硬编码 `alerts_bundle` /
    `strategy_bundle` / `structure_bundle`
  - [ ] `alerts_bundle` 仅在 chip 或 divergence 非空时入 primary
  - [ ] `strategy_bundle` 仅在 strategy_decision 非空时入 primary
  - [ ] `structure_bundle` 仅在 `structure.source == "structure_bundle"`
    （即非 fallback 路径）时入 primary，否则落 missing_sources

### V1.5.1 验证命令

- [ ] `python -m ruff check .` All checks passed
- [ ] `python -m compileall -q app tests scripts` 0 error
- [ ] `python -c "import app.main"` 成功
- [ ] `python -m pytest -q tests/test_direction_score_scale.py tests/test_chip_scale_contract.py tests/test_terminal_trigger_format.py tests/test_terminal_gate_format.py tests/test_snapshot_feature_sources.py tests/test_snapshot_lower_tf.py tests/test_futures_risk.py tests/test_monitoring_dashboard_respects_caller.py` 全绿
- [ ] `python -m pytest -q` 全量 492 passed / 5 skipped / 0 failed
- [ ] `python scripts/cross_check_and_retry.py` 9/9 PASS（沿用 V1.5 入口）
- [ ] `node --check app/static/**/*.js` 0 error（监控总览页 JS 未改）

### V1.5.2 实地核查命令（playwright / webfetch）

- [ ] `GET /api/v1/monitoring/dashboard?instrument_id=btc-usdt-perp&timeframe=1d&force=true`
  - [ ] `module_scores.structure.state` ∈ {low_confidence, 待确认, 趋势结构,
    区间结构, 结构切换, 形态待确认}（不再永远是 待确认）
  - [ ] `decision_brief.rows[*].key` ⊆ {market_situation, mtf_breakdown, key_risk}
    且不含 `trading_guidance` / `risk_invalidation`
  - [ ] 全文不出现 "30.8" / "减半仓位" / "one-ATR" / "合约保证金压力" 字符串
  - [ ] 全文不出现 "策略状态：OBSERVE" + "建议减半仓位" 同时存在
  - [ ] 出现 "证据不足" / "proxy" 标签（仅当 structure pipeline 未刷新时）

## V1.5.3 发布前验收清单（清理 + 快赢优化）

V1.5.3 在 V1.5.2 基础上完成两件事：

1. 删除 V1.5.1 / V1.5.2 遗留的死代码、未读字段、未用的 endpoint。
2. 应用 V1.5.3 审计中"快赢"级别的性能修复（B1, B2, B5, B6, B10-B12），
   不涉及结构性重构（V1.5.4 范围）。

### V1.5.3 改动一览

**Group A — 死代码删除**

- [P0] `terminal_summary_engine.py` 删 5 个 dormant / unreachable 助手
  - `_summarize_legacy` (line 773) — `summarize()` 早已走 snapshot 路径
  - `_decision_describe_timeframes` (line 1985) — 被 `_decision_format_mtf_breakdown` 取代
  - `_decision_describe_strategy_levels` (line 2447) — 决策摘要不再 surface 价位
  - `_decision_build_trading_row` dormant shim (line 2604)
  - `_decision_build_risk_row` dormant shim (line 2765)
- [P0] 删 2 个 dead endpoint + 对应 JS helper
  - `GET /alerts/chip-structure` + `api.getChipStructure`
  - `GET /strategy/iteration-proposals` + `api.getStrategyIterationProposals`
- [P0] 删 3 个未读 schema 字段 + 1 个未用 alias + 1 个未用 helper 参数
  - `MonitoringDashboardRead.technical_source / technical_indicator_count / onchain_observations`
  - `StrategyV15DecisionRead / StrategyV15BundleRead` alias
  - `build_bundle` alias (= `build_bundle_uncached`)
  - `_terminal_summary_payload(_cached, ...)` 的 `_cached` 参数（永远不被使用）
- [P0] 删 monitoring.js dead fallback + `formatValue` 死函数
  - `getTerminalDecisionRows` 的 3 行 synthetic fallback
  - `function formatValue(value, digits)` (line 259)

**Group B — 快赢性能修复**

- [B1] `app/main.py:196` — `/static/*` 静态资源缓存头从
  `no-store, max-age=0, must-revalidate` 改为
  `public, max-age=3600, must-revalidate`。
  配合已存在的 `?v=<mtime>` query string，浏览器在 1 小时内
  命中 304 而非重新下载 styles.css (116 KB) + 各 page JS。
- [B2] `monitoring_dashboard.py:112-125` — `get_bundle` 的 4 个
  独立 cache 读改为 `asyncio.gather`；`_load_cached_analysis_timeframes`
  内部 3-TF 循环（4h/1d/1w）也 gather。
- [B5] `alerts_bundle.py:202` + `final_decision.py:71` — chip payload
  走 `SharedQueryCache`（key=`alerts_bundle:chip_payload:v1:{inst}:{tf}`,
  TTL=settings.shared_query_cache_seconds）。原本两次 chip.analyze
  现在 60 秒内复用同一份结果。
- [B6] `templates/page.html:43` — Chart.js CDN 标签包
  `{% if page_id == "market-analysis" %}` 并加 `defer`。
  8/9 页不再下载 200 KB Chart.js。
- [B10] `static/pages/strategy.js` — 删除 review refresh 的
  `setTimeout(100ms)` listener 绑定，改为 attachEvents() 内的
  document 级 event delegation。`data-strategy-review-refresh`
  在每次 `renderReviewPanel()` 重建后不会重复绑定。
- [B11] `static/pages/analysis.js` — `scheduleBundleRetry` 加
  `MAX_BUNDLE_RETRY=3` 上限。3 次失败后渲染 "后台暂未就绪"
  警告并停止重试，避免无限轮询。
- [B12] `static/pages/alerts.js:716-743` — 状态切换 PATCH 后只
  更新本行的 state + actions 两个 cell，不再 refetch 整 bundle。

### V1.5.3 验证命令

- [ ] `python -m ruff check .` All checks passed
- [ ] `python -m compileall -q app tests scripts` 0 error
- [ ] `python -c "import app.main"` 成功
- [ ] `python -m pytest -q` 全量 **493 passed / 5 skipped / 0 failed**
- [ ] `node --check app/static/**/*.js` 0 error

### V1.5.3 实地核查命令（curl）

- [ ] `curl -I http://127.0.0.1:8002/static/styles.css`
  - [ ] 响应头 `Cache-Control: public, max-age=3600, must-revalidate`
- [ ] `curl -I http://127.0.0.1:8002/monitoring-page`
  - [ ] 响应 body 不含 `https://cdn.jsdelivr.net/npm/chart.js`
    （只在 analysis 页加载）
- [ ] `curl http://127.0.0.1:8002/api/v1/monitoring/dashboard?instrument_id=btc-usdt-perp&timeframe=1d | jq '.terminal_summary.decision_brief.rows[].key'`
  - [ ] 仍是 V1.5.2 三行（market_situation / mtf_breakdown / key_risk），
    没有 V1.5.3 删除的字段（technical_source / technical_indicator_count
    / onchain_observations）

### 已知限制 / 延后到 V1.5.4

- B7（懒加载 `core/knowledge.js`）— 6 个 page 都用 `knowledgeTooltip`，
  全改 async 会污染 6 个调用点；留到 V1.5.4 统一处理
  FeatureComputationCache 一起做。
- B3（`_load_cached_structure_payload` 单次请求内复用）— 在 B2 重构后
  `get_bundle` 已经只在 payload 缺失结构时才调用一次，所以 B3 实质上
  已被 B2 取代。
- B4（`_decision_format_mtf_breakdown` 去重）— 经实测这个函数在
  market_row 和 mtf_breakdown_row 各被调用一次，输入相同输出相同，
  但函数本身只是 small-dict filter，CPU 开销 < 1ms，refactor 不划算。
- B9（`renderDashboard` 算 6 个 helper map 一次）— 同上，单次 render
  内 helper map 的 cost < 1ms，且当前各子 renderer 已经是纯函数
  调用，传递 helper map 需要改所有 renderXxx 签名，触及面广。
- A13（snapshot 20+ 个 flat-feature 字段清理）— 需要逐字段验证
  `strategy_generator` 是否真不读，预期放 V1.5.4 C 阶段与
  `FeatureComputationCache` 一起重做字段建模。
- 全部 D 组（SPA / ETag / DecisionPipeline / ServiceWorker）— V1.5.4
  范围。

## V1.5.4 发布前验收清单（结构性优化）

V1.5.4 在 V1.5.3 基础上完成 5 项数据管道重构 + 1 项前端 SPA 路由：

### 数据管道

- [C1] `ComputedDatasetCacheService.get_or_build_indicator_series`
  加 in-process cache（key 复用 `indicator_series_cache_key`，
  已含 candle ts 自动失效）。同进程并发读去重，1-2 指标构建。
- [C3] 新增 `MarketRepository.list_latest_observations_by_key`，
  用 SQL window function 让 DB 一次返回每键 1 行，替换
  `list_indicator_observations(limit=5000) + Python dedupe`。
  监控冷读 -40-120 ms。
- [C5] 监控 dashboard 路径把 Pydantic `MonitoringDashboardRead`
  验证结果存到 `SharedQueryCache`，key 包含 `data_ts`。
  60s 内同 `(inst, tf, data_ts)` 命中缓存免验证。
- [C7] 新增 `MarketRepository.list_candles_for_instruments`，
  1 次 SQL 取 5 个 cross-asset 币的最近 2 根 K 线，替换
  5 次 `list_candles` 串行循环。
- [C12] `upsert_computed_dataset_cache` 改用 dialect-native
  `INSERT ... ON CONFLICT (cache_key) DO UPDATE`（Postgres
  / SQLite 各走对应 dialect），1 RTT 替换 select-then-upsert 2 RTT。

### 前端

- [C11] `monitoring.js` 加 `applyMonitoringDiff()`，首次构建
  stable shell 5 容器并缓存引用，refresh 只换 leaf innerHTML，
  不再全树重渲。30-60 ms / refresh。
- [D1] `main.js` 加 progressive SPA router。点击
  `[data-page-link]` 拦截 + pushState + 重跑 boot()，
  避免 116 KB styles.css + main.js 重新下载。
  后端 `/<page>-page` 路由仍工作作为 deep-link 回退。
  Cmd/Ctrl/Shift/Alt+click 不拦截。

### V1.5.4 验证命令

- [ ] `python -m ruff check .` All checks passed
- [ ] `python -m compileall -q app tests scripts` 0 error
- [ ] `python -c "import app.main"` 成功
- [ ] `python -m pytest -q` 全量 **493 passed / 5 skipped / 0 failed**
- [ ] `node --check app/static/**/*.js` 0 error

### V1.5.4 实地核查（webfetch + playwright）

- [ ] `curl -s http://127.0.0.1:8002/api/v1/monitoring/dashboard?instrument_id=btc-usdt-perp&timeframe=1d | jq '.terminal_summary.decision_brief.rows[].key'`
  第二次调用应该 < 50ms（hit C5 缓存）
- [ ] `curl -I http://127.0.0.1:8002/static/main.js`
  `Cache-Control: public, max-age=3600, must-revalidate`
- [ ] playwright: 连续点击 5 个 tab，每个 tab 切换 < 100ms
  （SPA 路由命中 main.js 已加载，跳过 HTML re-parse）

### 已知限制 / 延后到 V1.5.5

- C4 (cache key 命名空间) — 风险低、收益低，留待下次 SQL 重构
  一起做。
- C6 (minify JS+CSS) — 需要引入 esbuild + lightningcss 作为
  build step；当前静态资源已被 B1 缓存头优化，短期内
  minify 的收益 < 100KB。
- C8 (alerts 状态切换) — 已在 V1.5.3 B12 落地。
- C9 (structure SVG 持久化) — 需要重写 structure.js 重渲染逻辑，
  触及面广，留待后续。
- C10 (analysis chart.update 复用) — 同上，触及面广。
- D2 (ETag / 304) — 等 ServiceWorker / 反代层统一做。
- D3 (DecisionPipeline 类型化) — 大型重构，留 V1.5.5 重做。
- D6 (ServiceWorker 离线) — 等 SPA 路由稳定后做。
- A13 (snapshot flat-feature 字段) — 需要 strategy_generator
  逐字段验证，留 V1.5.5。

### 已知限制

- `chip_structure.direction_score` 仍是 K 线涨跌 proxy，完整 microstructure (OI / CVD / orderbook) 留待后续 V1.5.x 重写。
- 监控总览页不重算方向，所有方向分均来自 strategy_bundle / alerts / final_decision 三个上游。
- 当 structure / strategy bundle 都没有 cache 时，V1.5.2-T08 fallback 用
  alerts.chip_structure 占位，标 "证据不足（仅 K 线涨跌 proxy）"；
  用户应理解为"结构页 pipeline 未跑出快照，暂用筹码页代理"。
- `MarketRepository` 在测试中通过 fake 注入；snapshot 真实环境仍走
  `get_page_snapshot_cache`，DB schema 未变。
