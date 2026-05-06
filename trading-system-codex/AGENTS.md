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

## 六、输出要求

每次完成任务时：
1. 说明修改了哪些文件
2. 说明为什么这样设计
3. 说明已知风险和下一步建议
4. 不要一次性重构全项目，保持变更小而清晰
