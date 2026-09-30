# CIS System Integrity Remediation Report

- **Baseline**: `CIS-UI2-V2.3-Page-Migration`（V2.3 定版批次已入库，基线 commit `5655028..d072795`）
- **执行日期**: 2026-09-30
- **范围**: P0-QNT-001、P1-QNT-002、P1-SEM-001、P1-STATE-001（严格按此顺序实施）
- **证据登记**: `CIS_P0_P1_FIX_REGISTER.md` §3（逐项 Before → Change → Test → After）

> **所有者决定（2026-09-30）**：`.env` 中的密钥均为所有者为本分发单独创建，明文写入并嵌入内部便携包系所有者授权的设计，不构成泄漏事项。原整改指令中的 P0-SEC-001「分发秘钥隔离」与配套轮换要求据此**撤回**；secret scan 门禁保留为默认不含 `.env` 的安全默认值，所有者可用显式 `--embed-local-env` 开关按原设计嵌入（校验脚本对应 `--allow-embedded-env`）。详见 `CIS_P0_P1_FIX_REGISTER.md` 的 P0-SEC-001 条目。

# Executive Summary

4 个经源码复核确认的完整性问题全部修复并独立提交。核心成果：

1. **打包卫生（保留的基础设施）**：构建器 secret scan 门禁作为安全默认上线（默认不含 `.env`、凭证类文件名与非占位敏感赋值即构建失败）；所有者授权的分发可用 `--embed-local-env` 显式嵌入，豁免精确到 `source/.env` 单个文件，其余文件照扫。
2. **资产隔离**：方向信号带显式资产作用域，resolver 在加权前执行 fail-closed 资格门禁；BTC 衍生品对比特币仍有效（positive control），对 ETH/BNB/HYPE/OKB 的方向影响被证明为零，BTC 绝对价位不再进入非 BTC 价位体系。
3. **量化契约**：资金流方向只来自真实变化量，绝对正 level 不再等于流入；链上指标按共享契约读取并带指标级新鲜度/质量门禁。
4. **评分语义**：策略评分全面改称「证据质量 N/100」并携带 `confidence_kind` 语义字段，不再以「置信度 %」暗示成功概率。
5. **状态真实**：Shell 双健康 chip（服务/数据）以可观测状态投影，初始未知、无证据不给绿。

## P0 Status

| Finding | Status | 关键证据 |
|---|---|---|
| P0-QNT-001 | **FIXED** | 7 项隔离测试 PASS：BTC derivatives bullish→bearish flip 下，ETH/BNB/HYPE/OKB 的 direction/unified_code/position_cap/permission/trade_plan_inputs 完全不变且无 BTC 墙价位泄漏；同一 flip 使 BTC tactical LONG→SHORT。resolver 资格门禁 + 生产信号归属声明 + 前端「BTC 市场代理上下文」标注三层实现。 |
| ~~P0-SEC-001~~ | **WITHDRAWN（所有者决定）** | 泄漏前提不成立（密钥为所有者为本分发单独创建）；打包门禁保留为安全默认 + 显式授权开关，见 Executive Summary §1。 |

## P1 Status

| Finding | Status | 关键证据 |
|---|---|---|
| P1-QNT-002 | **FIXED** | `test_capital_flow_reads_onchain_metric_contract` 9 项 PASS：Case A（正 level → DATA_INSUFFICIENT，非 LONG）、B/C（正/负 delta → INFLOW/OUTFLOW）、D/E（stale/低质量 → 剔除）；历史派生测试证明 delta 来自真实序列（108/101≈+6.93%），未伪造。 |
| P1-SEM-001 | **FIXED** | 5 项静态守卫 PASS：渲染器无「置信度」残留、`证据质量 N/100` + 非概率 tooltip 在位、ScanItem/审计 payload 带 `confidence_kind`/`confidence_is_probability`、知识库声明非校准概率。 |
| P1-STATE-001 | **FIXED** | 6 项守卫 PASS + 实例冒烟：模板无「系统在线/数据连接正常」、双 chip 初始 `unknown`、CSS unknown 无正向色；服务/数据来源独立（/health vs 请求成败 tracker）。 |

## Files Changed

（`git log 5655028..HEAD`）

- **packaging**: `scripts/build_private_portable.py`、`scripts/verify_portable_package.py`*、`scripts/build_release.py`、`tests/test_distribution_secret_isolation.py`*、`tests/test_private_portable_paths.py`、`tests/test_ui2_release_hardening.py`、`.env.example`、`docker-compose.yml`、`README.md`、`docs/remediation/*`（\*=新增；secret scan 门禁为默认安全值，`--embed-local-env` 为所有者授权通道）
- **strategy（P0-QNT-001）**: `app/core/timeframes.py`、`app/services/strategy_unified/{direction_resolution,unified_service,risk_gate}.py`、`app/services/market_context.py`、`app/static/pages/strategy/{renderDecisionAudit,adapter}.js`、`tests/test_cross_asset_signal_isolation.py`*、`tests/test_cross_asset_frontend_scope_labels.py`*、`tests/test_strategy_direction_resolution.py`
- **quant（P1-QNT-002）**: `app/services/onchain/{metric_reader,feature_engine}.py`、`app/services/strategy_unified/capital_flow.py`、`tests/test_capital_flow_reads_onchain_metric_contract.py`*
- **semantics（P1-SEM-001）**: `app/services/strategy_unified/{opportunity_scanner,unified_service}.py`、`app/static/pages/strategy/{renderScanRanked,renderTimeframeFocus,renderScanMatrix}.js`、`app/static/core/knowledge.js`、`tests/test_evidence_quality_semantics.py`*
- **shell（P1-STATE-001）**: `app/templates/page.html`、`app/static/core/{shellHealth,api,main}.js`、`app/static/editorial.css`、`tests/test_shell_health_truthfulness.py`*

## System Invariants Added

- **INV-001** BTC exact 信号不能改变非 BTC 方向 → `test_cross_asset_signal_isolation.py`（7 测试）
- **INV-002** 绝对正 level ≠ 流入 → `test_capital_flow_reads_onchain_metric_contract.py`（9 测试）
- **INV-003** 启发式证据分 ≠ 校准概率 → `test_evidence_quality_semantics.py`（5 测试）
- **INV-004** 全局健康文案 = 可观测状态 → `test_shell_health_truthfulness.py`（6 测试）
- **INV-005** 分发归档**默认**不含凭证；显式 `--embed-local-env` 为所有者授权通道，豁免仅限 `source/.env` 单文件 → `test_distribution_secret_isolation.py`（5 测试）

## Tests Added

新增 6 个测试文件、**32 个测试函数**；另更新 `test_strategy_direction_resolution.py`（8 个既有用例按契约显式声明信号归属）与 2 个打包测试（新契约文案）。

## Existing Tests Result

- 全量 `pytest`（隔离实例 BASE_URL=:8003，WORKER_PROFILE=none）: **2276 passed、4 skipped、0 failed**（基线 2229 + 本轮新增 47）
- ruff（全部整改文件 + 目录范围）: **All checks passed**
- `python -m compileall app tests scripts`: **通过**
- `verify_pages.py` 全量: **11/11 冷启动、10/10 SPA 切换、0 失败**（0 pageerror / 0 console error）
- `stress_test.py --page ai-strategy`: **2 PASS / 0 FAIL**（21 动作 0 失败；pending-scan→SPA 退出 233ms）
- 无密钥默认包（NONSECRET-20260930）: `verify_portable_package.py --extract` 全 PASS + 启动冒烟 `/health/live → 200 {"status":"ok"}`（该包为默认模式验证产物；所有者授权分发构建时传 `--embed-local-env` 并以 `--allow-embedded-env` 校验）

## Cross-Asset Verification

见 P0-QNT-001：ETH/BNB/HYPE/OKB × {bullish, bearish} 全矩阵不变；BTC positive control 有效；exact 不匹配与 unknown scope 均被隔离并留审计 conflict（`cross_asset_signal_isolated`）；交叉验证矩阵复用同一门禁，隔离信号不作为参与行出现。

## Quant Logic Verification

metric dict 契约读取（raw number payload fail closed）、正 level 不产生方向、正/负 delta 方向、stale/低质量剔除、小 delta 中性、文本 flow_bias 仅诊断、真实历史派生 1d/7d 变化量——全部由测试钉住。

## UI Semantic Verification

ranked 卡、周期聚焦 chip、矩阵门禁、知识库词条四处用户可见面全部转为证据质量语义；`confidence_kind/confidence_is_probability` 随 asdict 进入 API payload，前端与未来消费者无法误读。

## Remaining P2 Items

按整改指令登记 DEFERRED（`CIS_P0_P1_FIX_REGISTER.md` §2）：P2-001 `fresh_until` 语义、P2-002 Monitoring BTC/1D scope（NO CHANGE REQUIRED）、P2-003 URL 上下文持久化、P2-004 组合感知（仅语义说明，不建 Portfolio Engine）。

## Manual Actions Required

1. **正在运行的旧实例**：8002 端口存在一个本轮之前启动的用户实例（PID 36844），其 Python 进程仍是旧代码（静态文件已从磁盘读到新 JS）。需要重启该实例以加载全部后端修复。

## Known Limitations

- 门禁内容扫描覆盖 config-surface 文件（.env*/yaml/toml/ini/cfg/conf/bat/cmd/ps1/json），不扫 .py/.js 源码（避免测试 fixture 误报）；源码内嵌密钥不在该门禁防御范围。
- 本轮未建 ETH/BNB/HYPE/OKB derivatives service（§4.5 临时安全政策）；跨资产代理传导需未来显式 `CrossAssetProxyPolicy`。
- 数据质量 chip 是「近期请求成败」的粗粒度投影，按数据源细分仍由页面内状态卡表达。
- 观测历史深度不足时，资金流维度如实输出 DATA_INSUFFICIENT（依赖监控面积累 onchain observations）。
