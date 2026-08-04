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

---

## 7. ETF 历史权益曲线（扩展模块，2026-08-04）

诚实的历史回放，不是预测。

### 输入
- 用户持仓（shares + cost_price，浏览器 localStorage）
- 起始日（用户在前端 `<input type=date>` 选）
- 截至日（默认今天）
- 现金（`state.cashToInvest`）
- ETF 历史 NAV 时序（来自 `runtime/cache/fund_history/{code}.json` 磁盘缓存 + `push2his.eastmoney.com` 增量回填）

### 输出
- `EtfEquityCurveResponse`
  - `labels: list[date]` — 窗口内所有有数据的交易日
  - `total_value: list[Decimal]` — cash + Σ shares × NAV 每日合计
  - `per_symbol: dict[symbol, list[Decimal | None]]` — 每只 ETF 子序列
  - `summary: { current, starting, peak, trough, max_drawdown_pct, total_return_pct, cumulative_cost, days_observed }`
  - `meta: { data_source, fetched_at, coverage_start, coverage_end, missing_dates, symbols_with_data, symbols_missing, source_status }`
  - `warnings: list[str]`

### 关键能力
- **历史回放**：每天 `cash + Σ shares × close` 严格累加
- **缺失日期 fallback**：last-known-good carry-forward + `meta.missing_dates` 审计
- **缺失 symbol**：记录在 `meta.symbols_missing`，不假装成 0
- **上游断连降级**：endpoint 仍返回 200 + `source_status: partial`，UI 显示"等待历史数据"
- **Decimal 端到端**：无 float 漂移
- **缓存优先 + 增量拉取**：先读磁盘 `runtime/cache/fund_history/`，缺哪段拉哪段

### 数据流
```
浏览器 (etf-equity-canvas) 
  ← JSON {labels, total_value, summary, meta}
  ← POST /api/v1/ashare-etf/equity-curve
  ← EtfHistoryService.get_snapshot() (cache → push2his)
  ← build_equity_curve() (Decimal math)
```

### 端点
- `POST /api/v1/ashare-etf/equity-curve`（canonical）
- `POST /api/v1/etf/equity-curve`（legacy alias）
- Auth：`require_roles("admin", "trader", "analyst", "viewer")`

### 不做
- 蒙特卡洛 / 概率带 / 未来预测
- 基准对比（如沪深300）
- 每只 ETF 子曲线切换 UI（数据已返回，前端按需扩展）
