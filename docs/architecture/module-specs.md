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

### 市场事件页渲染（2026-08-06 优化）
- **供给事件日历**：`GET /market-events/supply-event-calendar`（`supply_event_calendar_nodes` 只读视图，按 `event_at` 升序）→ `api.getSupplyEventCalendar()` → 页面「未来事件日历」卡。
- **渲染去重**：信息流按事件指纹（event_id/正文/翻译状态）diff，数据未变则跳过 innerHTML 重建；供给日历按 items 指纹独立重建。
- **竞态防护**：`load()` 统一走 AbortController；`unmount`/`pause` 中止在途请求并停翻译轮询；`resume` 重新拉取。
- **局部更新**：翻译开关切换只重建信息流容器（不全量重建 metrics/日历）；供给日历筛选只重建列表容器（保留 dropdown 实例）。
- **前端缓存**：供给日历 60s TTL；信息流沿用 `api.js` 的 ttl=30s。

---

## 6.1 知识百科页渲染（2026-08-06 优化）

- **生命周期**：`renderKnowledge` 返回 SPA controller；`unmount` 移除 `hashchange` 监听器、清防抖 `searchTimer`、重置过滤状态与挂载标记，`pause`/`resume` 收敛后台渲染——消除切页后监听器泄漏与悬空 timer。
- **事件委托**：`.knowledge-sections` 容器只挂一个 click 委托处理「展开/收起」，替代每次重建后逐卡绑定 146 个按钮监听器。
- **单一渲染源**：`renderSectionsHtml(sections)` 统一首屏布局与筛选更新的分区 HTML 生成，消除两处漂移逻辑。
- **数据缓存**：`ALL_ITEMS` 摊平一次（146 项），`allItems()`/`familyOptions()` 直接复用；metrics 按快照键去重。
- **hash 定位收敛**：`focusHashTarget` 只在挂载与 `hashchange` 时触发（不再在每次筛选/搜索后滚动定位）；过滤隐藏目标时清过滤使其可见的语义保持不变。
- 移除 `updateKnowledgeContent`/`syncFilterControls` 中已不存在的原生 `<select>` 死分支。

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
  ← JSON {series, events, summary, meta}
  ← POST /api/v1/ashare-etf/simulation
  ← EtfHistoryService.get_snapshot(fetch=False)   ← 纯读缓存历史,不触发外部拉取
  ← runtime/cache/fund_history/{code}.json         (历史数据库,导入脚本 append)
```

### 数据更新约定
- **每日更新 = 只新增**：当天拿到新数据后跑 `scripts/import_etf_history_csv.py --csv <当日文件>`，按 `trade_date` 追加新 bar 到缓存（幂等，重复导入不重复；已有 bar 不变）。
- **模拟计算只读数据库**：模拟端点 `get_snapshot(..., fetch=False)`，纯读缓存历史计算，绝不隐式触发外部 API。
- **只向前增量**：上游增量拉取（若启用）严格从 `coverage_end + 1` 开始，永不再抓已有日期，杜绝外部数据改写导入/核验过的 bar（如 563010 的 2023-07-14 起点）。
- 导入的 CSV 原始文件归档于 `runtime/cache/fund_history/source/`。

### 端点
- `POST /api/v1/ashare-etf/equity-curve`（canonical）
- `POST /api/v1/etf/equity-curve`（legacy alias）
- Auth：`require_roles("admin", "trader", "analyst", "viewer")`

### 不做
- 蒙特卡洛 / 概率带 / 未来预测
- 基准对比（如沪深300）
- 每只 ETF 子曲线切换 UI（数据已返回，前端按需扩展）

---

## 7.1 ETF 策略模拟（扩展模块，2026-08-06 修正）

按《ETF Rolling-252 Cov 策略与资金投入说明书》定稿（2026-08-06）执行规则回放，供「策略模拟」收益率图表使用。文件定位：正式执行只有一条主流程——初始建仓一次，之后固定月定投只买不卖，季末在当期定投计入后复核带宽并决定是否调仓；回测候选、12 期分批与多种初始比例不进入执行文件。

### 输入
- 初始建仓资金 `initial_capital`（默认 100000 元，一次性按目标权重建仓）
- 每期定投金额 `period_amount`（默认 5000 元/期）
- 定投频率 `frequency`：`month`（默认，每月末一个交易日）或 `week`（每周最后一个交易日；周与月只是资金到账频率的区别，首次建档后保持固定，§2.2/表0）
- 起始月份 `from_month`、截至日 `to_date`
- 6 只 ETF 历史 NAV（固定标的：561560 电力 / 159930 能源 / 512400 有色 / 516950 基建 / 512660 军工 / 563010 电信；不含现金流 ETF）。历史数据存储在 `runtime/cache/fund_history/{code}.json`，可由在线 API 增量拉取，也可用 `scripts/import_etf_history_csv.py --csv <文件>` 直接把打包好的日线 CSV（date + `{code}_close` + `{code}_volume`）合并导入缓存（幂等，按 trade_date 合并、只补缺不降级已有 OHLC bar）。

### 核心规则（与说明书逐条对应）
- **目标权重固定**（表1）：25.00 / 18.98 / 10.59 / 19.08 / 14.35 / 12.00（合计 100%）。研究只输出最终权重，引擎不做滚动 252 日 ERC 求解。
- **逐标的带宽**（§3）：`有效带宽 = max(目标权重×20%, 2.5pp)` → 5.00 / ≈3.80 / 2.50 / ≈3.82 / ≈2.87 / 2.50（%）。
- **初始建仓一次**（§2.1）：首个交易日把 `initial_capital` 按目标权重建仓，最欠配优先、逐手买入，不足一手的余额留存现金。
- **定投只买不卖**（§4）：每个定投日（月定投=每月末交易日；周定投=每周最后一个交易日）入账 `period_amount` 后仅买入低于目标权重的 ETF（欠配优先）；买不起一手 → HOLD，现金滚存下期。
- **定投尊重带宽走廊**（2026-08-07 修正）：月度定投的买入目标下移至带宽下沿 `目标权重 − 带宽`，只把明显欠配（跌破走廊下沿）的标的补回走廊内，不再每月把每只标的精确对齐到目标权重——否则季内价格漂移被月内对齐抹平，季末带宽复核几乎无漂移可纠（39 个真实月份仅 1 次调仓）。初始建仓与复核后修正买入仍部署到精确目标。走廊内漂移保留到季末复核，带宽机制恢复真实纠偏作用（39 个月约 5 次调仓）。
- **季末调仓**（§5）：当期定投计入后按逐标的带宽复核；触发时先卖超配（卖至接近目标的整手份额）再买欠配；未触发不卖。调仓时点默认资金可用当日（`rebalance_offset_days=0`，支持 0–5 交易日，不机械等 5/10 日）。
- **整手、费用与现金**（§6）：100 份整手；佣金 `max(成交额×万2.5, 5 元)`；滑点买价×(1+0.1%)、卖价×(1−0.1%)；交易后现金不低于最低保留现金。

### 输出
- `EtfSimulationResponse`
  - `series[]`：每期快照 `{date, total_value, cost_value, cash_value, per_symbol_shares, per_symbol_value, lump_sum_value, return_pct, lump_sum_return_pct}`
    - `cost_value` = 累计投入资金（初始建仓 + 各期定投），卖出不减少
    - `return_pct` = 现金口径 `(total_value − cost_value) / cost_value`
    - **起始锚点**：第一个快照是初始建仓交易日，其 `return_pct` / `lump_sum_return_pct` 固定为 0（参考原点）；`total_value` 仍是含当日费用后的真实市值。曲线从 0% 起步，避免「起始即负数」的伪影——首月月末快照起才展示真实的费用与市场漂移
  - `events[]`：DCA 与季末复核事件，含 `dca_cash_added`、`dca_trades`、`rebalance_trades`、`trade_rationale`（side / target_weight / current_weight / drift_pct / notional）
  - `summary`：`{final_total_value, final_cost_value, final_cash_value, peak, trough, max_drawdown_pct, total_return_pct, rebalance_count, cumulative_friction, months_simulated, lump_sum_final_value, lump_sum_vs_dca_pct}`
  - `meta`：`{data_source, coverage, symbols_with_data, symbols_missing, source_status, halos_listing_start}`
    - `halos_listing_start` = **六只齐全日**：第一个六只 ETF 都有 NAV 收盘价的交易日（交集首日，而非各标的首日的 max——max 会落在其他标的有数据缺口的日子，低估真实起点）。当前数据下为 **2023-07-14**；前端默认起始月取此值，曲线从六只齐全的第一天开始。
- 一次性投入对比基准：同额总资金（初始 + 定投合计）按目标权重在首个交易日建仓持有、不再平衡。

### 端点
- `POST /api/v1/ashare-etf/simulation`（canonical）
- `POST /api/v1/etf/simulation`（legacy alias）
- Auth：`require_roles("admin", "trader", "analyst", "viewer")`

### 已知边界
- 历史回放使用当前确认的固定权重（说明书未提供历史权重版本；回测候选不进入正式执行文件）
- 实盘「定投与再平衡」下单模块（`ashare_etf_rebalance.py`）仍使用旧目标权重，与表1 不一致——待独立对齐
- 周/月定投均已实现（`frequency` 参数）；定投频率仅影响资金到账节奏，不改变调仓逻辑
- 历史缓存为**只向前增量**：请求窗口早于缓存起点不触发回填（缓存是权威，可能含导入/核验过的 bar），只在上游有新数据时向后延伸（`_window_extends` 仅判断 `to_date > coverage_end`）；模拟计算走 `fetch=False` 纯读缓存
