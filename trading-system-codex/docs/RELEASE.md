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

### 已知限制

- `chip_structure.direction_score` 仍是 K 线涨跌 proxy，完整 microstructure (OI / CVD / orderbook) 留待后续 V1.5.x 重写。
- 监控总览页不重算方向，所有方向分均来自 strategy_bundle / alerts / final_decision 三个上游。
- 当 structure / strategy bundle 都没有 cache 时，V1.5.2-T08 fallback 用
  alerts.chip_structure 占位，标 "证据不足（仅 K 线涨跌 proxy）"；
  用户应理解为"结构页 pipeline 未跑出快照，暂用筹码页代理"。
- `MarketRepository` 在测试中通过 fake 注入；snapshot 真实环境仍走
  `get_page_snapshot_cache`，DB schema 未变。
