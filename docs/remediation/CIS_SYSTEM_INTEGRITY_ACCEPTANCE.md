# CIS System Integrity Acceptance

> 关闭条件：以下每一项都有 Before/Change/Test/After 证据（见 FIX REGISTER §3）。
> 测试矩阵覆盖不足、或只通过新增测试而未跑存量门禁，均视为未关闭。

## 1. System Invariants（写入测试与文档）

| ID | Invariant | 钉住方式 |
|---|---|---|
| INV-001 | BTC-specific exact signal 不能直接改变非 BTC 策略方向 | 跨资产不变性测试 ×4（ETH/BNB/HYPE/OKB）+ BTC positive control |
| INV-002 | 绝对正值 market metric 不得被解读为正向 flow，除非该 metric 本身表示变化 | capital flow 契约测试 Case A–E |
| INV-003 | 启发式证据分不得被呈现为校准概率 | 静态/UI 守卫：禁「成功概率/胜率/XX% certainty」默认呈现 |
| INV-004 | 全局健康文案必须反映可观测状态，不得是静态乐观默认 | shell 状态机测试：ready/degraded/offline/unknown/page-data-degraded |
| INV-005 | 分发归档默认不得包含私有凭证 | 包 secret scan gate + 分发内容测试 |

## 2. Required Test Matrix

- **A. Secret isolation**: distribution_without_env / archive_secret_scan / temp_secret_cleanup
- **B. Cross-asset invariance**: ETH、HYPE、BNB、OKB × {bullish BTC derivatives, bearish BTC derivatives} → 核心策略结果 invariant
- **C. BTC positive control**: BTC derivatives signal 对 BTC 策略仍然生效
- **D. Capital flow contract**: metric dict parsing / absolute level / positive delta / negative delta / stale / missing / poor quality
- **E. Confidence semantics**: 禁止 heuristic evidence score 默认显示为成功概率/胜率
- **F. Shell truthfulness**: ready / degraded / offline / unknown / page-data-degraded

## 3. P0 验收标准

### Security（P0-SEC-001）
- [ ] 新构建 ZIP：无 `.env`、无嵌入 secret 值、无 credential artifact
- [ ] secret scanner：PASS（BUILD FAIL 语义，非 warning）
- [ ] 历史 credential 轮换状态已登记（`SECRET_ROTATION_REQUIRED.md`，只记键名）
- [ ] 临时解压目录 try/verify/finally cleanup；cleanup 失败显式上报

### Cross-Asset（P0-QNT-001）
- [ ] BTC derivatives → BTC 方向链路正常工作（positive control）
- [ ] BTC derivatives ⇏ ETH / BNB / HYPE / OKB direction（除非未来显式 proxy policy）

## 4. P1 验收标准

- [ ] Capital Flow：不再存在「positive absolute level = inflow」路径；只用 change/trend/deviation 或 neutralize
- [ ] Confidence：用户不会自然把评分理解成预测成功概率；API/UI/Knowledge 语义一致
- [ ] Health：Shell 不得无证据地常显「正常/在线」；Service Health 与 Market Data Quality 语义分离

## 5. 最终验证（不得只跑新增测试）

- [ ] ruff（改动范围 0 错）
- [ ] 全量 pytest（记录 passed/failed/skipped）
- [ ] compileall
- [ ] 架构/策略页改动 → `verify_pages.py` 全量（冷启动 + SPA）
- [ ] 策略页改动 → `stress_test.py` 策略页
- [ ] portable 构建 + 校验（新包）
- [ ] Strategy 专项 regression：MarketContextBuilder / DirectionResolution / UnifiedStrategy / OpportunityScanner / OnchainFeatureEngine / CapitalFlow / Health / strategy 前端静态契约

## 6. Stop Condition

P0/P1 验收全部满足后 **STOP**：提交 `CIS_SYSTEM_INTEGRITY_REMEDIATION_REPORT.md`，等待下一轮独立复核。不自动继续 P2 重构、UI redesign、页面合并、框架迁移、组合扩展、模型增强。
