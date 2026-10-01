# CHANGELOG

## V2.3.1（当前源码版本，2026-09-30）

- 应用、API、Python 包、启动脚本、示例配置与 portable 清单统一更新至 `2.3.1` / `V2.3.1`；内部包继续原样内嵌本地 `source/.env`（其中 `APP_VERSION` 同步更新）。
- AI 策略矩阵中已发布但未通过交易门槛的“无机会”单元现可打开各自周期的抽拉页，复核多空评分、执行周期证据和未通过原因；未发布单元仍不可打开，未晋级单元不进入交易机会排序，也不提供可执行价位。
- 市场事件信息流去除重复的右侧 Inspector，统一事件卡 hover 反馈；沿用本批次的发布快照身份核对、URL 恢复及便携包内嵌配置契约。
- 发布门禁：全量 `pytest` **2268 passed、9 skipped、0 failed**；维护范围 Ruff、Python `compileall` 通过；隔离实例 Playwright **11/11 冷启动、10/10 SPA 切换**，AI 策略压力测试 **2 PASS / 0 FAIL**，`/openapi.json` 报告 `2.3.1`。
- Windows 私有便携包：`dist/CIS-UI2-V2.3.1-PRIVATE-20260930.zip`，内嵌本地 `source/.env` 与 Python 运行时；同目录 `.zip.sha256` 为整包校验值。该包仅供授权内部使用。

## V2.3（上一源码批次，文档更新至 2026-09-30）

- 2026-09-30 市场事件页移除重复的右侧 Inspector，信息流改用完整内容宽度；关联品种保留在事件卡内，正文不再截断。普通与冻结事件卡采用相同的 hover 表面、边框和阴影反馈。

- 2026-09-30 发布快照回放：以真实发布的 BTC 衍生品信号翻转核对 ETH、BNB、HYPE、OKB 决策不变，并复核监控、矩阵、详情的统一策略快照身份；记录见 `docs/remediation/PUBLISHED_SNAPSHOT_REPLAY_20260930.md`。
- 2026-09-30 策略机会身份：扫描单元携带来源快照键，详情换代时重新读取矩阵；扫描内部 `fresh_until` 统一使用缓存 TTL；URL 可恢复仍有效的品种×周期机会。界面明确杠杆为未计账户资金与已有持仓的模型参考值。

- 2026-09-30 审计后便携包契约修正：所有内部 portable 构建均要求并原样内嵌非空 `source/.env`；缺失即构建失败。校验器核对清单摘要，解压检查允许精确的 `source/.env`，其他凭证文件照常拒绝。同步启动提示与包内说明，去除“无密钥包”的错误文案。此前审计报告验证的是默认无密钥模式，不能作为内嵌模式通过的证据；新增不含真实密钥的归档回归测试覆盖内嵌、缺失、摘要不符及额外凭证四种情况。
- 2026-09-30 该修正的门禁：维护范围 Ruff、Python `compileall` 通过；全量 `pytest` **2282 passed、4 skipped、0 failed**；隔离实例 Playwright **11/11 冷启动、10/10 SPA 切换**。本地完整 portable 的归档扫描、结构、`.env` 摘要、解压及临时解压目录清理均通过；验证产物已清理。

- AI 策略扫描口径收紧：15 格是独立扫描单元，只有本周期方向、下一级执行价位、交易周期目标、盈亏比、杠杆预算与开仓许可全部通过时才展示交易机会；未晋级单元不再以“做多/做空＋等待确认”列出。已计算的“无机会”仍可打开抽拉页查看该周期证据与拒绝原因，不展示可执行交易计划。后台新增 1H 策略 bundle 独立周期刷新，并定期补齐 4H/日线/周线 bundle；bundle 发布后再排队重算统一快照，扫描仍只投影已发布结果。

- 2026-09-30 同步用户说明与现行设计契约：15 格始终表示扫描位置，不能写成 15 笔已成立机会；未通过完整门槛的研究倾向不显示多空方向、不进入排名，但可打开详情复核。数据尚未齐备与已完成计算但无机会分别显示，避免把后台依赖问题误称为市场结论。已有后台进程需重启才能加载新的周期刷新计划。

> 本批次产品与 UI 版本为 **V2.3**；应用、API 与 Python 包版本为 **2.3.0**。本节保留当时的源码记录，不追溯改写旧包的版本或验收结果。`dist/` 中 2026-08-31 的 V2.3 ZIP 是应用 `1.8.1` 的历史内部验收包，不能以该 ZIP 代替后续交付。

### 纳入范围

- 延续 2026-08-31 的六页 Workbench 迁移基线、Operator Core 与 Strategy Detail Panel 的 ADR 0023 边界；ETF、Gold、Knowledge 的页面范围仍按[设计手册](docs/design-guidelines.md)执行。
- 纳入 2026-09-23 前 V2.2 维护线的策略矩阵、战术价位、杠杆 sizing、黄金策略、数据预热与缓存治理改动；详细变更保留在下方 V2.2 历史记录。
- 收敛市场事件日历与信息流、知识库 hero、监控明细卡的垂直间距；修复两组 Node 子进程测试在 Windows GBK 环境读取 UTF-8 输出时的解码失败。
- 2026-09-28 修复监控总览读取卡顿：监控快照和宏观概览 GET 改走只读会话，技术指标缺失时由后台任务补齐，避免页面读取排队等待 SQLite 写锁或同步重建分析；浏览器门禁识别 AI 策略矩阵全部等待数据时的明确可用性状态。
- 2026-09-28 AI 策略扫描与页面访问解耦：移除页面挂载预热与每日首次访问预热；普通 `GET /strategy/scan` 只读后台发布的快照，不再因输入更新时间变化而同步重算。后台独立定时投影已发布的 unified 快照，页面轮询直接读取新版本；过期结果保留并标注为旧快照，同时禁用交易信号。缩减周期任务生产速度，避免预计算队列长期积压。
- 2026-09-28 修复跨页多空判定根因：形态融合分数实际为 `-1..1`，策略曾误按百分制使用，令 `+0.19` 变成 `0.19` 多头对 `99.81` 空头；现在统一转换量纲。策略与市场上下文按行情原始时间戳择取有效价格，五天前的 mark 不再覆盖当天 K 线。监控全局方向由后台已发布的同周期统一策略判断生成，技术面作为证据保留；撤除页面上的系统冲突提示和扫描结果的跨页过滤。
- 修复移动端使用指南空格键偶发不展开：在按钮 `keydown` 直接完成单次切换，避免导航焦点管理吞掉浏览器延迟派发的 click。
- 机会扫描拒绝入场价与止损价重合或止损落在入场区间内的计划：该单元不晋级、不进入排序，旧缓存卡片也不再展示无效止损价位。
- 2026-09-29 过渡修复：抽屉先按所点周期显示方向、评分和证据；扫描刷新改为只投影已发布快照，避免未发布临时结果与详情错位。该版仍依赖每品种一份统一交易决策，已由下条独立周期决策取代。
- 2026-09-29 按实际交易级别重建 AI 策略：每个品种分别生成周线、日线、4H 三份机会决策，5 个核心品种对应 15 个独立 `instrument×timeframe` 详情。执行周期固定为周线→日线、日线→4H、4H→1H。低一级 K 线负责入场与首目标，交易周期结构负责止损和持仓目标；分别计算首目标与交易目标盈亏比、预期波幅，并按止损距离、ATR 和周期上限独立计算杠杆。矩阵、排名与抽屉均从已发布快照里的对应周期决策投影，不再把品种级日线决策当成三个周期的交易许可。执行价位缺失、止损方向错误、盈亏比不足或风险门禁阻断时不发布可执行价位；旧快照缺少周期决策则进入后台重算状态。品种级统一决策继续供监控总览使用，不覆盖独立周期机会。
- 修复旧版 `/strategy/bundle` 在冷缓存时的响应校验 500：置信度尚未观测时允许 `null`，保留“数据准备中、仅观察”语义；补充接口回归测试。
- 同步 README、启动脚本、Python 包、API 默认版本、`.env.example` 与内部便携包 manifest 的版本口径。旧验收文档中的 `1.8.1` 保留为当时的实际版本。

### 2026-09-30 系统完整性整改（Integrity Remediation，P0×2 + P1×3）

- **P0-SEC-001 → 按所有者决定调整（2026-09-30）**：所有者确认 `.env` 密钥均为其为本分发单独创建，明文嵌入内部便携包系授权设计，原「分发秘钥隔离」 finding 与轮换要求撤回。保留工程成果：构建器默认不含 `.env`，并带构建前后两道 fail-closed secret scan 门禁（凭证类文件名 + 高风险变量非占位值即构建失败并删除产物；`runtime_python/` 内 stdlib `secrets.py` 与 certifi 公共 CA 束路径受限豁免）；所有者可用 `--embed-local-env` 显式嵌入本地 `.env`（豁免精确到该文件，其余照扫，manifest 记录 `embeds_local_env`），校验脚本对应 `--allow-embedded-env`；`verify_portable_package.py` 提供档案扫描 + 结构 + 可选解压核验（临时目录 try/verify/finally，cleanup 失败显式上报）。`.env.example` 示例值保持显式 `CHANGE_ME` 占位。
- **P0-QNT-001 跨资产信号隔离**：`ModuleSignal` 增加 `instrument_id`/`asset_scope`（exact/proxy/global/unknown），删除 `btc_perp` 危险默认值，未知作用域 fail closed；`DirectionResolutionEngine.resolve` 接收 `target_instrument_id` 并在加权前执行资格门禁——exact 不匹配、proxy、unknown 一律不参与方向计算，也不得向操作卡注入他资产绝对价位（BTC 期权墙/Max Pain 不再进入非 BTC 价位体系）；生产信号全部显式声明归属（价格结构/技术指标=exact 本资产，宏观/资金流/链上=global，衍生品=BTC 数据）；非 BTC 页面将 BTC 衍生品显式标注为「BTC 市场代理上下文，不参与本资产方向判定」；risk gate 的衍生品降级警告仅对 BTC 生效。BTC 自身衍生品证据链路保持不变（positive control 测试钉住）。
- **P1-QNT-002 资金流数据契约**：修复 `CapitalFlowEngine` 对链上指标 dict payload 的错误读取（原 isinstance 数值检查使结构化信号成为死代码）；新增共享读取器 `onchain/metric_reader.py`（按指标级 freshness 与质量门禁 fail closed）；`OnchainFeatureEngine` 由真实观测历史派生 ~1d/~7d 变化特征；资金流方向只消费变化量——绝对正 level（稳定币总量、DEX 成交额）不再等于流入；历史深度不足如实输出 `DATA_INSUFFICIENT`，不伪造 delta。
- **P1-SEM-001 证据质量语义**：策略评分在 UI 统一呈现为「证据质量 N/100」（不再用「置信度 N%」），并附「衡量数据新鲜度、证据覆盖与信号一致性，不代表预测胜率或盈利概率」说明；`ScanItem` 与决策审计 payload 增加 `confidence_kind="evidence_quality"`、`confidence_is_probability=false` 语义字段；矩阵门禁文案改「证据质量未达门槛」；知识库词条更名并声明非校准概率。
- **P1-STATE-001 Shell 健康真实化**：侧栏页脚的静态「系统在线」改为双 chip——`服务` 状态轮询 `/health`（ready/降级/不可达/未知），`数据` 状态来自 api.js 真实请求成败计数（与服务健康独立）；两 chip 初始均为「未知」，无观测证据不给绿色；请求失败显式显示服务不可达。

整改证据、逐项 Before/After 与不变量（INV-001..005）登记见 `docs/remediation/`。P2 项（fresh_until 语义、Monitoring BTC/1D scope、URL 持久化、组合感知）按整改指令登记 DEFERRED，未扩大范围。

### 验证与交付状态

- 2026-09-30 完整性整改门禁：隔离实例（精简验证库 + `WORKER_PROFILE=none`）全量 `pytest` **2276 passed、4 skipped、0 failed**；整改范围 Ruff 与 `compileall` 通过；Playwright **11/11 冷启动、10/10 SPA 切换**（0 pageerror），AI 策略压力测试 **2 PASS / 0 FAIL**；无密钥默认模式便携包 `verify_portable_package.py` 全 PASS + 启动冒烟 `/health/live → 200`（所有者授权分发可另用 `--embed-local-env` 构建并 `--allow-embedded-env` 校验）。验证后专用实例已关闭、精简库已删除。逐项证据见 `docs/remediation/CIS_SYSTEM_INTEGRITY_REMEDIATION_REPORT.md`。

### 验证与交付状态

- 2026-09-29 完整机会门槛最终验证：全量 `pytest` **2240 passed、4 skipped、0 failed**，维护范围 Ruff、Python `compileall` 与改动 JS 语法检查通过；Playwright **11/11 冷启动、10/10 SPA 切换**，AI 策略压力测试 **2 PASS / 0 FAIL**。隔离实例中 ETH 4H 虽有方向倾向，但 1H 执行结果为 `NO_EDGE`，不生成入场计划；页面因此不发布该交易机会。该精简库的 15 格均未通过完整门槛，排序区为空，验证实例和精简库已清理。本条为当前行为验证，前述“做多/等待确认/做空”的 2026-09-29 中途记录仅描述当时状态。
- 2026-09-26 同版门禁：`pytest` **2220 passed、4 skipped**；维护范围 Ruff 0 错、Python `compileall` 通过；Playwright **11/11 冷启动、10/10 SPA 切换**，无页面错误；运行实例 `/openapi.json` 的版本为 `2.3.0`。
- 2026-09-28 监控性能修复门禁：`pytest` **2221 passed、4 skipped**；维护范围 Ruff 与 Python `compileall` 通过；Playwright **11/11 冷启动、10/10 SPA 切换**，监控压力测试 **1 PASS / 0 FAIL**。隔离实例中监控快照读取约 **15–43 ms**，宏观概览读取约 **5–7 ms**；实际耗时仍取决于运行库和后台负载。
- 2026-09-28 策略扫描解耦门禁：`pytest` **2220 passed、4 skipped**，维护范围 Ruff 与 Python `compileall` 通过；隔离实例 Playwright **11/11 冷启动、10/10 SPA 切换**，AI 策略压力测试 **2 PASS / 0 FAIL**。后台发布器在精简库写出 **11 品种、33 单元**，普通扫描 GET 读取约 **37 ms**；该耗时仅代表隔离实例。
- 2026-09-28 前轮隔离实例门禁：全量 `pytest` **2215 passed、15 skipped、0 failed**；维护范围 Ruff、Python `compileall`、改动 JS 语法检查均通过；Playwright **11/11 冷启动、10/10 SPA 切换**，AI 策略与监控压力测试 **3 PASS / 0 FAIL**。该轮仅定位到方向差异，本轮已继续修复量纲与价格时效；下方测试记录以本轮最终验证为准。
- 2026-09-28 多空判定修复最终门禁：隔离实例全量 `pytest` **2218 passed、15 skipped、0 failed**；维护范围 Ruff、Python `compileall` 与改动 JS 语法检查通过；Playwright **11/11 冷启动、10/10 SPA 切换**，固定数据下 AI 策略与监控压力测试 **3 PASS / 0 FAIL**。精简库市场上下文读取 BTC 当日价格 `83389.8`，不再选用五天前的 `85843.2`；原策略快照离线复算从偏空转为无明确优势。当时真实数据下手动强制刷新仍需等待全量重算，已在 2026-09-29 修复。
- 2026-09-29 周期详情与扫描同源门禁：全量 `pytest` **2229 passed、4 skipped、0 failed**，维护范围 Ruff、Python `compileall` 与改动 JS 语法检查通过；Playwright **11/11 冷启动、10/10 SPA 切换**，真实扫描压力测试 **2 PASS / 0 FAIL**。隔离实例点击 HYPE 周线、日线、4H 后，矩阵与抽屉分别为做多、等待确认、做空；强制扫描读取已发布统一策略，未晋级单元不含执行价位。验证后已关闭专用实例并移除本轮精简数据库。
- 本次未生成新的 V2.3 便携包；重建时需使用当前源码，重新运行包内预检并生成新的校验值。历史 ZIP 的哈希与内容保持不变。

## V2.2（上一正式版，2026-09-23 增补）

> 历史版本口径：V2.2 基线为 2026-08-27（commit `38932ee`）；本节汇总基线之后到 `f205c35` 的演进，当时均记在 V2.2 名下。当时应用运行版本为 `1.8.1`。下方 2026-08-31 的 V2.3 内部验收记录属于另一份历史交付，不代表当前源码包。

### AI 策略页（9-22 十问题修复 + 9-23 跟进）

- 机会矩阵口径统一：非 fresh 格只报"数据准备中 / 数据更新中"，不再把"没数据"说成"没机会"；有方向但未过门禁的格显示方向 + 中性说明，stale 格显示旧方向（last-known-good）。
- 抽屉（详情面板）有界自动刷新（5 秒 × 9 次）+ 常驻"重新推演"按钮；轮询 bypass 客户端 30 秒缓存；force 扫描超时放宽到 240 秒。
- 计划"出生即死"修复：结构入场位必须距现价 ≤ 3 ATR（`entry_max_distance_atr`，`market_strategy_signal_config_v17.json`）且止损不被现价穿过，否则退回现价相对入场；价格溯源只用本周期 mark / 收盘 / 库内最新标记价，不再取 structure 包 K 线尾；ATR 后备止盈与 `min_rr_trade: 1.5` 对齐。
- 矩阵格盈亏比只用本格几何，不再借用 4h 交易计划的决策级 RR；ranked 摘要跳过 bundle 校验行"策略价位无效"；ranked 卡片标扫描年龄（`served_at`）。
- live-scan：scan 行比 unified 输入旧时就地重算（`source=live`）；策略页每 60 秒静默刷新（`scanned_at` 变化才重绘，切后台暂停，卸载清理）。
- `/strategy/bundle` 毒行隔离：快照改写 `strategy_snapshot:*` 独立 key，端点对非决策行同步重建（此前 46/66 行缺 `strategy_state`，读到即 500）。
- 矩阵方向格统一底色：候选 / 过期 / 过门禁共享牛熊色，门禁只用虚线边框 + 小字区分。
- ranked 卡片改点位行：`做空 区间｜止损｜止盈`（与抽屉战术计划同源），缺失隐藏，TP1 缺失不再显示"止盈 0"。

### 黄金配置页

- VEGAS 通道短轨改用 EMA12（原误用收盘价）；金额单位读 `portfolio.base_currency`（USD 不再显示"元"）；空金额显示"—"（`Number(null)===0` 防护）。
- 新增策略写入路径：`POST /gold/policy`（版本追加、Decimal 全链路）+ 页内策略表单（保存即新版本、自动刷新）；空态指引不再指向不存在的流程；`decimal_string` 去 18 位小数填充。

### 预热队列与缓存治理

- 单 hint 只刷所要周期（不再六栈扇出）；FAST/SLOW 计划裁剪 related 连带；新增队列预算守卫（FAST 周期任务数上限）。
- `display_only` 指标不计入宏观置信度分母（`fed_operations` 展示型指标不再把整页置信度钉在 low）；宏观总分与偏差口径不变。

### 前端清理

- 技术指标页移除已弃用的上下文横栏（删除 `ui/contextRail.js`）与"数据已就绪"噪音横幅；A股 ETF 页移除多余的"执行计划已生成"横栏；衍生品行权价图表标签碰撞避让（`resolveReferenceLineX` + 参考线标签布局守卫）。

### UI 审计与设计收敛

- P1（手机单列 / 抽屉 / 结构 SVG / 报价 stale 语义 / ETF 待态）与 P2（审计详情脱术语 / 成交量整数轴 / 冷启动骨架占位 / 44px 触屏命中）清偿；`editorial.css` 为 token 唯一权威；响应式断点 17→6；治理底栏共享化。

### 工程门禁

- Ruff 5101 → 0（vendor 排除 + auto-fix + 手工清偿 + per-file-ignores 豁免）；pre-commit 加强 + AGENTS.md §六.6 Lint 门禁；`runtime_python/` 取消跟踪（5283 文件）；price-lag 五件套（mark 新鲜度 helper / 600s 丢弃 WS 残值 / WS 断开清缓存 / stale 阈值对齐 15s / 守卫单测）。

### 验证记录（2026-09-23）

- `pytest tests/ -q`：**2200 passed, 4 skipped, 0 failed**；`ruff check app/ tests/ scripts/`：All checks passed。
- `verify_pages.py`：冷启动 11/11、SPA 切换 10/10，0 pageerror；`stress_test.py`：策略页 2 PASS（全量偶发 LOADING_STUCK 单页重跑通过）。

## V2.3 内部验收记录（2026-08-31，历史包）

> 本节保留 08-31 内部 hygiene 验证包的原始记录（见 `dist/` 下 ZIP 与 `.verification.json`）。它在当时不是正式版，应用版本为 `1.8.1`；当前源码版本见本文开头。

- 发布卫生补验：2013 passed、4 既有 skip、0 warnings；11/11 冷启动、10/10 SPA、8/8 压力通过。指南 `[hidden]` 恢复真实隐藏语义；FAB 三页三视口操作链替换旧 Knowledge skip。
- 增加 `pytest --acceptance` 后端预检与禁止缺后端 skip 的守卫；修复六个测试脚本入口导入、旧 Pydantic/JWT 测试警告和手册测试的固定字符窗口。本轮修复文件 Ruff 为 0，项目遗留降至 221；第三方源码未改。
- 筹码结构无数据极端风险、legacy 权限与 freshness 的消费链已审计，业务语义留待专项修复。Hygiene 便携包单独校验，不覆盖原包；人工敏感副本清理状态见交付记录。

- UI 发布版本 V2.3 与应用运行版本 1.8.1 分开记录；不改变后端接口或市场计算。
- 保留 P1 四页及 P2 Operator Core：Command Palette、Inspector pin/resize、URL selection recovery 与浮层协调。
- H0 改为 HTML/静态子模块协商缓存，旧版首次升级需 Ctrl+Shift+R；命令错误保留内部 cause，控制台仅输出脱敏诊断。
- H0–H4 与最终同版软件门禁通过：1986 passed、6 既有 skip、5 warnings；11 个冷启动路由、10 个 SPA 页面及 8 个压力场景通过，详见迁移验收记录。
- Structure 统一 click/PointerEvent 的 CSS 像素坐标，避免打开 Inspector 后静止鼠标误切 preview；静态图表 surface 不再继承卡片 hover 上浮。
- 未落库标记价沿用既有临时报价 `mark_id=0` 标识，修复响应序列化 500；不新增 DTO、数据库写入或 provider 请求。
- 压力测试覆盖同上下文刷新忙碌态，六页及 Strategy 使用确定性真实字段 fixture；包的独立验证结果由 ZIP SHA-256 绑定的外部验收记录提供。
- 内部便携包包含 Python、依赖及授权的原样 `.env`，未加密；不是公开发行包。

## V2.2 (2026-08-25)

### 波动率研究与影子验证

- 新增 BTC 原生波动率研究层，覆盖 realized volatility、range estimator、经验分位、IV–RV、期限结构、skew、basis、funding、OI 与清算压力等候选族。
- 新增 append-only 波动率观测与版本化研究快照，金额、价格和比率保持 Decimal/numeric，时间戳统一为 UTC，并记录 `event_time`、`available_at`、`calculated_at`、数据质量与缺失原因。
- 研究候选默认使用 `shadow / diagnostic_only / rejected` 状态；未通过时间戳、稳定性和增量价值门禁前，不参与 canonical decision、仓位、杠杆或方向判断。
- 修正将 `BB Width / 90 日均值` 表述为 percentile rank 的语义问题，明确区分均值比率与 rolling empirical percentile。

### 数据抓取、网络与缓存治理

- 统一 direct/proxy 请求路径、代理探测、超时和错误状态，外部 API 不可达时保留 last-known-good 或返回明确的 `source_unavailable / data_insufficient`。
- 补强冷启动预热、后台刷新、防重入、writer queue 与 SQLite 事务边界，避免空结果覆盖有效快照及并发写锁竞争。
- 增加外部市场数据重置与重新抓取工具，支持在不保留旧行情缓存的情况下重新验证数据链路。

### 首次加载与动效衔接

- 全局 stagger 调整为 28ms 间隔、最多 6 个相位；真实内容从较高透明度和 3px 位移开始衔接，避免 skeleton 替换时闪白。
- skeleton shimmer 使用基于全局时钟的负相位，蜡烛、文本条和事件行首次出现即形成完整错峰波形。
- 技术指标、形态结构、市场事件、BTC 衍生品、A股 ETF 与黄金配置页均在异步数据真正落地后执行一次性 reveal。
- 黄金配置页新增醒目的“正在接入黄金配置数据”加载面板，BTC 衍生品等待 Chart.js 绘制完成后入场，ETF 曲线与业务内容分别衔接且后续交互不重放整页动画。
- `prefers-reduced-motion` 下直接呈现稳定终态，并清理临时动画状态与合成层。

### 分发与验证

- V2.2 内部分发包包含内置 Python 运行环境、依赖和当前 `.env` 配置；运行数据库、日志、缓存、测试截图及 Git 元数据不进入压缩包。
- 全量验证结果：`1793 passed, 6 skipped`；Playwright 冷启动 11/11、SPA 切换 10/10，console error 与 pageerror 均为 0。
- 动效专项检查无失败；保留 4 项历史硬编码时长警告，未影响本次页面交接。

### 安全提示

- V2.2 压缩包包含密钥和代理配置，只允许通过可信渠道发送给授权同事，不得上传至公开仓库或公开共享链接。

## Unreleased (2026-07-30)

### 全站自定义 Dropdown 统一

- **前端**: 新建 `app/static/ui/dropdown.js`,导出 `mountDropdown(root, options) -> { setValue, destroy, refresh }`,替换全站 6 个页面 21 处原生 `<select>`(analysis × 2、structure × 5、knowledge × 4、btc-derivatives × 8、ashare-etf × 1、market-events × 1)
- **设计**: 控件主体 40px / 圆角 12 / 冷白半透明;弹层 item 44px;Click 展开 + Click 选中(零误触);固定 280px max-height + 8px fade-out;视觉态用现有 token,内嵌 SVG icon,不引入新颜色,不引入 backdrop-filter
- **键盘**: Tab 焦点(3px 青绿 focus-ring)/ Enter|Space|↓ 展开 / ↑↓ Home End 移动焦点 / Enter 选中 / Esc 关闭 / Type-ahead 输入字母跳转(前缀优先,短 buffer 退化为 substring 匹配,适配中英混合 label)
- **a11y**: ARIA listbox / role=option / aria-selected / aria-haspopup / aria-expanded / aria-controls
- **样式**: 新增 `.dropdown-*` 命名空间;沿用现有 :root token,不引入新颜色;不放 backdrop-filter;z-index 1000
- **btc-derivatives 表单兼容**: chart toolbar + hedge form 各放 hidden `<input type="hidden" name="...">`,dropdown onChange 写入 hidden,FormData 读取不变(避免改动现有 form submit 流程)
- **测试**: 新增 `tests/test_dropdown_component.py`(CSS 契约 5 项 + size 变体 + 颜色 token 约束) + `tests/test_no_native_select_remaining.py`(页面 JS 静态守卫 12 项);Playwright 烟雾测试 3 个文件,覆盖 cold-load + 键盘交互 + Esc 关闭 + Type-ahead
- **验证**: 19 个测试全部 PASS(改动范围 0 fail);Playwright 全 6 页 cold + 1 个交互用例,0 console error / 0 page error;`node --check` 7 个 JS 文件全部通过

## Unreleased (2026-07-29)

### SQLite 冷启动并发与页面超时治理（2026-07-30）

- SQLite 写路径统一进入支持优先级、FIFO、取消安全与同任务重入的单写协调器；锁覆盖写入、flush、commit/rollback 完整事务，PostgreSQL 自动旁路。
- candle upsert 在 SQLite 下按 400 行短事务分批提交，批间释放 writer slot，允许交互刷新优先插队；复合幂等键保证失败后可安全重试。
- precompute 在 SQLite 下强制单并发，启动预热按 BTC、ETH、HYPE、BNB、OKB 串行入队并等待完成；周期扫描增加启动宽限、积压退让及近过期过滤。
- Workbench 六周期依赖在 SQLite 下串行读取，PostgreSQL 保持并发 3；纯读 session 退出时 rollback/close，readiness 使用 1 秒内部 deadline。
- `stale_revalidating` 且存在 last-known-good 时立即渲染旧快照并后台刷新；只有 `queued/running` 冷启动壳同步展示进度，避免页面等待刷新任务超时。
- 健康检查新增兼容性的 SQLite writer 队列诊断；业务 API 契约、旧 Workbench/缓存接口和独立 `refresh_jobs.sqlite3` 保持不变。
- 验证：`1363 passed, 7 skipped`；Playwright 11/11 冷启动、10/10 SPA 切换通过；改动范围 Ruff、Python 编译及改动 JS 语法检查通过。

### AI 策略 Workbench 冷启动闭环

- `StrategyWorkbenchRead` 升级至 `3.0.0`，新增 `build_state`、`system_availability`、`last_known_good`、`progress` 与 `source_manifest_hash`。构建中不再伪造方向、市场风险或 `0.00` 价格。
- 冷缓存 `GET /api/v1/strategy/workbench` 现在直接创建带 instrument dedupe key 的 targeted refresh job；相同资产并发请求复用同一任务。
- 新增 `StrategyWorkbenchBuildCoordinator`：检查六周期依赖、使用独立 session 与并发上限 3、合成 canonical decision、应用供给门禁并原子发布 Workbench。
- 过期缓存保留完整 last-known-good，返回 `stale_revalidating` 并收紧新增仓位权限；不再用空 `DATA_BLOCKED` 内容覆盖旧分析。
- `RefreshReceipt` 增加 phase、进度、message 与 error code；前端共享 `waitForRefreshJob()` 会自动轮询、成功后 bypass 客户端缓存重读，面板关闭时通过 AbortController 中断。
- 策略统一加载器改为只读领域快照；缺少依赖时返回 dependency gap，不再在请求合成阶段同步执行六次 uncached rebuild。

### HYPE 供给事件与解锁风险

- 新增通用 `supply_events` 模块，包含 contracts、Tokenomist/Hyperliquid providers、reconciler、snapshot builder、risk engine 与 history study。
- 供给状态固定为 `SCHEDULED / COMMITTED / CLAIMED / UNSTAKING / SELLABLE / ABSORBED / EXPIRED`，计划量、承诺量、实际领取、解质押、可售量和已吸收量分别记录。
- 只有可售供给、交易所或做市商流入、主动卖压、衍生品多头拥挤及结构破位同时成立，供给证据才允许贡献 `BEARISH`；计划或单纯领取保持 `NEUTRAL`。
- 供给门禁只允许收紧仓位、杠杆及交易权限，不能放宽 canonical decision，也不能仅凭计划解锁生成做空方向。
- 新增 `/api/v1/supply-events/snapshot`、`calendar`、`history-study` 与 `refresh`。缺少 Tokenomist/Nansen Key 或 verified 地址时返回明确 `source_unavailable`，不生成模拟事实。
- 历史研究按事件锚点输出 T-7 至 T+30 的描述性窗口；样本不足时固定为 `insufficient_sample`，不输出概率。

### 数据模型、SQLite 与前端

- Migration `0013_hype_supply_events` 新增 append-only domain snapshot、供给事件快照及未来日历节点；金额和数量使用 Numeric/Decimal，时间统一 UTC。
- 新增进程内单写协调器。page cache、领域快照、策略审计和黄金 OI 的写锁覆盖完整 commit/rollback 边界，避免“锁只包 flush、commit 已出锁”的伪串行。
- AI 详情页在执行计划后增加“供给事件与解锁风险”卡；市场作战图增加 `supply_event_regime` 第六维。
- Crypto 市场事件页增加未来供给日历、节点类型筛选和明确空态。
- 策略 SPA 冷启动使用可识别的 warming shell，避免通用 loading class 让页面实例检查误判为未完成。

### 验证

- Alembic 隔离升级和运行库版本均为 `0013_hype_supply_events`。
- 全量 pytest：`1349 passed, 7 skipped`。
- 完整 Playwright：11/11 冷启动、10/10 SPA 切换通过，HTTP、console error 与 pageerror 均为 0。
- Hyperliquid direct/proxy 均返回 200；Tokenomist 无 Key 时 direct/proxy 均明确返回 401。
- 最新验证日志中 `database is locked=0`、`PendingRollback=0`。
- 参考审计脚本结果：0 个 P0、0 个 P1。

### 已知限制

- 当前未配置 Tokenomist/Nansen 凭据，也没有 verified HYPE 地址，因此生产结果使用真实适配器的明确降级路径；不会猜测地址或伪造解锁事实。
- 当前供给事件历史样本不足，不自动晋级研究阈值。
- 仓库全量 Ruff 仍有历史遗留问题；本次改动范围 Ruff 已全部通过。

## v1.8.1 (2026-07-28)

### 通道多边形左边缘扩展到历史 pivot

- **后端**：`app/services/structure/classic.py` 的 `detect_channels` 改为贪心扩展历史 pivot 窗口：在已有 4 个最新 pivot 的拟合基础上，向左逐一加入更老的 pivot 并重做线性回归，只要上下边界的 mean error 都仍在 `tol * 2.0` 之内就保留。`left_idx = min(hs[0].index, ls[0].index)` 现在反映真实通道起点，而不是固定截断到第 4 根 pivot。
- **测试**：`tests/test_classic_pattern_detection.py::test_channel_polygon_left_edge_includes_older_pivots_in_tolerance` 用 10 根 pivot 的水平通道验证 `region.points[0].index ≤ 12`，而旧逻辑会落在 56 附近。
- **验证**：`tests/test_classic_pattern_detection.py` 9 passed、`tests/test_structure*.py` 27 passed。

### 保护规划表单现价输入 step='any'

- **前端**：`app/static/pages/btc_derivatives.js` 在 `<input name="spot_price">` 上增加 `step="any"`。`hedge_context.spot_price` 是浮点数（如 65226.17），HTML5 `<input type="number">` 默认 step=1 会触发"请输入有效值。两个最接近的有效值分别为 N 和 M"原生校验提示，让用户误以为系统导入的现价是错误的。
- **测试**：`tests/test_btc_hedge_form_input_step.py` 静态守卫：`name="spot_price"` 输入必须包含 `step="any"`。
- **验证**：`tests/test_btc_derivatives_*` 29 passed。

### 期限矩阵 wall cell 视觉权重分层

- **前端**：`app/static/styles.css` 新增 `.btc-wall-cell` 基础样式 + `.is-effective` / `.is-insufficient` 两个变体。有效墙（`$60,000` 等）字号 16px / ink 色 / 青绿 border-top / 单点·集群百分比用 accent 色；未形成有效墙字号 13px / muted 色 / dashed border / 整体 opacity 0.86，显著弱化。
- **测试**：`tests/test_btc_maturity_wall_visual_weight.py` 静态守卫 3 个：两类选择器都存在、`<b>` 字号差 ≥ 2px、insufficient 必须有 opacity / dashed / muted 之一。
- **验证**：`tests/test_btc_derivatives_*` 31 passed。

### 关键行权价迁移图叠加标准到期日 marker

- **前端**：`app/static/ui/charts.js` 新增 `expiryAnchors` Chart.js 插件；`key_levels_history` 图表配置注入每个标准到期日（4D / 32D / 60D / 151D / 242D / 333D 等）的 marker：垂直虚线 + 3 个圆点（PUT WALL / MAX PAIN / CALL WALL）。让用户在一张图上同时看到 180D 历史 + 期限矩阵 6 行快照。
- **前端**：`app/static/pages/btc_derivatives.js` 新增 `buildMaturityExpiryAnchors(labels)`，从 `dashboard.options.maturity_ladder` 派生 anchor 列表，按 chart x 轴格式（epoch ms / ISO）自适应转换到期日。
- **后端**：`app/services/btc_derivatives/chart_builder.py` 把 `key_levels_history` 的 `span: 6` 改为 `span: 12`，使其在期权结构段单独占满整行，避免和 `options_risk_premium_history` 挤在同一半。
- **测试**：`tests/test_btc_derivatives_chart_expiry_anchors.py` 静态守卫 3 个：插件存在、`maturity_ladder` 被读、`key_levels_history` 配置使用 overlay。
- **验证**：`tests/test_btc_derivatives_*` 38 passed。

### BTC 衍生品证据大卡片 4×2 统一网格

- **前端**：`app/static/pages/btc_derivatives.js` 把"衍生品状态"4 张子项和"推理"4 张子项合并到同一个 `.btc-evidence-grid`（4 列 × 2 行，`grid-auto-rows: 1fr`），共享 `.btc-evidence-tile` 容器，消除原本两行之间的大段空白。
- **设计**：删除原 `.btc-decision-card` 旧包装；衍生品状态子项现在使用与推理子项完全一致的容器与 chip（kind chip + 置信度 chip + 标题 + 影响），并通过新增的 `judgementTone()` 把 `stateLabel` 映射到 bull/bear/neutral 配色。
- **测试**：`tests/test_btc_evidence_grid_unified.py` 静态守卫 4 个：使用统一网格、衍生品子项使用 `.btc-evidence-tile`、CSS 包含 `grid-auto-rows: 1fr` + `repeat(4`、CSS 定义 `.btc-evidence-tile`。
- **验证**：Playwright 实测 8 张子卡等高 304.3px，证据层高度从 ~1100px 降到 750px（-32%），0 console error / 0 page error。

### 结构图"已确认"chip 方向色

- **前端**：`app/static/pages/structure.js` 新增 `chipToneForDirection()` 工具函数，把系统方向（`bullish` / `weak_bullish` / `bearish` / `weak_bearish` / 其它）映射到现有 `.chip-bullish` / `.chip-bearish` / `.chip-neutral` CSS class。右侧 system 卡片（摆动结构 / 经典图形 / 成交量·市场轮廓）标题区"已确认"chip 改为随方向着色。
- **测试**：`tests/test_structure_status_chip_tone.py` 静态守卫 3 个：函数存在、映射规则正确、system 卡片调用点使用派生 class。
- **验证**：`tests/test_structure*.py` 全量 40 passed。

### 形态结构图表延伸到最新 K 线

- **前端**：`app/static/pages/structure.js` 的 `shouldExtendToLatest` 新增 `pattern_region` 与 `region` 角色；`extendOverlayToLatestCandle` 新增 polygon 右角延伸分支，把经典形态矩形 / 通道 / 三角形 / 楔形的多边形右边缘从形态确认时刻拉到最新 K 线 X。
- **前端**：摆动骨架（zigzag / backbone / live_leg）末端 dot 改为锚定到最新 K 线的 high / low，按"与上一个 dot 距离更近"挑选，使蓝色折线在右侧收束到一个明显的活动 dot，而不是留下一段空白 trendline 外推。
- **测试**：新增 `tests/test_structure_overlay_extension.py`，4 个静态断言：region 必须延伸、swing_zigzag 必须延伸、pattern_path 不能延伸、polygon 右角必须移动到 latestX。
- **验证**：`tests/test_structure*.py` 全量 45 passed；Playwright 后端无快照时无法截屏验证视觉，依赖源码 + 静态测试作为回归门禁。

### BTC 衍生品页证据/保护规划上下两层重设计

- **前端**：把“指标状态与多空证据”与“网格与现货保护规划”从并排改为上下两层（`btc-layout-row--evidence` 与 `btc-layout-row--protection` 各自独占一行），4 张证据子卡改为 `repeat(auto-fit, minmax(220px, 1fr))` + `grid-auto-rows: 1fr` 等高排版。
- **设计**：新增 `.btc-confidence-chip` 三档配色（高/中/低）与 `.btc-tone-chip`（bullish/bearish/neutral）；保护规划表单拆 3 段（标的 / 网格区间 / 风控参数）使用 fieldset + legend；按钮带 SVG 箭头，提示文字置于按钮下方。
- **修复**：删除原 `btc-hedge-result` 容器在无数据时输出的小字溢出（`min-height: 220px` 配合右浮小字）改为上下排版与表单同列。
- **测试**：`tests/test_btc_derivatives_frontend_static.py` 更新 CSS class 引用 `.btc-hedge-grid` → `.btc-hedge-form` / `.btc-hedge-section`。
- **验证**：Playwright 实测 4 张证据子卡等高 221.2px、3 段 fieldset、8 个字段、按钮 + 提示文字、0 console error / 0 page error。

### 市场状态卡冷静专业化

- **前端**：技术指标页 `.status-mode-badge` 重新设计，从大面积琥珀色警告框改为冷白半透明、三段式（`.regime-icon` / `.regime-info` / `.regime-action`）的冷静专业风格。左侧 36px 圆角方形图标使用内嵌 SVG（range: 趋势柱线 / transition: 折线）+ 青绿色调；中部眉题 `市场状态 · RANGE|TRANSITION` + 主结论；右侧圆角幽灵按钮，内嵌 SVG 箭头替代文本字符 `→`，hover 时箭头右移。
- **设计**：删除 emoji 风格不一致（📊 / ⚡），统一 SVG；删除文本下划线和黄色警告色；保留 RANGE / TRANSITION 模式结构，仅通过图标和强调色区分。
- **响应式**：720px 以下允许操作按钮换行到下一行并右对齐。
- **测试**：`tests/test_analysis_mode_badge.py` 新增 `test_mode_badge_markup_has_no_emoji_or_text_arrow` 静态断言，约束新结构。
- **验证**：Playwright 实测 cold-load 0 错误、状态卡 bbox `{w:1368, h:64}`、hover 态箭头右移生效。

## v1.8.0 (2026-07-23)

### 知识百科 chip 压缩

- **前端**：术语卡"出现在 X 个页面"的多 chip 簇改为单行 `i N 页可用 ▾` 触发器 + hover/focus 弹出 popover（每页 + 一句话用途）。`app/static/pages/knowledge.js` 的 `renderPageRefsBadge()` 重写；CSS-only 交互；新增 `KNOWLEDGE_PAGE_NOTE` 映射。`app/static/styles.css` 新增 `.knowledge-page-refs*` 块。
- **测试**：`tests/test_knowledge_catalog.py` 新增 3 个静态断言（compact trigger、无 SPA 链接泄漏、per-page notes）。
- **验证**：`python tests/verify_pages.py` 11/11 cold-load + 10/10 SPA switch 通过，0 console/page errors。

### 版本号统一

- **架构**：以 `app/__version__ = "1.8.0"` 为单一来源；`config.py` / `paths.py` 改为 import 而非硬编码；`pyproject.toml` 作为 packaging release authority，由 `tests/test_version_consistency.py` 钉住与 `app.__version__` 一致。
- **文档**：`.env.example` / `README.md` / `CHANGELOG.md` 全部对齐到 1.8.0。

## v1.7.1 (2026-07-07)

### 黄金配置页 V2 升级

- **多空标签**：核心/派生指标卡右上角标签从"可用/偏低"改为 5 档多空判断（强势看多 / 看多 / 中性 / 看空 / 强势看空）。新增 `_bias_for_indicator()` 后端函数 + 5 档 CSS 类。
- **宏观指标**：新增 4 个核心宏观卡（real_yield_10y / DXY / CPI YoY / VIX）。每个卡显示多空标签 + bias_reason + 数据源。后端新增 `_gold_macro_snapshot()` 函数实现黄金视角的多空判断（含 CPI 二维表 / VIX 流动性冲击例外 / DXY 危机例外）。
- **设计语言**：页面从 4 段并列升级到 9 段递进（Hero 决策 → 4 宏观 → 7 模块 → 图表 → XAUT/黄金坑 → 执行 → 核心/派生指标 → 数据治理）。新增 `.gold-bottom-group` 二级容器（沿用 BTC bottom-group 模式）与 `.gold-decision-card[data-tone]` 4 色状态。

### 后端

- `app/services/gold_dca_dip.py`: `_indicator_card()` 新增 `bias` 字段；新增 `_bias_for_indicator()` 函数
- `app/services/gold_macro_adapter.py`: 新增 `_gold_macro_snapshot()` 函数
- `app/services/gold_allocation_engine.py`: `AllocationPlan` 新增 `macro_payload` 字段；`to_dict()` 暴露 `gold_macro_snapshot`
- `app/schemas/gold_allocation.py`: `GoldAllocationPlanResponse` 新增 `gold_macro_snapshot` 字段

### 前端

- `app/static/pages/gold_allocation.js`: 9 段递进重写（hero / decision / macro / modules / charts / xaut / execution / indicators / governance）；新增 `biasLabel` / `renderMacroStrip` / `renderMacroCard` / `renderDecisionGrid` / `renderModuleSection` / `renderChartSection` / `renderGovernanceSection` / `renderModuleCard` 函数；`loadExecutionPlan` 拉取 `/gold/allocation`
- `app/static/styles.css`: 新增 ~122 行 CSS（7 个多空 chip + 二级容器 + 4 宏观卡 + 流动性冲击警告）

### 测试

- `tests/test_gold_dca_dip_engine.py`: 新增 6 个 `_bias_for_indicator` 测试
- `tests/test_gold_macro_adapter.py`: 新建文件，6 个 `_gold_macro_snapshot` 测试
- `tests/test_gold_allocation_engine.py`: 新增 1 个 `gold_macro_snapshot` 集成测试
- `tests/test_gold_frontend_static.py`: 新增 7 个 V2 DOM 结构断言

### 已知问题 / Follow-up

- 强档阈值在 spec 文本"lower*0.7 / upper*1.3"对 negative lower 存在语义歧义。Implementer 做了语义化解读（lower≥0 时 *0.7，lower<0 时 *1.3，向 strong 方向延伸 30%）。建议未来 spec 修订时明确化。
- 图表区（5 段）目前是占位卡，真实图表实现可在 v1.7.2 实施。
- `_gold_macro_snapshot` 中 `bias_reason` 中文长字符串与流动性冲击阈值 (25/105/2.0) 硬编码在函数体内。可在未来 Task 提取为常量以减少漂移风险。
