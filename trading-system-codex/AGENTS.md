# AGENTS.md

你正在实现一个交易系统管理平台。请严格遵守以下约束。

## 一、总目标

构建一个**以管理链路为核心**的交易系统，而不是先做超低延迟撮合系统。  
最少包含以下 6 个模块：

- 仓位管理
- 盈利计算
- 交易复盘
- 技术指标
- 市场价格
- 市场事件信息

## 二、实现优先级

1. 数据模型与数据库
2. 市场数据接入
3. 仓位管理
4. 盈利计算
5. 复盘分析
6. 技术指标
7. 市场事件
8. 观测、权限、审计

## 三、硬性约束

- 禁止用 float 存储金额、数量、价格，统一使用 decimal / numeric
- 所有时间统一使用 UTC，存储为 timestamptz 或 epoch_ms
- 交易事实必须 append-only，不允许直接覆盖历史事实
- 所有 PnL 输出必须带上口径版本 metadata
- API 设计优先 REST + OpenAPI，内部流式/高频接口可补充 gRPC
- 先保证正确性、可回放、可审计，再做性能优化
- 代码必须可测试，至少提供单元测试和集成测试骨架

## 四、领域规则

### 1. Fill 幂等
同一个 `(source, account_id, fill_id)` 只能入账一次。

### 2. 仓位成本法
第一版必须支持：
- AVG_COST
- FIFO

### 3. PnL 输出
至少包含：
- realized_pnl
- unrealized_pnl
- fees
- funding
- slippage_cost
- equity

### 4. 多币种
所有费用保留原始币种，同时支持折算到报告币种。

### 5. 市场数据
第一版只需要支持：
- candle
- best bid/ask
- mark price
- order book diff（可选）

### 6. 技术指标
第一版只实现：
- SMA
- EMA
- RSI
- MACD
- Bollinger Bands

### 7. 复盘
第一版只实现：
- 胜率
- 盈亏比
- 最大回撤
- 收益曲线
- 费用归因
- 品种贡献

## 五、工程风格

- 目录按模块拆分，避免一层 giant service
- 所有 handler / service / repository / domain model 分层明确
- 所有对外结构定义放在 schema / DTO 层
- 所有重要公式和边界条件要写注释
- 所有数据库变更必须有 migration 思维
- 所有新接口都要更新 OpenAPI 文档

## 六、验证工作流（强制）

每次修复完成后，必须执行以下验证步骤，**绝对禁止未经验证即汇报完成**：

### 验证流程

1. **语法检查**
   - JS 文件：`node --check <file>`
   - Python 文件：`python -c "import py_compile; py_compile.compile(...)"`

2. **数据连通性验证（涉及外部 API 时必须）**
   - 用 `curl` 或 `python -c "import httpx..."` 直接请求外部 API
   - 确认返回状态码和数据内容
   - 测试 direct + proxy 两种路径

3. **运行相关测试**
   - `python -m pytest tests/` 运行对应模块测试
   - 确认全部通过，不忽略任何失败

4. **日志验证（涉及后台 worker / 数据抓取时必须）**
   - 检查 `runtime_dev/source_runtime/runtime/logs/` 下最新日志
   - 确认有预期中的成功日志 / 错误日志
   - 没有日志输出 = 可能根本没跑到

5. **缓存/数据文件验证**
   - 检查缓存文件是否更新（时间戳、内容）
   - 确认数据字段不是全 null / 空

### 验证清单模板

```
☐ 语法检查通过（JS + Python）
☐ 外部 API 连通性测试通过
☐ 相关 pytest 全部通过
☐ 日志中有预期输出
☐ 缓存/数据文件有有效内容
```

### 工作流集成

每次修改完成后，**必须**执行：

1. `node --check <每个改动的 JS 文件>`
2. `python -c "import py_compile; py_compile.compile('<file>', doraise=True)"`
3. `python -m pytest tests/ -q`（或相关测试模块）
4. **全部通过后再汇报**，不得跳过验证步骤

验证通过标志：
```
☐ ruff: All checks passed
☐ pytest: X passed, 0 failed
☐ compileall: all compiled
☐ node --check: all passed
```

### 错误处理原则

- 修复代码只是手段，**数据正确到达前端**才是目标
- 如果外部 API 不可达，记录原因并告知用户，而非静默吞掉错误
- 永远保留缓存降级路径，确保网络故障时不返回空白页

## 七、提交策略

- 每个功能域独立 commit，禁止混入运行时文件（.db, .log, cache）
- 禁止直接提交 API Key 和 secret
- Commit message 格式：`[domain] 简述`
  - `[macro]` — 宏观数据、指标、评分
  - `[frontend]` — 前端页面、JS、CSS
  - `[network]` — 代理、数据源、API 接入
  - `[config]` — 配置文件（catalog, yaml, json）
  - `[test]` — 测试用例
  - `[docs]` — 文档
  - `[infra]` — 构建脚本、CI、工作流

## 八、输出要求

每次完成任务时：
1. 说明修改了哪些文件
2. 说明为什么这样设计
3. 说明已知风险和下一步建议
4. 不要一次性重构全项目，保持变更小而清晰
