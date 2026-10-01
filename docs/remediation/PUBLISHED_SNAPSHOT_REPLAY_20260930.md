# 发布快照回放记录（2026-09-30）

输入为 `scripts/create_verification_db.py` 从本机真实发布库抽取的精简验证库（11 个品种、175 条页面快照）；不复制完整历史库，不改写运行库。复现命令：

```text
cd source
python -m scripts.create_verification_db --source runtime/data/trading_system.db --output runtime_dev/verification_snapshot_replay.db
python -m scripts.replay_published_strategy_snapshots --db runtime_dev/verification_snapshot_replay.db
```

回放以发布 BTC 快照的衍生品信号为基线，将其中的多头确认翻转为空头，并以当前资产归属门禁重新解析。历史快照生成于资产归属字段显式化之前，因此回放会给历史信号补上当前归属语义；这不是重新运行历史行情采集或重建整份策略。BTC 的衍生品卡片与总决策在这份样本中均维持中性/等待，表明仅这一个信号翻转不足以越过其余门禁，不能据此宣称 BTC 必须反向交易。

ETH、BNB、HYPE、OKB 在翻转前后的战略/战术/执行方向、交易许可、仓位上限和计划输入逐字段相同。回放将每个品种的 1W、1D、4H 矩阵单元来源键与统一策略详情键核对，并把监控摘要按读取路径重新投影；五个品种的监控 canonical 键均与详情一致。BTC 的键为 `btc-usdt-perp:4e6d5553d94b5f62`。监控存储行本身较旧，实际读取路径会核对时效；过期时不会把旧方向冒充为当前结论。

新扫描发布才会携带单元来源键；旧扫描行若曾标记可交易却没有来源键，API 会降为待更新，直到后台重新发布。前端只在同一快照代际下展开详情。
