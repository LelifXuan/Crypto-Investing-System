# CIS System Integrity Acceptance

> **2026-09-30 后续所有者决定**：本表 INV-005 中的“默认无密钥 + 显式开关”是当轮历史验收口径。当前内部 portable 必须原样内嵌非空 `source/.env`，校验器同时核对清单摘要和解压结果；其他凭证文件仍被拒绝。见整改报告顶部补充和 CHANGELOG 最新条目。

> 关闭条件：以下每一项都有 Before/Change/Test/After 证据（见 FIX REGISTER §3）。
> 测试矩阵覆盖不足、或只通过新增测试而未跑存量门禁，均视为未关闭。

## 1. System Invariants（写入测试与文档）

| ID | Invariant | 钉住方式 |
|---|---|---|
| INV-001 | BTC-specific exact signal 不能直接改变非 BTC 策略方向 | 跨资产不变性测试 ×4（ETH/BNB/HYPE/OKB）+ BTC positive control |
| INV-002 | 绝对正值 market metric 不得被解读为正向 flow，除非该 metric 本身表示变化 | capital flow 契约测试 Case A–E |
| INV-003 | 启发式证据分不得被呈现为校准概率 | 静态/UI 守卫：禁「成功概率/胜率/XX% certainty」默认呈现 |
| INV-004 | 全局健康文案必须反映可观测状态，不得是静态乐观默认 | shell 状态机测试：ready/degraded/offline/unknown/page-data-degraded |
| INV-005 | 分发归档**默认**不包含私有凭证；显式所有者授权（`--embed-local-env`）除外，豁免仅限 `source/.env` 单文件 | 包 secret scan gate + 分发内容测试 + 授权通道守卫 |

## 2. Required Test Matrix

- **A. Secret isolation**（按所有者决定调整为：默认无 env / 授权嵌入守卫 / archive_secret_scan / temp_secret_cleanup）
- **B. Cross-asset invariance**: ETH、HYPE、BNB、OKB × {bullish BTC derivatives, bearish BTC derivatives} → 核心策略结果 invariant
- **C. BTC positive control**: BTC derivatives signal 对 BTC 策略仍然生效
- **D. Capital flow contract**: metric dict parsing / absolute level / positive delta / negative delta / stale / missing / poor quality
- **E. Confidence semantics**: 禁止 heuristic evidence score 默认显示为成功概率/胜率
- **F. Shell truthfulness**: ready / degraded / offline / unknown / page-data-degraded

## 3. P0 验收标准

### Security（P0-SEC-001 → WITHDRAWN BY OWNER，2026-09-30）
> 所有者确认 `.env` 密钥均为其为本分发单独创建，明文嵌入内部包系授权设计，泄漏前提不成立，原轮换要求撤回（轮换登记文档已删除）。保留的工程成果：
- [x] secret scan 门禁作为安全默认：默认构建不含 `.env`、凭证类文件名与非占位敏感赋值即 BUILD FAIL 并删产物
- [x] 所有者授权通道：`--embed-local-env` 显式嵌入，豁免精确到 `source/.env` 单文件，manifest 如实记录 `embeds_local_env`；校验脚本对应 `--allow-embedded-env`
- [x] 临时解压目录 try/verify/finally cleanup；cleanup 失败显式上报（`verify_portable_package.py`，本轮验证 cleanup=clean）

### Cross-Asset（P0-QNT-001）
- [x] test_btc_derivatives_can_affect_btc_strategy PASS（bearish flip 下 BTC tactical LONG→SHORT）
- [x] 4 个不变性测试 PASS（bullish/bearish flip 下方向/计划输入/权限/仓位上限全不变）

## 4. P1 验收标准

- [x] Case A–E 测试 PASS；正 level → DATA_INSUFFICIENT
- [x] 「证据质量 N/100」+ confidence_kind 字段 + 知识库非概率声明，5 守卫 PASS
- [x] 双 chip 初始未知 + 双来源（/health 与请求成败），6 守卫 PASS + 实例冒烟

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
