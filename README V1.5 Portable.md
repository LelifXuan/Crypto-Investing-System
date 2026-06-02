# Crypto Investing System V1.5 Portable

本项目是一个**本地优先、可解释、可离线降级**的加密市场研究、宏观监控、形态结构识别与策略辅助系统。

V1.5 Portable 面向 Windows win-x64 用户，目标是：用户从 GitHub 下载压缩包后，解压即可运行；不要求提前安装 Python，不要求手动安装依赖，也不要求用户必须配置全部第三方 API Key。

> 本 README 面向完成 V1.5 构建后的发布版本。如果当前代码尚未合并 V1.5 修复，请先执行 `docs/RELEASE.md` 中的 V1.5 验收清单。

---

## 重要声明

本系统只用于市场研究、数据监控、策略复盘和决策辅助，不构成任何投资建议，也不是自动交易执行系统。加密资产和相关风险资产波动极高，任何模型、指标、形态识别、宏观评分或 AI 策略输出都可能失效。

系统输出应被理解为：

- 对已有数据的结构化整理；
- 对市场状态的辅助性描述；
- 对多空条件、风险因素和缺失输入的提示；
- 不保证未来收益，也不替代人工判断。

请结合自身风险承受能力独立决策。

---

## V1.5 版本定位

V1.5 在 V1.4.1 Portable 基础上的**监控总览解释闭环升级版**。

本版本重点解决以下问题：

1. 监控总览页三卡片不能解释页面结论与其他页面的脱节；
2. 终端摘要不是交易决策语言（缺方向结论、缺触发条件、缺失效条件）；
3. 监控总览未复用 alerts bundle（筹码结构 / 背离风险 / final decision）；
4. 监控总览未消费 4h / 1d / 1w 多周期一致性证据；
5. 决策摘要无快照，无法复盘"当时判断 vs 后续价格"；
6. P2 风险：AlertsBundleRead 字段缺失、divergence 路径分叉、chip-structure 缓存时间戳错配、strategy lower_tf_missing 假阴性。

一句话概括：

```text
V1.5 = V1.4.1 Portable
     + decision_brief_v1 (市场情况 / 交易指引 / 风险点与失效条件)
     + 多周期冲突矩阵 (6 行 evidence_strength)
     + 决策快照持久化 (ComputedDatasetCache / 24h TTL)
     + 4 项 P2 风险修复
     + 行尾规范化 (.gitattributes)
```

---

## V1.5 新增能力

### 1. 监控总览三行决策简报

终端摘要不再是 `主要矛盾 / 策略含义 / 观察条件` 三卡片，而是新的三行：

| 行 | Key | 用途 |
|---|---|---|
| 市场情况 | `market_situation` | 多周期趋势、动量、筹码、背离、结构证据汇总 |
| 交易指引 | `trading_guidance` | 触发条件、仓位上限、止损/止盈参考，条件式表达 |
| 风险点 / 失效条件 | `risk_invalidation` | 关键均线/VWAP/结构边界反向确认、gates 失败、数据缺口 |

每行都带 `tone`（bullish / bearish / neutral / warning）和 `evidence_strength`（0-1）。
当 `evidence_strength < 0.5` 时该行 `tone` 自动降级为 `warning`，并在 `summary` 前缀
"证据强度 N%，结论置信度有限"——避免用户在数据不充分时被虚假结论误导。

### 2. 多周期冲突矩阵

`terminal_summary.decision_brief.source_alignment.matrix` 始终包含 6 行固定顺序的证据行：

```
1w_trend      (背景 regime)
1d_bias       (主战 bias)
4h_trigger    (执行 readiness)
chip_structure (筹码压力 / 支撑)
divergence_summary (动量背离)
strategy_gates (策略风控门槛)
```

每行带 `direction` / `weight` / `evidence_strength`。
当 `4h vs 1d vs 1w` 方向冲突，或 `terminal_summary.bias` / `strategy.bias` /
`chip_structure.direction` / `divergence.overall.tone` 出现对立时，
`consistency` 自动标为 `conflict`，交易指引降级为"等待确认"。

### 3. 决策快照持久化

每次 `MonitoringDashboardService.refresh_bundle` 完成后，决策简报会 best-effort
写入 `ComputedDatasetCache` 表（`dataset_type=monitoring_decision_brief`，24h TTL）。
历史快照可通过以下 endpoint 读取：

```http
GET /monitoring/decision-brief/history?instrument_id=btc-usdt-perp&timeframe=1d&limit=20
```

返回结果含 `consistency` 字段，便于复盘筛选。

### 4. 跨页快照复用

监控总览页不再独立造结论，而是只读读取：

- `alerts_bundle_cache_key` → 筹码结构、背离风险、final decision
- `strategy_bundle_cache_key` → AI 策略页准入、触发器、gates
- `analysis_cache_key` → 4h / 1d / 1w analysis bundle 摘要

`StrategySnapshotBuilder` 完成时 best-effort 写入 `strategy_bundle_cache_key`，
避免与 `MonitoringDashboardService` 形成循环刷新。

### 5. P2 风险修复

| 问题 | 修复 |
|---|---|
| `AlertsBundleRead.contract_snapshot` 字段缺失 | schema 补字段 |
| `/alerts/divergence` 未复用 `indicator_matrix` | endpoint 改为先取 matrix 再计算 |
| `/alerts/chip-structure` 缓存 key 用 1h candle ts | 改用请求 timeframe 自己的 ts，v2→v3 强制旧 key 失效 |
| `StrategySnapshotBuilder.lower_tf_missing` 假阴性 | 改为基于 `data_quality_score` 真检查 |

### 6. 行尾规范化

仓库根目录新增 `.gitattributes`：

- 源代码（`*.py` / `*.js` / `*.css` / `*.md` / `*.json` / `*.yaml` / `*.toml`）→ LF
- Windows 脚本（`*.bat` / `*.ps1` / `*.cmd`）→ CRLF
- Shell（`*.sh`）→ LF
- 二进制（`*.png` / `*.zip` / `*.exe` / `*.pyd` / `*.db` 等）→ 不转换

设置 `core.autocrlf=false` + `git add --renormalize` 一次完成 109 个历史文件的
CRLF→LF 转换。Windows 脚本仍保留 CRLF 以保证 `start_portable.bat` / `start_source.bat`
能直接双击运行。

---

## 核心能力

### 1. 本地 Portable 运行

- 内置运行环境：通过 `runtime_env/` 携带嵌入式 Python 和依赖；
- 用户运行态隔离：运行日志、缓存、配置统一进入 `runtime/`；
- 升级友好：升级时通常保留 `runtime/`，替换其它程序文件即可；
- 适合普通用户下载、解压、双击启动。

### 2. 宏观数据监控

系统围绕加密资产和美股风险资产的相关性，重点监控美国宏观、利率、流动性、信用、美元、原油、黄金和风险资产代理指标。

宏观数据源包括但不限于：

| 类型 | 主要用途 | 示例 |
|---|---|---|
| FRED | 利率、信用、美元、流动性、通胀 fallback | DFF、DGS10、BAMLH0A0HYM2、CPIAUCSL |
| BLS | CPI、核心 CPI、就业、失业率 | CPI、Core CPI、NFP、Unemployment Rate |
| BEA | GDP、PCE 等宏观数据 backup | NIPA 表 |
| Treasury | 美债利率曲线 | 3M、2Y、10Y |
| Gate.io / RWA | 可交易风险资产与商品代理 | XAUT、WTI、SPY、QQQ 等可用标的 |
| CoinMarketCap | 加密市场结构类指标 | BTC dominance 等 |
| A 股 ETF 数据源 | 现金流 ETF、HALO ETF 价格观察 | 159201 及 HALO ETF 组合 |

宏观指标采用统一状态输出：

```text
indicator_key / value / unit / latest_date / source / source_ref / status / cache_origin / cache_age_days / is_scored
```

### 3. 监控总览页解释闭环

监控总览页是终端用户的"第一入口"。V1.5 把它从"独立摘要生成器"升级为"跨页汇总只读视图"：

- 读取 `alerts_bundle` 的 `chip_structure` / `divergence_summary` / `final_decision`
- 读取 `strategy_bundle` 的 `decision` / `gates` / `no_trade_reasons`
- 读取 4h / 1d / 1w analysis bundle 摘要
- 与本页面 1d 技术观测对齐
- 输出 `decision_brief` 三行 + 多周期冲突矩阵 + evidence_strength

缺失数据不再显示为"中性"，而是显示：

```text
未计分：缺少有效观测值 / provider 不可用 / 缓存过期 / 配置无效
```

### 4. 宏观缓存与离线降级

宏观数据通常是日度、周度、月度或季度更新，变化频率低、数据量小、时效窗口长。
因此系统支持三层缓存策略：

```text
运行期缓存 → 内置种子缓存 → live 数据源 → 缺失/降级状态
```

当 BLS、CoinMarketCap 等受网络或代理影响的数据源不可用时，只要缓存仍在有效窗口内，
页面仍可展示 last-good 数据，并明确标记缓存来源。

### 5. 多页面数据复用

V1.5 要求同一批已抓取或已计算的数据被多个页面复用，避免页面切换时重复请求外部 API 或重复计算。

推荐工作流：

```text
后台刷新服务：负责抓取和更新缓存
页面服务：只读缓存和计算结果
监控总览：读取统一 macro snapshot + alerts/strategy bundles + 多周期 analysis
宏观明细：读取统一 macro snapshot
AI 策略：复用 macro snapshot、技术指标、结构识别结果 + 监控决策简报
```

页面请求不应直接触发慢速外部 API。需要刷新时，页面只投递刷新任务，由后台 worker 执行。

### 6. 监控总评分原则

V1.5 推荐将评分逻辑从代码硬编码迁移到：

```text
app/monitoring/configs/macro_scoring_registry.v1.json
```

总览页判定原则：

```text
score >= 65  → 偏多
score <= 35  → 偏空
其它         → 中性
缺有效数据    → 未计分，不参与层级均值
```

新增：决策简报三行（市场情况 / 交易指引 / 风险失效）独立于总分，三行各自的
`evidence_strength` 和 `tone` 由多周期冲突矩阵和来源数据质量决定。

---

## 目录结构

```text
CryptoInvestingSystem/
├─ TradingSystemLauncher.exe          # 推荐启动入口
├─ start_portable.bat                 # 调试启动入口
├─ README V1.5 Portable.md             # 本文件
├─ app/                               # 应用源码
│  ├─ monitoring/configs/             # 指标池、数据源、刷新策略、评分注册表
│  ├─ services/                       # 数据服务、宏观服务、策略服务、缓存服务
│  │  └─ monitoring_decision_review.py # 决策快照复盘 read path
│  ├─ static/                         # 前端静态资源
│  └─ assets/seed_cache/              # 随包发布的只读宏观种子缓存
├─ runtime_env/                       # 不可变运行环境：嵌入式 Python 与依赖
├─ runtime/                           # 用户本地运行状态，升级时建议保留
│  ├─ config/portable.env             # 用户本地配置
│  ├─ config/proxy.detected.json      # 自动代理检测结果，不含密码
│  ├─ cache/                          # 用户运行期缓存
│  └─ logs/                           # 本地运行日志
├─ scripts/                           # 审计、打包、维护脚本
├─ tests/                             # 单元测试和集成测试
├─ docs/                              # 文档（CHANGELOG / OPERATIONS / RELEASE / CACHE_ARCHITECTURE）
├─ .gitattributes                     # 行尾策略（新增）
└─ README.md
```

发布包中不应包含：

```text
.env
.env.*
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
logs/
runtime/logs/
runtime/cache/
*.db-journal
*.db-wal
*.db-shm
旧版本临时报告
开发机本地数据库
```

---

## 启动方式

### 推荐方式

```text
双击 TradingSystemLauncher.exe
```

### 调试方式

```text
双击 start_portable.bat
```

启动成功后浏览器会打开本地页面，默认地址通常为：

```text
http://127.0.0.1:8000/strategy-page
```

如端口被占用，请修改：

```text
runtime/config/portable.env
```

示例：

```env
APP_PORT=8000
```

### 源码开发模式

```powershell
py -3.14 -m venv ..\runtime_dev\.venv
..\runtime_dev\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/tasks.py dev-local
```

源码模式默认端口 `8002`，带热重载；详见 `docs/OPERATIONS.md`。

---

## 代理自动发现

默认启用代理自动发现：

```env
APP_PROXY_MODE=auto
PROXY_AUTO_DETECT_ENABLED=true
```

系统会按以下顺序检测：

1. `APP_PROXY_URL`；
2. `HTTPS_PROXY / HTTP_PROXY / ALL_PROXY`；
3. 上次检测结果 `runtime/config/proxy.detected.json`；
4. Windows 系统代理；
5. WinHTTP 代理；
6. 常见本地代理端口，如 `127.0.0.1:7890`、`127.0.0.1:7897`、`127.0.0.1:10809`。

如果没有开启 VPN 或代理，系统不应整体失败。默认只有以下 live 数据源可能受影响：

```text
BLS
CoinMarketCap
```

若存在内置缓存或运行期缓存，宏观页应继续展示缓存数据，并明确标记数据状态。

代理检测结果文件：

```text
runtime/config/proxy.detected.json
```

该文件不得保存代理密码、完整鉴权 URL 或 API Key。

---

## API Key 配置

真实 API Key 只能写入用户本地配置或系统环境变量，不得写入源码仓库、发布包、日志、缓存、healthcheck 返回体或前端响应。

用户本地配置文件：

```text
runtime/config/portable.env
```

可配置：

```env
FRED_API_KEY=
BLS_API_KEY=
BEA_API_KEY=
COINMARKETCAP_API_KEY=
GATEIO_API_KEY=
GATEIO_API_SECRET=
TIINGO_API_KEY=
TWELVEDATA_API_KEY=
ALPHA_VANTAGE_API_KEY=
OPENEXCHANGERATES_APP_ID=
```

没有 API Key 时，系统应：

1. 标记 provider 为 `auth_missing` 或 `optional_auth_missing`；
2. 尝试 public fallback、运行期缓存或内置种子缓存；
3. 不应崩溃；
4. 不应把缺失数据写成 0；
5. 不应让宏观监控总览整页空白。

---

## 主要页面

| 页面 | 作用 | 数据复用要求 |
|---|---|---|
| 监控总览 | 查看关键市场指标、层级得分、多空偏向、缺失输入和风险提示 | 读取统一 macro snapshot、技术指标快照、alerts/strategy bundles、4h-1d-1w analysis |
| 技术分析 | 查看 K 线、核心指标、衍生指标与基础趋势判断 | 输出指标快照，供 AI 策略和总览页复用 |
| 形态结构 | 识别 swing、箱体、三角形、楔形、颈线和关键价位 | 输出结构快照，供策略页复用 |
| 告警中心 | 聚合结构、指标、背离、风险和事件类告警 | 复用各模块标准化 alert payload |
| AI 策略 | 生成倾向、条件、止损止盈、置信度和缺失输入说明 | 不重复计算，读取缓存快照 + 监控决策简报 |
| 决策复盘 | 历史 decision_brief 快照列表 | 通过 `/monitoring/decision-brief/history` 读取 |
| 宏观与事件 | 展示指标池、数据源状态、缓存状态、宏观事件和翻译状态 | 读取宏观服务统一结果 |
| A 股 ETF | 展示现金流 ETF 与 HALO ETF 价格 | 读取独立 ETF 数据缓存 |
| 知识百科 | 整理指标、形态、风控、ETF 和交易术语说明 | 与页面标签和解释文案保持一致 |

---

## 监控总览 V1.5 评分原则

V1.5 推荐将评分逻辑从代码硬编码迁移到：

```text
app/monitoring/configs/macro_scoring_registry.v1.json
```

每个指标应声明：

```json
{
  "indicator_key": "us_10y_yield",
  "aliases": ["us10y_yield", "ust_10y_yield"],
  "formula_id": "inverse_linear",
  "formula_text": "score = 100 - clamp((value - 2.5) / (6.0 - 2.5)) * 100",
  "unit": "%",
  "thresholds": {"low": 2.5, "high": 6.0},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "利率压力缓和",
  "bearish_label": "利率压力偏强",
  "neutral_label": "利率压力中性"
}
```

总览页判定原则：

```text
score >= 65  → 偏多
score <= 35  → 偏空
其它         → 中性
缺有效数据    → 未计分，不参与层级均值
```

层级得分应显示数据完整度：

```text
layer_score / layer_weight / scored_count / missing_count / completeness
```

当数据完整度过低时，最终操作倾向应降级为：

```text
观察 / 数据不足 / 等待刷新
```

V1.5 在传统总分基础上增加 **决策简报三行**（`decision_brief`）：

- `市场情况` — 多周期趋势、动量、筹码、背离、结构证据汇总
- `交易指引` — 触发条件、仓位上限、止损/止盈参考，**条件式表达**
- `风险点 / 失效条件` — 关键均线/VWAP/结构边界反向确认、gates 失败、数据缺口

每行带 `evidence_strength`（0-1）和 `tone`（bullish / bearish / neutral / warning）。
当 `evidence_strength < 0.5` 时该行 `tone` 自动降级为 `warning`。

---

## 数据状态说明

| 状态 | 含义 | 是否计分 |
|---|---|---|
| `live` | 来自实时或最新外部数据源 | 是 |
| `cache_fresh` | 来自运行期缓存，仍在新鲜度窗口内 | 是 |
| `seed_cache_fresh` | 来自随包种子缓存，仍在新鲜度窗口内 | 是 |
| `stale` | 有历史值但超过新鲜度窗口 | 否，除非配置允许 |
| `auth_missing` | 缺少必要 API Key | 否 |
| `network_error` | 网络不可达或代理不可用 | 否 |
| `invalid_config` | source_key、table、line、frequency 等配置不完整 | 否 |
| `source_unavailable` | provider 可用但该标的或指标不可用 | 否 |
| `parse_error` | 响应存在但字段或日期解析失败 | 否 |
| `not_scored` | 指标仅展示或当前无有效评分规则 | 否 |
| `aligned` | 决策简报一致性：所有来源方向一致且无缺失 | 是（决策简报） |
| `mixed` | 决策简报一致性：来源方向混合但无直接对立 | 是（决策简报） |
| `conflict` | 决策简报一致性：出现明确的多空方向对立 | 否，强制降级 |
| `degraded` | 决策简报一致性：任一必需来源缺失 | 否，强制降级 |

---

## 故障排查

优先查看：

```text
runtime/logs/portable_console.log
runtime/logs/portable_startup_diagnostics.log
runtime/config/proxy.detected.json
runtime/cache/macro_api/cache.sqlite
```

常见情况：

| 现象 | 说明 | 处理 |
|---|---|---|
| BLS / CMC live 不可用 | 未检测到代理、网络不可达或 key 缺失 | 开启 VPN，或继续使用缓存数据 |
| FRED official 不可用但页面有值 | public CSV fallback 或缓存生效 | 正常降级，查看 source_ref |
| 宏观页显示 stale | 缓存超过新鲜度窗口 | 开启网络后手动刷新或等待后台刷新 |
| BEA 指标 invalid_config | source_key 缺少 table/line/frequency | 检查 `macro_indicator_api_map` |
| gold / RWA 不显示 | Gate.io provider 路由或交易对不可用 | 检查 `gateio_rwa` 配置和 symbol |
| 总览页大量中性 | 可能是旧 key 未命中或缺数据被误处理 | 运行宏观审计脚本 |
| 决策简报显示 `degraded` | 必需来源缺失 | 等待缓存预热或运行后台预计算 |
| 决策简报显示 `conflict` | 多源方向冲突 | 等待更高级别证据一致后再做决策 |
| 决策简报 tone=warning | evidence_strength < 0.5 | 阅读 summary 前缀的"证据强度"提示 |
| 页面切换卡顿 | 可能存在重复外部请求或缓存写竞争 | 检查后台 worker 和 SQLite WAL |
| 日志出现 `database is locked` | SQLite 并发写入冲突 | 启用 WAL、busy_timeout 和原子 upsert |
| git 操作出现 CRLF 警告 | 历史文件未规范化 | 已通过 V1.5 `.gitattributes` 处理，验证 `git ls-files --eol` |

---

## 开发与审计命令

建议在项目根目录执行：

```bash
python scripts/audit_release_integrity.py --fail-on-critical
python scripts/audit_macro_coverage.py
python opencode_macro_monitoring_audit.py --repo . --json-out reports/macro_monitoring_audit.json
pytest tests/test_macro_api_sources.py
pytest tests/test_macro_coverage_audit.py
pytest tests/test_macro_never_empty.py
pytest tests/test_macro_provider_contracts.py
pytest tests/test_macro_scoring_registry.py
```

V1.5 专项：

```bash
pytest tests/test_terminal_summary_engine.py
pytest tests/test_monitoring_dashboard_summary_sources.py
pytest tests/test_monitoring_decision_review.py
pytest tests/test_monitoring_frontend_static.py
pytest tests/test_monitoring_decision_brief_matrix.py
```

发布前至少确认：

1. 宏观指标 key 全部可 canonicalize；
2. provider alias 全部可路由；
3. 缺数据不会被当成 50 分中性；
4. 监控总览每个指标都能解释公式、阈值和判定原因；
5. 页面切换不触发重复外部 API；
6. 决策简报三行渲染正确，证据强度联动 tone；
7. 多周期冲突矩阵 6 行方向 / weight / evidence_strength 全部填充；
8. 决策快照 endpoint `/monitoring/decision-brief/history` 可查询历史；
9. 发布包不包含 `.env`、日志、运行缓存、开发机本地数据库或 Python 缓存。

---

## 升级说明

从 V1.4.1 升级到 V1.5 时，推荐：

1. 备份旧版 `runtime/`；
2. 替换应用程序文件、`app/`、`scripts/`、`tests/`、`docs/` 和配置模板；
3. 保留用户本地配置：`runtime/config/portable.env`；
4. 首次启动后检查 `runtime/logs/portable_startup_diagnostics.log`；
5. 在宏观与事件页面检查每个 provider 的状态；
6. 在监控总览页检查公式解释与缺失数据提示；
7. （可选）访问 `GET /monitoring/decision-brief/history` 复盘历史决策。

如发现宏观页仍然为空，应优先确认：

```text
indicator key 是否命中 canonical alias
provider 是否注册成功
source_key 是否完整
是否存在可用 last-good cache
缺失数据是否被错误写成 0
```

如发现监控总览页 decision_brief 异常：

```text
source_alignment.consistency 是否合理
matrix 6 行的 evidence_strength 是否正常
row.evidence_strength 是否在 0-1 之间
是否触发了 tone=warning 降级
```

---

## 版本关键词

```text
Portable
Macro Data Reliability
Explainable Monitoring
Canonical Indicator Keys
Provider Fallback
Cache First
Last Good Observation
Not Scored Instead of Fake Neutral
SQLite WAL
Release Hygiene
Decision Brief
Multi-Period Conflict Matrix
Evidence Strength
Decision Snapshot
```

