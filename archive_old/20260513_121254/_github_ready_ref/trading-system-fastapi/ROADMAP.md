# ROADMAP.md

## Phase 0：项目初始化
- 建立目录结构
- 建立数据库 schema
- 建立 OpenAPI
- 建立 proto
- 建立基础配置与日志框架

## Phase 1：市场数据
- Candle 接入
- BBO 接入
- Mark Price 接入
- Instrument 主数据
- 基础查询接口

## Phase 2：仓位管理
- Fill 入账
- AVG_COST
- FIFO
- Position View
- Position Snapshot
- 幂等与重放

## Phase 3：盈利计算
- Realized PnL
- Unrealized PnL
- Fees
- Funding
- FX 折算
- Equity 曲线

## Phase 4：技术指标
- SMA
- EMA
- RSI
- MACD
- Bollinger Bands
- 批量回算 + 增量更新

## Phase 5：交易复盘
- Trade grouping
- 胜率 / 盈亏比 / 最大回撤
- 收益曲线与费用归因
- 事件对齐
- 导出 CSV

## Phase 6：市场事件
- 宏观日历
- 新闻事件
- 交易所公告
- 链上事件
- 事件去重与可靠性分级

## Phase 7：工程化增强
- 审计日志
- 权限体系
- OpenTelemetry
- 限流与重试
- Docker Compose / Helm
