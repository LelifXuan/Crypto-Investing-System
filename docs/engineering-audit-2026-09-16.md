# Crypto Research Terminal 工程规范审查报告

> 审查日期：2026-09-16
> 审查基线：[工程规范手册](engineering-guidelines.md) 与根目录 `AGENTS.md`
> 范围：领域模型、数据正确性、API/分层、SQLite 并发、缓存与快照、前端资产、测试/CI、仓库卫生

## 1. 结论

系统的研究、监控、策略与可视化链路已经具备较强的测试和回归防御，但距离“交易系统管理平台”的目标仍有一项结构性缺口：仓位、成交、订单、PnL 与复盘的核心领域尚未形成完整的 canonical model 和 API。现阶段更准确的定位是“加密资产研究与策略终端”，而不是已经闭环的交易管理系统。

本轮已完成两项低风险、高收益优化：

1. 将已识别的数据库写接口统一接入进程级 SQLite writer gate，锁覆盖依赖生命周期中的 flush、commit/rollback，移除 endpoint 内的显式 commit。
2. 删除两个未被引用的生产目录实验脚本 `me_test1.js`、`me_test2.js`，并增加静态门禁，避免实验资产再次进入生产页面目录。

## 2. 规范符合度矩阵

| 领域 | 状态 | 审查证据 | 处置 |
|---|---|---|---|
| 金额/价格精度 | 符合 | 持久化层使用 `ExactNumeric`/Decimal，未发现 SQLAlchemy `Float`/SQLite `REAL` 业务列 | 保持静态检查 |
| UTC 时间 | 符合 | 模型使用 timezone-aware DateTime，应用代码未发现 `datetime.utcnow()` 或无时区 `datetime.now()` | 保持静态检查 |
| SQLite 单写边界 | 已修复已知缺口 | bootstrap、indicator、market price/event、strategy、alerts 的写路径曾使用普通 session | 改用 `get_db_writer_session`；新增 AST 合同测试 |
| 冷缓存/市场风险分离 | 基本符合 | availability 与 market risk 已分离；Workbench 有 job、dedupe、轮询与 LKG 约束 | 继续以实例检查和专项合同测试保护 |
| API 与分层 | 部分符合 | 主要路径已按 endpoint/service/repository/schema 分层；少数服务和页面文件过大 | 列入拆分队列，不做一次性重构 |
| 交易事实 append-only | 未形成闭环 | 未发现 Fill/Order/Position canonical domain 与入账 API | P0：先补领域模型、幂等键和 migration |
| AVG_COST/FIFO | 未实现 | 未发现仓位成本引擎 | P0：与 Fill ledger 一并建设 |
| PnL 口径版本 | 未实现 | 未发现完整 PnL 输出模型与 metadata contract | P0：先定义 DTO/公式版本，再实现计算 |
| 市场数据 | 基本符合 | candle、mark、best bid/ask 等链路存在；live 同步会落库 | 已将可能落库的 GET 路径纳入 writer gate |
| 宏观数据源 | 部分符合 | fed、ism、agushuju、tushare、zhituapi 仍为显式 stub | 保留明确 unavailable/fallback，不伪造数据 |
| 前端生命周期/可访问性 | 基本符合 | 有 verify_pages、stress、a11y 与静态守卫 | 删除未引用实验资产；继续全量浏览器门禁 |
| CI/本地门禁 | 符合 | root CI、pre-commit、EditorConfig 与统一任务入口已建立 | 持续以 `python scripts/tasks.py ci` 为唯一入口 |
| 仓库卫生 | 已改善 | `source/runtime_python/` 已从索引移除并加入 ignore | Git 历史体积仍需独立、可回滚的清理方案 |

## 3. 本轮变更

### 3.1 SQLite writer gate 收口

以下会写数据库或在配置开启时可能写数据库的请求，统一使用 writer session：

- bootstrap seed；
- indicator calculate/refresh/query auto-calculate/policy upsert-delete；
- mark/candle create，以及 live mark/candle 同步；
- market event create/freeze/unfreeze；
- strategy shadow refresh/signal/snapshot；
- alert status update/alerts refresh。

同时移除了 freeze/unfreeze endpoint 内的 `session.commit()`。事务提交和异常 rollback 现在由同一个 writer dependency 负责，避免“repository 加锁、锁外 commit”的半保护状态。

### 3.2 生产静态资产清理

`app/static/pages/me_test1.js` 与 `me_test2.js` 没有路由、模板或模块引用，属于历史实验副本。删除后增加测试，禁止 `app/static/pages/*_test*.js` 回归。

## 4. 未解决风险与建议顺序

### P0：补齐交易管理核心

按最小闭环依次建设：

1. append-only Fill ledger，唯一键 `(source, account_id, fill_id)`；
2. Position projection，首版支持 AVG_COST 与 FIFO；
3. PnL DTO，固定输出 realized/unrealized/fees/funding/slippage/equity，并携带 formula/version metadata；
4. 多币种费用原币与报告币折算；
5. review 聚合（胜率、盈亏比、最大回撤、费用与品种贡献）。

这部分应拆成独立 migration、domain、repository、service、API 和测试提交，不宜混入本轮基础设施修复。

### P1：完成数据源与存储演进

- 为 5 个宏观 provider 分别定义授权、速率限制、字段契约、LKG 与 source_unavailable 验收标准；不要以空成功替代真实不可用状态。
- 多进程部署前迁移 PostgreSQL。当前 asyncio/threading writer gate 只保证单进程正确性。
- 为 Git 历史瘦身单独制定备份、协作窗口和 force-push 方案；本轮仅停止继续跟踪 runtime，未重写历史。

### P2：按变化率拆分热点

优先拆分 `terminal_summary_engine.py`、`indicator_monitoring.py`、`market_repository.py`，以及 `knowledge.js`、`btc_derivatives.js`、`analysis.js`。拆分目标应是缩小变化影响面和明确契约，不以行数下降作为唯一指标。

## 5. 验收标准

本报告中的“已修复”必须同时满足：Ruff、compile/语法检查、全量 pytest、全量 Playwright `verify_pages.py`、相关 stress test 全部通过；验证实例使用精简数据库、禁用 worker/warmup，并在验证后回收。

本轮最终结果：

- Ruff、compileall、全部 JavaScript `node --check`：通过；
- pre-commit `--all-files`：通过，且检查过程不改写工作区；
- pytest：`2085 passed, 4 skipped`；
- Playwright：11/11 页面冷启动、10/10 SPA 切换通过，console error/pageerror/HTTP 失败均为 0；
- deterministic fixture 压力测试：8 PASS、0 WARN、0 FAIL；
- 验证实例、精简数据库及 sidecar/cache 已回收，8002 端口恢复为空闲。
