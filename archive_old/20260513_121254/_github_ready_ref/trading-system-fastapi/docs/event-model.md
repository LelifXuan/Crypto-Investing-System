# 事件模型

## Event Envelope

所有事件统一封装：

```json
{
  "event_id": "01JABC...",
  "event_type": "trade.fill.v1",
  "schema_version": 1,
  "source": "venue.binance",
  "partition_key": "account_001|BTCUSDT",
  "ts_event": 1760000000123,
  "ts_ingest": 1760000000456,
  "trace": {
    "trace_id": "abc",
    "span_id": "def"
  },
  "payload": {}
}
```

## 事件类型

### trade.fill.v1
成交事实。

### cash.movement.v1
入金、出金、人工调整、手续费扣减。

### funding.payment.v1
永续资金费率支付。

### market.candle.v1
K线。

### market.tick.v1
买一卖一 / best bid ask。

### market.mark_price.v1
标记价格。

### market.fx_rate.v1
汇率。

### market.event.v1
市场事件信息。

## 重放规则

- 事件存储 append-only
- 读取按 `(partition_key, ts_event, event_id)` 排序
- 同一个幂等键重复写入应被拒绝
- 派生视图允许删表重建
