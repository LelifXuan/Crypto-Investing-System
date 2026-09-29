# CIS P0/P1 Fix Register

> 每项关闭时回填 Evidence 区块。状态枚举：`OPEN → IN_PROGRESS → FIXED(验证通过) / DEFERRED`。
> 禁止把未经验证的问题升级进本表；P2 项只在 §2 登记 DEFERRED。

## 1. Findings

### P0-SEC-001 — 分发包与真实 Secret 未分离

- **Status**: FIXED（2026-09-30）
- **Current behavior**: 见 Before 证据。
- **Root cause**: 分发边界设计把「内部授权」等同于「携带凭证」；`.gitignore` 只防 Git 入库，不防 distribution artifact 泄密。
- **Files affected**: `source/scripts/build_private_portable.py`、`source/scripts/verify_portable_package.py`（新增）、`source/scripts/build_release.py`、`source/tests/test_distribution_secret_isolation.py`（新增）、`source/tests/test_private_portable_paths.py`、`source/tests/test_ui2_release_hardening.py`、`source/.env.example`、`source/docker-compose.yml`、`README.md`、`docs/remediation/SECRET_ROTATION_REQUIRED.md`
- **Proposed minimal fix**: 已实施——构建器不再读取/包含/要求 `.env`；两段式 fail-closed secret scan gate（写入前列表扫描 + 写入后档案重扫，命中即删产物并 BUILD FAIL）；`runtime_python/` 路径受限豁免（stdlib `secrets.py` + certifi 公共 CA 束）；交付校验脚本（档案扫描 + 结构 + 可选解压核验 + cleanup 状态显式上报）；`.env.example` 示例值改显式 `CHANGE_ME`；轮换登记只记键名。
- **Tests added**: `test_distribution_contains_no_env`、`test_distribution_contains_no_private_credentials`、`test_distribution_secret_scan_gate`、`test_gate_allowlist_scoped_to_embedded_runtime`（4 passed）；`test_ui2_release_hardening` 文案契约按新语义更新。
- **Remaining limitations**: 门禁内容扫描只覆盖 config-surface 文件（.env*/yaml/toml/ini/cfg/conf/bat/cmd/ps1/json），不扫描 .py/.js 源码（避免测试 fixture 误报），源码内嵌密钥不在本门禁防御范围。

#### Evidence — P0-SEC-001

- **Before**: `build_private_portable.py:143` `files["source/.env"] = env_path`（原样打包）+ `:125` 缺 `.env` 即 `RuntimeError` + `:197` 断言包内有 `.env`；`dist/` 两个 2026-08-31 PRIVATE ZIP 含密钥；`.env.example:20/:25` 带示例默认值（`change-me`/`admin123` 形态），且运行中的 `source/.env` 使用相同值（masked 核验 `example==env? True`）。
- **Change**: 见 Proposed minimal fix；gate 首次运行即拦截 4 类违规（示例默认值 ×2、stdlib `secrets.py`、`cacert.pem`），前两类促成真实修复（example 占位化 + 轮换登记升级），后两类促成路径受限豁免并配 `test_gate_allowlist_scoped_to_embedded_runtime` 防扩大。
- **Test**: `pytest tests/test_distribution_secret_isolation.py tests/test_private_portable_paths.py tests/test_ui2_release_hardening.py` → **12 passed**；ruff（6 文件）All checks passed。
- **After**: 真实构建 `dist/CIS-UI2-V2.3-Page-Migration-NONSECRET-20260930.zip`（6136 files, 33,888,682 bytes, sha256 `2b21f2ec…ddbb8`）→ `verify_portable_package.py --extract`：`secret_scan=pass`（档案成员仅 `.env.example`，无 `.env`）、`structure=pass`、`manifest_parse=pass`、`extraction=pass`、`sensitive_cleanup_status=clean`、`sha256_sidecar=pass`；便携启动冒烟：解压目录内嵌运行时拉起 uvicorn:8003，`GET /health/live → 200 {"status":"ok"}`，退出后临时目录清理 done。构建过程未打印任何 secret 值。

### P0-QNT-001 — BTC derivatives 信号可污染非 BTC 策略方向

- **Status**: IN_PROGRESS（2026-09-30）
- **Current behavior**: `MarketContextBuilder` 对任意 instrument 注入 `btc_derivatives` 依赖；策略前端 detail 无条件拉 `getBtcDerivativesDashboard()`；`ModuleSignal.asset_lens` 默认 `btc_perp`；Direction Resolution 无目标资产隔离门禁。
- **Root cause**: 资产作用域是隐式约定而非显式契约；缺失声明时 fail open。
- **Files affected**: 调查后回填（预期 `services/market_context.py`、`services/strategy_unified/*`、`schemas/strategy_unified.py`、`static/pages/strategy/*`）
- **Proposed minimal fix**: Asset Scope Contract（`asset_scope ∈ {exact, proxy, global, unknown}` + `instrument_id`）；Direction Resolution 接收 `target_instrument_id` 并在加权前执行 eligibility gate（exact 不匹配 → 拒绝；proxy → directional_weight=0；unknown → fail closed）；BTC derivatives 对 BTC 保持 exact 可参与方向，对非 BTC 降级为 proxy 观察上下文；期权墙/Max Pain 等 BTC 绝对价位禁止进入非 BTC entry/stop/target/支撑/阻力。
- **Tests added**: `test_btc_derivatives_can_affect_btc_strategy`、`test_btc_derivatives_cannot_change_{eth,bnb,hype,okb}_direction`
- **Evidence**: 见 §3（回填）

### P1-QNT-002 — CapitalFlow 消费 onchain metric 的契约错误 + level 当 delta

- **Status**: IN_PROGRESS（2026-09-30）
- **Current behavior**: CapitalFlowEngine 对 `metrics["stablecoin_total_mcap"]` 做 `isinstance(.., (int, float))`，实际取得 dict，结构化信号永远不进入；若按取 `.value` 快修，`stablecoin_total_mcap`/`dex_volume_24h` 这类天然为正的 level 会被当成流入并推出 LONG。
- **Root cause**: ①消费方未按 OnchainFeatureEngine 的 metric dict 契约读取；②方向逻辑把绝对 level 当变化量。
- **Files affected**: 调查后回填（预期 onchain/capital flow 引擎 + 统一读取 helper）
- **Proposed minimal fix**: 新增 metric 读取 helper（返回 value/observation_ts/quality/freshness/usable）；资金流方向只消费 change/trend/deviation 类 feature；历史数据不足以算 delta 时返回 `NEUTRAL / DATA_INSUFFICIENT`、directional contribution=0；metric 级 freshness 独立于 Context 顶层 cache state。
- **Tests added**: `test_capital_flow_reads_onchain_metric_contract`（Case A–E）
- **Evidence**: 见 §3（回填）

### P1-SEM-001 — 启发式证据分被呈现为「置信度 %」

- **Status**: IN_PROGRESS（2026-09-30）
- **Current behavior**: strategy confidence 由 freshness/consistency/coverage 启发式合成，是证据质量分；UI 以「置信度 87%」「高确定性机会」呈现，自然被读成 87% 成功概率。
- **Root cause**: 字段名与文案沿用了概率语义，未声明评分种类。
- **Files affected**: 调查后回填（预期 schemas + strategy 前端 render 模块 + 知识库文案）
- **Proposed minimal fix**: 用户可见文案改「证据质量 87/100」；扫描 copy 改「高证据质量候选」；API 增加 `confidence_kind="evidence_quality"`、`confidence_is_probability=false`（兼容保留 `confidence` 字段）；tooltip/知识库明确「不代表预测胜率或盈利概率」。
- **Tests added**: 证据分不得显示为概率/胜率的静态与 UI 守卫
- **Evidence**: 见 §3（回填）

### P1-STATE-001 — Shell 全局健康状态写死为健康

- **Status**: IN_PROGRESS（2026-09-30）
- **Current behavior**: Shell 模板静态写「系统在线 / 数据连接正常」，无前端逻辑更新；可与页面级 stale/error/degraded 同时出现，构成系统级事实冲突。
- **Root cause**: 全局状态是静态乐观默认值，不是可观测状态的投影；Service Health 与 Market Data Quality 被混成一个绿灯。
- **Files affected**: 调查后回填（预期 `templates/page.html` + 新 shell 健康状态模块）
- **Proposed minimal fix**: Shell mount 时轻量检查 `/health`（30–60s 低频轮询），区分「服务正常/降级/不可达/未知」；数据质量来自页面实际数据（正常/部分降级/过期/不可用）；请求失败显示「服务状态未知」，禁止保留绿色在线。
- **Tests added**: `test_shell_does_not_hardcode_healthy_data_state`、`test_shell_health_{ready,degraded,unreachable}_state`、page-degraded + service-online 组合
- **Evidence**: 见 §3（回填）

## 2. Deferred（P2，本轮不改）

| ID | 主题 | 决定 |
|---|---|---|
| P2-001 | strategy `fresh_until` 实为当前时间取整分钟 | DEFERRED——未证明驱动核心交易判断；统一 cache contract 时修复 |
| P2-002 | Monitoring 固定 BTC/1D scope | NO CHANGE REQUIRED——页面自身明示该 context；产品定义变更时另议 |
| P2-003 | URL 上下文持久化不全 | DEFERRED——deep-link 优化，无错误金融结果证据 |
| P2-004 | Strategy 缺组合感知 | 仅改语义说明（建议非个性化账户 sizing）；不建 Portfolio Engine/OMS |

## 3. Evidence Log

（每个 finding 关闭时回填 Before → Change → Test → After 四段证据；禁止用 "Fixed/Improved/Refactored" 等空泛词作为完成证据。）
