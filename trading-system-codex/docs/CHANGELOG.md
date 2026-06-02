# Changelog

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

- 详见 `README V1.4.1 Portable.md` 历史版本与 `archive_old/...` 快照。
- 重点：宏观数据可靠性、监控总览解释性、工作流稳定性。

## V1.4

- 略（详见 git history）

## V1.3 / V1.3.1

- 略（详见 git tag）

## V1.2

- 略

## 0.3.0 (历史内部版本)

- 详见 `docs/archive/changelog-legacy.md`
