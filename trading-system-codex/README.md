# 交易系统 FastAPI

基于 `FastAPI + SQLite + Gate.io` 构建的 Windows 本地加密货币研究与交易管理应用。

当前版本：**V1.5.5**（详见下方 [Release Timeline](#release-timeline)）。

## Release Timeline

`V1.5` 系列在 V1.5 监控总览可解释性闭环的基础上，引入了"可解释性 + 性能 + UI 清晰度"三方面的迭代。每个 release 独立可发布、内容自洽；下面的版本号按工作落地顺序排列。

### V1.5 — 监控总览可解释性闭环

V1.5 聚焦在 **监控总览可解释性闭环**。终端摘要现以三行 `decision_brief` 形式呈现：

- `市场情况` (market situation)
- `交易指引` (trading guidance)
- `风险点 / 失效条件` (risk / invalidation)

每行携带一个 `evidence_strength` (0-1)，由新增的多周期冲突矩阵
`terminal_summary.decision_brief.source_alignment.matrix` 计算。
当证据强度跌破 `0.5` 时，行语气降级为 `warning`，summary 前缀加显式
的不确定性提示。

每次 `MonitoringDashboardService.refresh_bundle` 之后，`decision_brief`
都会持久化到 `ComputedDatasetCache`，用户可通过
`GET /monitoring/decision-brief/history` 复盘历史决策。

### V1.5.1 — long/short reasoning 审计 (7 项修复)

V1.5.1 是审计驱动的多空推理链重写。审计发现：

- `normalize_direction_metrics(score)` 默默把 signed chip 分数
  （范围 -100..+100）当成 legacy 0..100 值处理，导致在打分引擎
  里被重复计入；
- `next_trigger` 不是多态 — 字符串触发器、列表触发器、字典触发器
  走不同输出路径，其中一条路径会被静默丢弃；
- 门控在每个调用点 ad-hoc 解析，`block` / `warning` 走字符串匹配，
  结构化的 `GateDiagnostic` 丢失；
- 5 个 feature 来源（trend / structure / regime / momentum / flow）
  不独立 — 改一个 EMA 会污染多个分；
- 短周期快照不是从 cache 加载，而是从 aggregate data quality 推断；
- ATR × leverage 没有用于期货保证金压力；
- `MonitoringDashboardService` 会用自己的默认值覆盖调用方的
  `instrument_id` / `timeframe`。

T01-T07 七项修复：

- **T01** `normalize_direction_metrics(score, *, scale="signed")`
  强制显式 scale。Chip 走 `scale="signed"`；legacy 输入抛 `ValueError`。
- **T02** `next_trigger` 接受 `str | list | dict`，输出统一规范化文本。
- **T03** 门控解析为 `GateDiagnostic`（code、status、severity、
  message、current、required），分 `block / warning / info` 三级；
  trading row 用 `；` 拼接 blockers 并内联 warning。
- **T04** `snapshot_builder` 拆出 5 个独立分量（mtf_trend / structure /
  regime / momentum / flow），并给每个分量打 `*_source` 标签，
  调用方清楚知道是哪个输入在动。
- **T05** `lower_tf_snapshot` 从 `PageSnapshotCache` 加载；老的
  `data_quality_score < 60` 启发式删除。
- **T06** `compute_futures_risk` 读 `atr_14` × `default_leverage`，
  输出 `block / downsize / watch / ok` 四档压力；并有强平缓冲检查：
  止损离强平线 < 1.5 ATR 时强制 `block`。
- **T07** `MonitoringDashboardService.get_bundle` 不再覆盖调用方
  入参；只有当 FastAPI 默认值生效时空字符串才回退到
  `btc-usdt-perp` / `1d`。

### V1.5.2 — 监控总览 4 项用户反馈修复

V1.5.2 关闭了用户在 live 部署中点击监控页时发现的 4 个问题：

- **T08** 结构模块现在读真实的 `structure_bundle` cache（带
  `strategy.structure_overall` 与 `alerts.chip_structure` fallback），
  永久 `待确认` 占位不再出现。
- **T09** Decision brief 行重设计：删 `trading_guidance`（重渲了
  策略页）和 `risk_invalidation`（罗列每个 chip / divergence /
  structure 风险）。新行集：`market_situation`（一句话 headline +
  per-TF bullets）+ `mtf_breakdown`（多周期冲突时显示 per-TF 列表）+
  `key_risk`（前 1-2 条关键失效条件 + 数据缺口）。
- **T10** 期货保证金压力按 actionable 策略状态 gate —
  `OBSERVE / NO_EDGE / WAIT_* / EVENT_WAIT / RISK_OFF /
  INVALID_PLAN_LEVELS / 终态` 隐藏该 bullet。"OBSERVE + 建议减半仓位"
  矛盾不再渲染。
- **T11** `MonitoringDashboardService.get_bundle` 在 cache stale
  时真的调用 `refresh_bundle`。旧代码只 log "refresh is needed"
  然后返回 stale 载荷。修复后真正调用 refresh，refresh 自身失败时
  才回退到 stale。

### V1.5.3 — 死代码清理 + 快赢性能

V1.5.3 删除了 V1.5.1 / V1.5.2 残留的 dormant 助手，并应用审计中
识别的快赢性能修复：

- **A1-A6** 删除 `terminal_summary_engine` 5 个 dormant 助手
  （`_summarize_legacy`、`_decision_describe_timeframes`、
  `_decision_describe_strategy_levels`、
  `_decision_build_trading_row`、`_decision_build_risk_row`）。
- **A9** 删除 2 个 dead 端点（`/alerts/chip-structure`、
  `/strategy/iteration-proposals`）和对应 JS helper。
- **A10-A12** 删除 3 个未读 `MonitoringDashboardRead` 字段
  （`technical_source`、`technical_indicator_count`、
  `onchain_observations`）、2 个 schema alias
  （`StrategyV15DecisionRead`、`StrategyV15BundleRead`）、
  `build_bundle` alias、以及 `_terminal_summary_payload` 未用的
  `_cached` 参数。
- **B1** 静态资源缓存头：`no-store` → `public, max-age=3600,
  must-revalidate`（依赖已有 `?v=<mtime>` 自动 bust）。
- **B2** `get_bundle` 4 处串行 cache 读改为 `asyncio.gather`；
  `_load_cached_analysis_timeframes` 内部 3-TF 循环也 gather。
- **B5** Chip payload 通过 `SharedQueryCache` 去重
  （`alerts_bundle:chip_payload:v1:{inst}:{tf}`，TTL
  `settings.shared_query_cache_seconds`）。
- **B6** Chart.js CDN 标签包 `{% if page_id == "market-analysis" %}`
  并加 `defer` — 8/9 页跳过 200 KB 下载。
- **B10** `strategy.js` review-refresh listener race 修复
  （document event delegation）。
- **B11** `analysis.js scheduleBundleRetry` 上限 3 次。
- **B12** `alerts.js` 状态切换点击只做 surgical 行更新（仅 state +
  actions 两格），不再 refetch 整 bundle。

### V1.5.4 — 数据管道重构 + SPA 路由

V1.5.4 重做了数据管道热路径，并把 tab 导航改成进程内 SPA 路由：

- **C1** `ComputedDatasetCacheService.get_or_build_indicator_series`
  in-process 缓存，key 沿用 `indicator_series_cache_key`（已含 candle
  timestamp，新 candle 自动失效）。
- **C3** 新增 `MarketRepository.list_latest_observations_by_key`，
  用 SQL window function；macro overview 不再拉 5000 行在 Python
  端 dedupe。
- **C5** `MonitoringDashboardService.get_bundle` 把验证过的
  `MonitoringDashboardRead` 模型缓存在 `SharedQueryCache`，
  key 为 `(instrument_id, timeframe, data_ts, cache_state)`，TTL 60s。
- **C7** 新增 `MarketRepository.list_candles_for_instruments`，
  把 `_cross_asset_snapshot` 的 5 次串行查询合并为 1 条 SQL。
- **C12** `upsert_computed_dataset_cache` 改写为 dialect-native
  `INSERT ... ON CONFLICT (cache_key) DO UPDATE`（Postgres / SQLite
  各走对应 dialect）。
- **C11** `monitoring.js` `applyMonitoringDiff` 构建一个稳定 shell
  5 个命名容器，refresh 时只换 leaf innerHTML（不再整树重渲）。
- **D1** `main.js` 渐进式 SPA 路由：拦截 `[data-page-link]` 点击、
  preventDefault、pushState、对同一 shell 重跑 boot()。后端
  `/<page>-page` 路由仍作为 deep-link fallback。

### V1.5.5 — 监控总览 6 项用户反馈修复

V1.5.5 关闭了用户对监控页的第二轮反馈：

- **⑥** `monitoring_dashboard._load_cached_structure_payload`
  改为读 `payload.snapshot.overall.{overall_bias, score,
  regime, confidence, ...}`，替代原来错误的顶层
  `payload.get("score")`。修复了"结构页看空，监控页中性"的
  矛盾。`StructureSummaryAdapter._BIAS_TO_IMPACT` 补上
  `weak_bullish / weak_bearish / mild_* / uncertain /
  no_clear_structure` 映射并加 score clamp，弱方向 token 不再
  漏到 `neutral`。chip_structure proxy 路径强制 `confidence=0.2`
  + `is_proxy=True`，proxy 永远不再伪装成真实信号。
- **②** `_determine_regime` 末尾按 `global_score` 子分类为
  `偏多震荡`（>= 55）/ `偏空震荡`（<= 45）/ `中性震荡`（中间）。
  前端把 `regime` + `bias · confidence` 两个 chip 合并为单个
  regime chip + 置信度数字。
- **③** 头部（`_generate_text` 末尾分支）和 `_decision_build_market_row`
  4 个 summary 分支各自砍到 1 句话。Regime 前缀去掉（head chip
  已经显示）。
- **④** `_decision_build_key_risk_row` 不再渲染 `数据缺口`
  bullet（那是内部数据质量报告，不是用户风险）；行 summary 改为
  `关键失效条件：{topmost invalidation}`。`_decision_text` 不再
  `str(dict)` repr — 拆 `text / message / label / reason / summary`
  字段，单元素 list 也拆。
- **⑤** 新增 `SOURCE_REF_META` 给每个 `source_ref` key 一个
  中文 label + 目标页面。前端把 chip 渲染为
  `<a data-page-link="{page}">`，复用 V1.5.4 D1 的 SPA 路由。
  `missing:{bundle}` ref 加 `(未刷新)` 后缀并指向所属页面。
- **①** `monitoring-snapshot-grid` 改为
  `grid-template-areas: "terminal terminal / macro technical"`。
  TERMINAL BRIEF 卡片现在跨满 content 宽度，MACRO 和 TECHNICAL
  共享第 2 行。6 个 vote tile 仍留在 brief 卡片内部，headline
  加 `line-clamp: 3`。

详细 pre-flight 清单和实地核查命令见 `docs/RELEASE.md`。

## Source Of Truth

- 项目主目录：仓库根
- 推荐运行模式：本地单用户
- 支持 Python：`3.11` 与 `3.14`
- 推荐本地 host：`127.0.0.1`

本项目是本地研究工具，不是公开 SaaS，也不是自动化执行引擎。

## Project Layout

- `app/`：API、workers、services、templates、static 资源
- `tests/`：回归与行为检查
- `alembic/`：数据库 migration
- `scripts/`：工作区自动化、清理、发布打包
- `docs/`：项目文档与归档笔记

本地运行状态刻意放在仓库外：

- `..\runtime_dev\.venv`：开发用 Python 虚拟环境
- `..\runtime_dev\source_runtime`：源码模式下的数据库、日志、cache、临时文件
- `..\TradingSystemPortable`：生成的便携包；不要手动改

## Windows Quick Start

1. 在源码树之外创建并激活支持的虚拟环境。

```powershell
py -3.11 -m venv ..\runtime_dev\.venv
..\runtime_dev\.venv\Scripts\Activate.ps1
```

也可以用：

```powershell
py -3.14 -m venv ..\runtime_dev\.venv
```

2. 复制示例环境文件。

```powershell
Copy-Item .env.example .env
```

3. 安装依赖并跑质量检查。

```powershell
python scripts/tasks.py install
python scripts/tasks.py check
```

4. 启动本地应用。

```powershell
python scripts/tasks.py dev-local
```

如果用工作区标准外部环境，这个 helper 在端口 `8002` 启动源码实例，
并把运行文件隔离在仓库外：

```powershell
.\scripts\dev_env.ps1 -StartServer
```

在源码树里双击启动用：

```powershell
.\start_source.bat
```

`start_portable.bat` 仅供生成的 `TradingSystemPortable` 便携包使用，
它依赖 `runtime_env\python` 下的内嵌 Python 运行时；源码仓库里双击
会失败。

5. 打开本地 UI。

- Dashboard: [http://127.0.0.1:8002/dashboard](http://127.0.0.1:8002/dashboard)
- Indicators: [http://127.0.0.1:8002/indicators-page](http://127.0.0.1:8002/indicators-page)
- Market events: [http://127.0.0.1:8002/market-events-page](http://127.0.0.1:8002/market-events-page)
- Imports: [http://127.0.0.1:8002/imports-page](http://127.0.0.1:8002/imports-page)

## Windows Task Runner

可用 `python scripts/tasks.py <task>` 或 `.\scripts\dev.ps1 <task>`。

可用 task：

- `install`：安装可编辑的 app 与开发依赖
- `dev`：在 `127.0.0.1:8000` 跑 Uvicorn
- `dev-local`：在 `127.0.0.1:8002` 跑 Uvicorn
- `test`：跑 `pytest -q`
- `lint`：跑 `ruff check .`
- `check`：跑 lint、tests、compile 烟测、import 检查、JS 语法检查
- `clean`：删除生成的 cache、日志与安全的本地运行产物
- `release-zip`：构建 GitHub release zip
- `build-portable`：构建便携发行包
- `portable-preflight`：发布前校验便携包

开发 task 在以下情况快速失败：

- Python 不是 `3.11`
- Python 不是 `3.11` 或 `3.14`
- 没有激活虚拟环境
- 缺少 `pytest`、`ruff`、`uvicorn` 等必需工具

## Makefile Mapping

`Makefile` 仍可用于 CI 与类 Unix 环境。

- `make install`
- `make dev`
- `make dev-local`
- `make test`
- `make lint`
- `make check`
- `make clean`
- `make release-zip`

## Health And Stability

- 健康端点：
  - `/health`
  - `/health/live`
  - `/health/ready`
- 默认 worker profile：`desktop_light`
- 市场事件翻译使用 provider cooldown 机制，减少重复 `429` 噪音
- Websocket 断线视为可恢复并自动重连

## Verification Gate

按 `AGENTS.md` 与 `docs/RELEASE.md` 的要求，每次变更必须通过：

```text
[ ] python -m ruff check .              All checks passed
[ ] python -m compileall -q app tests scripts   0 error
[ ] python -c "import app.main"          OK
[ ] python -m pytest -q                  X passed, 0 failed
[ ] node --check app/static/**/*.js       all passed
```

V1.5.5 基线：**493 passed / 5 skipped / 0 failed**（5 个 skip 是先于
本次工作的 `chip_structure` 测试）。

## Cleanup Rules

`python scripts/tasks.py clean` 只删安全生成的产物：

- `__pycache__`
- `.pytest_cache`
- `.ruff_cache`
- `.mypy_cache`
- `run/`
- `*.pyc`
- `*.log`
- `dist/`
- `build/`
- `site/`
- `htmlcov/`
- `trading_system.db-shm`
- `trading_system.db-wal`
- `trading_system.db-journal`

cleanup task 不删：

- `.env`
- `trading_system.db`
- 本地导入的数据
- `docs/`
- tests、migration、应用源码

## Release Packaging

用以下命令构建发布包：

```powershell
python scripts/tasks.py release-zip
```

输出：

```text
dist/trading-system-fastapi-github.zip
```
