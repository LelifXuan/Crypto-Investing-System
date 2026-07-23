# 六大模块规格

## 1. 仓位管理

### 输入
- Fill
- InstrumentSpec
- MarkPrice

### 输出
- PositionView
- PositionSnapshot

### 关键能力
- AVG_COST / FIFO
- 反手拆分
- 幂等
- 重放
- 对账

---

## 2. 盈利计算

### 输入
- Fill
- Funding
- CashMovement
- MarkPrice
- FXRate

### 输出
- PnLSnapshot
- PnLLine

### 关键能力
- realized / unrealized
- fee / funding / slippage
- 多币种折算
- 版本化口径

---

## 3. 交易复盘

### 输入
- PositionSnapshot
- PnLSnapshot
- Fill
- MarketEvent

### 输出
- equity curve
- drawdown curve
- trade group stats
- export csv

### 指标
- win_rate
- profit_factor
- max_drawdown
- sharpe_like
- holding_time_distribution

---

## 4. 技术指标

### 输入
- Candle

### 输出
- SMA
- EMA
- RSI
- MACD
- BBANDS

### 关键要求
- 支持 lookback
- 支持增量更新
- 支持批量回算
- 参数可序列化

---

## 5. 市场价格

### 输入
- WebSocket / REST / Vendor API

### 输出
- CandleEvent
- TickEvent
- MarkPriceEvent
- OrderBookDiffEvent

### 关键要求
- 断线重连
- 快照回补
- 延迟监控
- 源质量打分

---

## 6. 市场事件信息

### 输入
- 宏观日历
- 新闻
- 公告
- 链上日志

### 输出
- MarketEvent
- EventAnnotation

### 关键要求
- 去重
- 可靠性分级
- 事件与 instrument 绑定
- 与复盘时间轴对齐
