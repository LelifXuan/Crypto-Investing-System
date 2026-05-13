# SPEC.md

## 1. 项目定义

这是一个交易系统管理平台，用于统一记录、计算、查询和复盘交易行为。  
其核心价值是：

- 统一交易事实
- 统一仓位视图
- 统一盈利口径
- 统一复盘分析
- 支持市场数据和事件对齐
- 为 AI 编程助手提供稳定、可分阶段实现的工程边界

## 2. 目标用户

### A. 个人加密交易者
- 多交易所
- 现货 / 永续
- 重视手续费、资金费率、滑点
- 更重视看板和复盘体验

### B. 机构多资产团队
- 多账户、多柜台、多资产
- 更重视权限、审计、一致性
- 更重视标准化接口和历史复算能力

## 3. 非目标

第一版不做：
- 撮合引擎
- 订单执行算法
- 做市策略引擎
- 高频低延迟撮合网关
- 风险审批工作流的完整企业系统

## 4. 总体架构

建议采用：

- 事件总线：JetStream（原型）/ Kafka（生产）
- 关系库：PostgreSQL
- 时序/分析库：TimescaleDB 或 ClickHouse
- 缓存：Redis
- 对外接口：REST/OpenAPI
- 内部流式接口：gRPC（可选）

## 5. 核心实体

- Tenant
- Account
- Strategy
- Instrument
- Order
- Fill
- CashMovement
- FundingEvent
- FXRate
- MarkPrice
- PositionSnapshot
- PnLSnapshot
- MarketEvent

## 6. 核心流程

### 6.1 Fill -> Position
Fill 写入事件存储后，Position 聚合器更新当前仓位视图。

### 6.2 Fill + Mark + FX -> PnL
PnL 聚合器消费 Fill / Funding / Cash / Mark / FX，生成当前收益快照和历史曲线。

### 6.3 Market Data -> Indicators
K线入库后触发指标引擎，生成 SMA/EMA/RSI/MACD/BBANDS。

### 6.4 PnL + Trades + Events -> Review
复盘服务聚合收益曲线、交易分组、市场事件和指标，生成报表。

## 7. 成本法与收益口径

### 7.1 AVG_COST
同向加仓采用均价法；反向成交拆成平仓部分和新开仓部分。

### 7.2 FIFO
按批次先进先出匹配平仓。

### 7.3 已实现收益
由平仓部分产生。

### 7.4 未实现收益
由当前仓位和 mark price 产生。

### 7.5 费用
必须保留原币种。

### 7.6 滑点
默认参考价基准允许配置：
- mid
- arrival
- snapshot_bid_ask

## 8. 可靠性要求

- Fill 入账必须幂等
- Market data 允许最终一致
- Read Model 允许最终一致
- 审计和事件事实必须强一致
- 所有批量重算结果必须可复现

## 9. 性能目标（建议值）

### 原型版
- Fill -> Position P95 < 500ms
- Fill -> PnL P95 < 500ms
- Position 查询 P95 < 200ms
- 指标查询 P95 < 100ms

### 生产版
- Fill -> Position P95 < 100ms
- Fill -> PnL P95 < 200ms

## 10. 安全要求

- JWT/OAuth2 兼容
- RBAC 至少支持：admin / trader / viewer / auditor
- 手工调账必须有审计记录
- 所有敏感写接口必须有幂等键
- 所有接口需具备限流能力

## 11. 交付标准

每个模块的第一版都必须满足：
- 数据结构明确
- API 明确
- 单元测试可跑
- 集成测试可跑
- OpenAPI 已更新
- 至少一个示例请求/响应
