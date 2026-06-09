# Changelog

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

