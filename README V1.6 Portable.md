# Crypto Investing System V1.6 Portable

Crypto Investing System 是一套面向个人研究者的本地市场研究、风险监控与决策辅助系统。

系统以 BTC 和加密市场为核心，同时覆盖宏观日历、市场事件、技术指标、结构分析、策略推定、A 股 ETF 与黄金配置。它强调“证据、解释、数据质量和有限风险”，用于把分散的数据整理成可复核的研究页面，而不是替用户下单。

当前版本：`1.6.0`

## 重要声明

- 本系统不执行下单，不连接交易账户，不提供自动交易。
- 页面结论是研究辅助信息，不构成投资建议。
- 系统不推荐裸卖期权。
- Max Pain 用于观察期权持仓分布，不是价格预测。
- Call Wall、Put Wall 用于观察持仓集中区和潜在对冲敏感区，不是确定支撑或阻力。
- 比例价差不应被描述为安全对冲；系统的 Hedge Planner 只展示有限风险动作。
- 实际投资决策仍需结合个人资金、期限、风险承受能力和独立判断。

## 系统定位

这个项目解决的不是“预测下一根 K 线”，而是以下几类更实际的问题：

1. 当前宏观环境对风险资产是顺风、逆风还是相互冲突？
2. BTC 的价格、持仓量、资金费率和基差是否形成杠杆压力？
3. 期权 IV、Skew、Put/Call Ratio、Wall 与 Max Pain 正在如何迁移？
4. 多周期趋势、结构、动量和资金证据是否一致？
5. 现有观点的主要反证、失效条件和数据缺口是什么？
6. 当风险上升时，是否存在成本可控的有限风险保护方式？
7. 页面显示的数据来自哪里、何时更新、是否陈旧、是否只是降级结果？

因此，系统的核心输出不是单一“买入/卖出”按钮，而是：

- 当前市场状态；
- 支持多头和空头的证据；
- 相互冲突的证据；
- 关键风险与失效条件；
- 数据质量与来源；
- 可供比较的有限风险保护方案。

## 主要页面

| 页面 | 主要用途 |
| --- | --- |
| 监控总览 | 汇总宏观、技术、结构、策略与风险状态，形成可解释的市场简报 |
| 技术指标 | 查看多周期价格、趋势、动量、波动率与技术风险 |
| 形态结构 | 识别 HH/HL、LH/LL、BOS、CHOCH 和结构失效 |
| 市场事件 | 汇总交易所、监管、宏观及行业事件，并支持本地缓存 |
| 宏观日历 | 查看重要宏观发布、实际值、预期值、前值和事件窗口 |
| BTC 衍生品 | 查看永续、期货、期权、关键价位迁移及保护成本 |
| AI 策略 | 将多周期证据组织为观察、等待、风险阻断和条件式方案 |
| A 股 ETF | 维护 ETF 观察池、行情、分组与再平衡辅助信息 |
| 黄金配置 | 查看黄金市场状态、定投、回撤加仓和配置辅助信息 |
| 知识百科 | 解释指标、结构、衍生品术语和系统使用边界 |

## 核心能力

### 1. 监控总览与多空证据层

监控总览将多个页面的最近快照组织成统一摘要：

- 市场状态与主要矛盾；
- 多周期方向及冲突；
- 支持多头、削弱多头、支持空头、削弱空头的证据；
- 关键风险、失效条件和数据缺口；
- 宏观、结构、技术和策略来源引用。

页面读取优先使用缓存，不因打开页面而等待外部 API。需要更新时，由刷新工作流在后台执行。

### 2. 技术指标与结构分析

技术指标页覆盖：

- 多周期 K 线；
- EMA、RSI、MACD、ATR、布林带、CCI 等指标；
- 趋势、动量、波动率和背离；
- 局部风险提示与多周期一致性。

结构页覆盖：

- HH、HL、LH、LL；
- BOS 与 CHOCH；
- 关键结构位；
- 当前结构方向、置信度和失效条件。

### 3. 宏观与事件研究

宏观模块将利率、通胀、增长、就业、流动性、美元、实际利率和跨资产指标分层展示。

主要能力包括：

- 宏观日历；
- 数据发布窗口；
- 实际值与预期差；
- 分层宏观评分；
- 数据新鲜度和来源状态；
- 缓存读取与稳定降级。

市场事件页用于补充交易所、政策、监管和行业事件。空缓存时页面保持可用，不会在首屏自动发起长时间外部同步；用户可主动刷新。

## BTC 衍生品市场

V1.6 的 BTC 衍生品页由六张决策型主图组成：

1. 价格、持仓与资金费率压力；
2. 交易所杠杆拥挤快照；
3. IV 与基差期限结构；
4. 行权价表面：Call/Put OI、IV 与关键参考位；
5. Call Wall、Put Wall、Max Pain 与 Spot 的历史迁移；
6. 期权情绪与保护成本历史。

### 数据源

系统接入六个无需私钥的公开市场数据源：

- Deribit；
- OKX；
- Bybit；
- Binance Futures；
- Bitget；
- Hyperliquid。

期权主链优先级为：

```text
Deribit → OKX → Bybit
```

Wall、Max Pain、IV Smile 等指标使用单个可用主链计算，不把不同交易所的期权 OI 直接相加。其他期权源用于覆盖率、质量和价位交叉验证。

永续与期货数据保留 provider 维度，并进一步计算：

- Funding median 与 dispersion；
- USD OI 总量、分布与变化；
- Price/OI regime；
- Basis 与 annualized basis。

### Constant Maturity

关键价位历史默认使用 60D Constant Maturity。

系统从未来有效到期日中选择最接近 30D、60D 或 90D 目标期限的合约。来源到期日变化时会明确记录 rollover，不平滑或隐藏跳变。

行权价表面和原始期权链则使用用户当前选择的到期日。

### 关键价位

页面解释以下四类信息：

- Call Wall：Call OI 较集中的行权价区域；
- Put Wall：Put OI 较集中的行权价区域；
- Max Pain：根据当前期权持仓计算的到期支付最小化参考点；
- Constant Maturity：保持近似剩余期限的历史跟踪方法。

这些指标用于观察持仓和对冲结构，不被描述为确定预测。

### 有限风险 Hedge Planner

Hedge Planner 可比较：

- 买入保护性 Put；
- 买入保护性 Call；
- Put Debit Spread；
- Call Debit Spread；
- 降低网格或现货敞口；
- 暂不对冲并继续观察。

结果会结合 IV、流动性、关键价位和保护预算，但不会生成订单，也不会推荐裸卖期权。

## 数据质量与降级原则

BTC 衍生品运行时只使用真实公开数据。

状态分为：

- 实时：本次采集成功；
- 最近真实缓存：实时采集失败，但存在 15 分钟内的真实快照；
- 数据不足：没有可用实时数据，也没有符合时限的真实缓存。

Fixture 只用于自动化测试，不参与运行时回退。

每张图表可携带：

- providers；
- primary provider；
- updated time；
- requested/actual/maximum window；
- data points；
- quality；
- missing reason。

Provider 的地区限制、`403`、`451`、限流或结构漂移只会降低相应数据能力，不应被解释成市场信号。

## 异步刷新工作流

页面 GET 负责读取最近缓存，不等待外部数据源。

刷新流程为：

1. 前端提交刷新请求；
2. 服务返回 HTTP `202` 和刷新任务回执；
3. 相同任务在队列中去重；
4. 前端轮询 `/api/v1/refresh-jobs/{job_id}`；
5. 任务成功后重新读取缓存；
6. 任务失败时保留页面当前可用状态。

刷新任务状态写入独立 SQLite 文件，终态可在应用重启后继续查询；重启时未完成任务会被标记为中断。

诊断和 smoke 场景仍可使用 `wait=true` 同步等待。

## 数据存储

### 主数据库

SQLite 保存：

- 市场与指标数据；
- 页面快照和计算缓存；
- 策略与监控结果；
- 刷新任务状态；
- 衍生品分区索引、行数、大小和校验信息。

### 衍生品分区归档

高频衍生品历史使用 gzip JSONL 分区：

```text
runtime/data/derivatives_archive/
  archive_index.sqlite3
  provider/
    BTC/
      data_type/
        YYYY/
          MM/
            DD/
              HHMMSS-hash.jsonl.gz
```

存储策略包括：

- 内容哈希去重；
- provider、标的和数据类型作用域；
- 临时文件写入后原子替换；
- 文件成功后事务登记索引；
- 过期清理；
- oldest-cold-first 配额治理；
- 孤立文件和索引恢复入口。

默认保留期：

| 数据 | 保留期 |
| --- | --- |
| 主期权链 15 分钟快照 | 7 天 |
| 高频永续快照 | 7 天 |
| 小时级压缩快照 | 90 天 |
| Wall、Max Pain、Funding、OI、保护成本等日级指标 | 400 天 |

默认归档上限为 5 GiB：

```env
BTC_DERIVATIVES_ARCHIVE_QUOTA_BYTES=5368709120
```

Latest 文件和受保护的日级指标不会作为普通冷分区直接删除。

## 系统架构

```text
Browser UI
  │
  ├─ 页面缓存读取
  ├─ 异步刷新任务
  └─ 数据质量与来源展示
  │
FastAPI
  │
  ├─ API endpoints
  ├─ schemas
  ├─ domain services
  ├─ provider adapters
  ├─ normalizers / collectors
  └─ background worker
  │
Storage
  ├─ SQLite
  ├─ raw/normalized latest
  ├─ gzip JSONL partitions
  └─ logs / cache / tmp
```

主要源码目录：

```text
trading-system-codex/
  app/
    api/
    schemas/
    services/
    static/
    templates/
    workers/
  tests/
  scripts/
  tools/
  docs/
```

## Portable 版本

Portable 版本面向 Windows win-x64，内置 Python 3.11 运行时。

目标机器无需安装 Python。

主要文件：

```text
TradingSystemPortable/
  TradingSystemLauncher.exe
  start_portable.bat
  app/
  scripts/
  runtime_env/python/
  runtime/
  README_PORTABLE.md
  release_manifest.json
```

### 启动

推荐双击：

```text
TradingSystemLauncher.exe
```

诊断启动：

```text
start_portable.bat
```

默认访问地址：

```text
http://127.0.0.1:8000/
```

### Portable 运行时目录

```text
runtime/
  config/
  data/
  cache/
  logs/
  tmp/
```

其中：

- `runtime/config/` 保存本地配置、JWT 和管理员凭据；
- `runtime/data/` 保存数据库和衍生品归档；
- `runtime/cache/` 与 `runtime/tmp/` 可重建；
- `runtime/logs/` 保存启动、运行和审查日志。

## 安全升级与同步

同步命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_portable_local.ps1
```

流程包括：

1. 构建到独立 staging；
2. 运行严格 verifier 和 preflight；
3. 拒绝覆盖正在运行的 Portable；
4. 备份原配置、数据库和用户文件；
5. 清理 cache/tmp，并归档日志；
6. 同步程序文件；
7. 合并原运行时数据；
8. 将数据库路径重写为目标 Portable 自身目录；
9. 使用 embedded Python 启动同步后的实例；
10. 运行 Playwright 页面审查；
11. 审查通过后完成切换，失败则回滚。

可用参数：

```powershell
-Destination <path>
-SkipBuild
-SkipBrowserAudit
-ResetRuntime
-WhatIf
```

`-ResetRuntime` 会清空原运行时状态，只应在明确需要全新安装时使用。

同步报告：

```text
trading-system-codex/reports/portable_sync_v16.json
```

## Portable Playwright 发布验收

发布验收针对同步后的真实 `TradingSystemPortable`，不使用源码服务器代替。

审查实例由以下解释器启动：

```text
TradingSystemPortable/runtime_env/python/python.exe
```

自动检查：

- 十个主要页面；
- 1440、1280、768、390px 四个视口；
- 页面身份与真实内容；
- console error 与 page error；
- 失败 HTTP 响应；
- 横向溢出；
- BTC 六图、风险模式和异步刷新；
- 静态资源、模板与 vendor 文件；
- Portable 数据库路径；
- 重启后配置与数据保持；
- 外部 provider 不可用时的稳定降级。

输出：

```text
trading-system-codex/reports/portable_playwright_v16.json
trading-system-codex/reports/portable_playwright_screenshots/
```

统一发布命令：

```powershell
python scripts/tasks.py release-v16
```

## 源码开发

### 环境要求

- Windows；
- Python 3.11 或 3.14；
- Node.js，用于 JavaScript 语法检查；
- 推荐将虚拟环境放在源码树外。

### 快速开始

```powershell
py -3.11 -m venv ..\runtime_dev\.venv
..\runtime_dev\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python scripts/tasks.py install
python scripts/tasks.py dev-local
```

开发地址：

```text
http://127.0.0.1:8002/
```

源码模式运行数据默认位于：

```text
..\runtime_dev\source_runtime
```

避免把数据库、日志、缓存和本地密钥提交到源码仓库。

## 常用开发命令

```powershell
python scripts/tasks.py test
python scripts/tasks.py lint
python scripts/tasks.py check
python scripts/tasks.py build-portable
python scripts/tasks.py portable-preflight
python scripts/tasks.py release-v16
```

单独运行：

```powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q app tests scripts
python scripts/audit_redundant_workflows.py
```

## API 概览

主要 API 前缀：

```text
/api/v1
```

BTC 衍生品：

```text
GET  /api/v1/btc-derivatives/dashboard
POST /api/v1/btc-derivatives/dashboard/refresh
GET  /api/v1/btc-derivatives/live/snapshot
POST /api/v1/btc-derivatives/live/refresh
GET  /api/v1/btc-derivatives/sources/status
POST /api/v1/btc-derivatives/sources/probe
GET  /api/v1/refresh-jobs/{job_id}
```

健康检查：

```text
/health
/health/live
/health/ready
```

默认 Portable 配置关闭公开 OpenAPI 文档；源码开发模式可按本地配置启用。

## 配置与密钥

源码模式使用：

```text
.env
```

Portable 使用：

```text
runtime/config/portable.env
```

升级时保留：

- JWT secret；
- 管理员用户名和密码；
- 数据库；
- 用户导入和导出文件；
- 自定义配置。

不要把 API Key、JWT、管理员凭据或包含个人数据的运行时文件提交到 GitHub。

## 故障排查

### Portable 无法启动

1. 运行 `start_portable.bat`；
2. 检查 `runtime/logs/portable_console.log`；
3. 检查 `runtime/logs/portable_startup_diagnostics.log`；
4. 确认 `runtime_env/python/python.exe` 存在；
5. 确认目标目录没有被安全软件隔离。

### 同步提示实例仍在运行

关闭 Portable 窗口，并确认没有从目标目录启动的 `python.exe` 或 Launcher 进程。

同步脚本不会直接删除正在运行的目标目录。

### 页面显示数据不足

这通常表示：

- 外部 provider 当前不可访问；
- 地区限制返回 `403/451`；
- 请求被限流；
- 尚未积累真实快照；
- 本地没有 15 分钟内的真实缓存。

可在 BTC 衍生品页打开“数据源状态”，或使用“一键探测数据源”查看具体 provider。

### 归档空间过大

优先调整归档配额或等待维护任务清理过期高频分区。

不要直接删除 `archive_index.sqlite3`。如需手工处理，先关闭应用并完整备份 `runtime/data/derivatives_archive/`。

### 浏览器验收失败

查看：

```text
reports/portable_playwright_v16.json
reports/portable_playwright_screenshots/
```

报告会记录具体页面、视口、console error、page error、失败响应和溢出状态。

## 验证基线

V1.6.0 当前验证结果：

```text
pytest: 747 passed, 6 skipped
Ruff: passed
Python compile: passed
JavaScript syntax: passed
Portable strict verifier: passed
Portable Playwright: 40/40 page-viewports passed
```

发布产物必须满足：

- `release_manifest.json` 版本为 `1.6.0`；
- embedded runtime 不是 stub；
- Portable 不依赖系统 Python；
- 数据库写入 Portable 自身 `runtime/data`；
- 无绝对开发路径；
- 浏览器审查零关键错误。

## V1.6 相比 V1.5 的主要演进

V1.6 不是单独的“衍生品插件”，而是一次系统级升级：

- 新增 BTC 衍生品决策页面和六个公开数据源；
- 引入异步刷新任务与缓存优先页面工作流；
- 引入可扩展的衍生品分区归档；
- 加强数据质量、来源和降级状态展示；
- 取消空缓存页面的隐式长时间外部刷新；
- 加固 Portable 构建、同步、路径、备份和回滚；
- 将同步后 Portable 的 Playwright 实例审查设为发布门槛。

## License 与贡献

如需公开发布，请在仓库中补充明确的 License、贡献指南和安全披露方式。

提交变更前至少运行：

```powershell
python scripts/tasks.py check
```

涉及页面、发布或 Portable 的变更，还应完成真实实例 Playwright 验收。
