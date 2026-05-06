# market-event-sources-codex-pack

这是一份给 Codex 的“市场事件信息源”扩展包，目标是为你现有的交易系统补上**国内不翻墙优先**的事件信息来源目录、抓取策略、规范化字段和数据库设计。

## 包含内容

- `configs/market_event_source_catalog.yaml`
  - 事件源目录，含官方优先级、可访问性判断、接入方式、轮询周期、解析提示
- `configs/market_event_ingestion_profiles.yaml`
  - 抓取/回补/失败重试策略
- `configs/market_event_normalization_rules.yaml`
  - 事件规范化字段、重要性映射、去重规则
- `db/market_event_source_extension.sql`
  - PostgreSQL 表设计
- `docs/source-selection-notes.md`
  - 来源选择说明与推荐顺序
- `prompts/codex-market-event-source-implementation.md`
  - 直接发给 Codex 的实现任务
- `examples/event_source_bootstrap.json`
  - 启动时写入 `market_event_sources` 的示例数据

## 设计目标

1. 官方源优先，门户聚合作为 fallback。
2. 国内网络优先可访问，减少依赖需要翻墙的源。
3. 宏观、交易所、项目事件、链上异动分层处理。
4. 所有外部源均先落 `raw_items`，再规范化入 `market_events`。
5. 事件系统要支持：
   - 日历类事件（scheduled）
   - 快讯类事件（published）
   - 链上异动类事件（detected）
   - 监管/政策类事件（effective）

## 推荐第一批接入顺序

1. `cn.stats.*`
2. `cn.pbc.*` + `cn.lpr.index`
3. `cn.safe.statistics`
4. `cn.gov.policy`
5. `domestic.jin10.calendar`
6. `crypto.gate.announcements` + `crypto.gate.new_listings` + `crypto.gate.calendar`
7. `crypto.panews.rss`
8. `crypto.odaily.newsflash`
9. `onchain.tokenview.api`

## 落地建议

- 宏观官方源：偏低频、高可信，适合 `scheduled poller`
- Gate / Web3 媒体：中高频，适合 `fast poller`
- Tokenview：高频，适合 `api poller` 或 webhook
- 对动态渲染页面（如部分日历页），默认启用 Playwright/Chromium fallback
- 所有来源都要做 `etag/last-modified`、内容哈希和语义去重

## 你给 Codex 的一句话提示

请基于本包实现市场事件源接入层、规范化层、调度层与告警层，并与现有 `market_events`、`indicators`、`market_prices` 模块打通。
