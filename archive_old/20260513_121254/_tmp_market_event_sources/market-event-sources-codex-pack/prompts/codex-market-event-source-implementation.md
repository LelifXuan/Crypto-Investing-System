你正在为一个 FastAPI + PostgreSQL 的单用户本地交易系统实现“市场事件信息源”模块。

请严格依据本目录下的配置文件完成实现，不要重新发明数据模型。

## 输入文件

- `configs/market_event_source_catalog.yaml`
- `configs/market_event_ingestion_profiles.yaml`
- `configs/market_event_normalization_rules.yaml`
- `db/market_event_source_extension.sql`

## 目标

实现以下能力：

1. 建立 `SourceAdapter` 抽象接口：
   - `fetch_index()`
   - `fetch_detail()`
   - `parse_candidates()`
   - `healthcheck()`

2. 按 source catalog 为这些 source 生成 adapter skeleton：
   - `cn.stats.release_schedule`
   - `cn.stats.home_preview`
   - `cn.pbc.home`
   - `cn.pbc.omo_announcements`
   - `cn.lpr.index`
   - `cn.safe.statistics`
   - `cn.gov.policy`
   - `domestic.jin10.calendar`
   - `domestic.eastmoney.calendar`
   - `crypto.gate.announcements`
   - `crypto.gate.new_listings`
   - `crypto.gate.calendar`
   - `crypto.panews.rss`
   - `crypto.odaily.newsflash`
   - `onchain.tokenview.api`

3. 为 HTML 源实现通用抓取器：
   - requests + httpx
   - retry with backoff
   - etag/last-modified
   - content hash
   - optional Playwright fallback

4. 为 RSS 源实现：
   - feedparser adapter
   - published_at parsing
   - link canonicalization

5. 为 API 源实现：
   - API key injection
   - rate limit guard
   - pagination abstraction
   - retry and timeout policy

6. 实现规范化层：
   - `RawEventCandidate -> NormalizedMarketEvent`
   - importance / severity mapping
   - event_type / event_subtype mapping
   - dedupe logic

7. 实现调度层：
   - 根据 `market_event_ingestion_profiles.yaml` 注册 cron/interval jobs
   - source health state
   - fallback source failover

8. 实现数据库写入：
   - `market_event_sources`
   - `market_event_fetch_runs`
   - `market_event_raw_items`
   - `market_events`
   - `market_event_alert_rules`
   - `market_event_alerts`

9. 实现 API：
   - `GET /api/v1/market-events/sources`
   - `POST /api/v1/market-events/sources/{source_id}/sync`
   - `GET /api/v1/market-events`
   - `GET /api/v1/market-events/{event_id}`
   - `GET /api/v1/market-events/fetch-runs`
   - `POST /api/v1/market-events/alerts/test`

10. 实现测试：
   - config load tests
   - normalization tests
   - dedupe tests
   - source adapter smoke tests
   - parser fixture tests

## 关键约束

- 事件源必须按 official_priority 分层治理
- 不允许把媒体快讯直接覆盖官方事件
- 所有外部事件必须先落 raw，再做 normalize
- 不要把 source-specific 字段硬编码进 canonical schema
- 不要在代码中明文写 API key
- 默认时区为 `Asia/Shanghai`

## 代码组织建议

- `app/events/sources/`
- `app/events/adapters/`
- `app/events/normalizers/`
- `app/events/scheduler/`
- `app/events/repositories/`
- `app/api/v1/endpoints/market_event_sources.py`

## 第一阶段可接受的结果

- 先实现 skeleton + config-driven registry
- 至少完成：
  - 国家统计局
  - PBOC
  - Gate announcements
  - Gate listings
  - PANews RSS
  - Tokenview API

生成代码时保持可读、模块化、可测试。
