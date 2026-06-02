# 缓存架构

## 缓存层级

| 层级 | 位置 | 用途 |
| --- | --- | --- |
| Page Snapshot | `page_snapshot_cache` 表 | 分析页、监控页、告警页的页面快照 |
| Computed Dataset | `computed_dataset_cache` 表 | 预计算数据集，例如策略信号 bundle |
| Macro Provider TTL | 内存与 `runtime/cache/` | 宏观 API 响应缓存 |
| ETF Quotes Disk | `runtime/cache/ashare_etf_quotes.json` | A 股 ETF 报价磁盘缓存 |
| Seed Cache | `app/assets/seed_cache/` | 便携版预置种子数据 |
| Translation Text | `translation_text_cache` 表 | 翻译文本去重与复用 |

## 降级链路

1. 实时 API 拉取，标记为 `live`。
2. TTL 内命中内存缓存，标记为 `hit`。
3. 过期但仍在可接受窗口内，标记为 `stale`。
4. 使用磁盘持久化缓存，标记为 `cached`。
5. 使用打包种子缓存，标记为 `seed`。
6. 无可用数据时返回明确占位状态，避免空白页。

## 页面快照

分析页、监控页和告警页使用统一快照机制：

- 写入：`MarketRepository.upsert_page_snapshot_cache()`
- 读取：`MarketRepository.get_page_snapshot_cache()`
- 状态：`fresh`、`stale`、`missing`、`error`
- 刷新入口：`/api/v1/analysis/refresh`、`/api/v1/monitoring/dashboard/refresh`

## Worker 日志

启动时应记录每个 worker 的状态：

```text
worker indicator_monitor: started
worker precompute: started
worker market_event_translation: started
worker market_events_feed: started
worker event_bus: skipped (profile=desktop_light)
worker market_stream: skipped (profile=desktop_light)
```

同步完成或失败时应记录结果、耗时和异常原因，便于判断页面数据来自实时源、缓存还是降级路径。
