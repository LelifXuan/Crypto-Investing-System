# 2026-07-06 全仓"未使用资产"审计与处置路线图

> 状态：审计完成；**等待用户 review 后再决定走哪条处置路径**
> 关联 spec：黄金页 V2 (`2026-07-06-gold-allocation-page-v2-design.md`)
> 审计范围：`trading-system-codex/app/{services,api,static,schemas}` + 部署文件 + tests

## 0. 一句话总结

仓库存在**两个相反方向的未使用资产**：

- 🟢 **可清理 ~6,600 行代码**（~12% 服务端 + ~59% CSS）— 零外部引用，确定是死代码或前代 UI 残留
- 🟡 **~3,000 行可启用的"已写好但未触达"代码**（黄金 V2 引擎、monitoring decision-brief、structure bundle 5 字段只用 2 字段等）— 后端完整、前端只缺 UI

**建议**：先做"立即清理"（纯收益），再分批做"启用资产"（分页 V2 升级，复用现有后端与 CSS）。

---

## 1. 后端 service 处置分类（来自域 A 报告）

| 处置 | 数量 | 行数 | 备注 |
|---|---|---|---|
| 🟢 **可安全删除** | **8 个** | **~1,105 行** | signal_service、confidence_engine、monitoring_source_catalog、translation/cache、page_cache、data_quality、macro/healthcheck、strategy_unified/contracts（误判见注） |
| 🟡 **需前端补 UI** | **1 个** | **103 行** | monitoring_decision_review（`/monitoring/decision-brief/history` 后端完整） |
| 🟠 **内部支撑（保留）** | 18 个 | ~6,822 行 | monitoring_dashboard、terminal_summary_engine、strategy_unified/*、strategy_signal/snapshot_builder 等 |
| 🔴 **暂时保留** | 2 个 | ~341 行 | data_quality（测试依赖）、macro/healthcheck（CLI） |
| **总涉及** | — | **~11,245 行** | 占后端 53,943 行的 **20.8%** |

**🟢 可立即删除清单**：

1. `app/services/signal_service.py` (322) — 注释自承 "Legacy kept for compatibility"
2. `app/services/confidence_engine.py` (656) — 0 hits，功能被 `strategy_signal/confidence_dimensions.py` 覆盖
3. `app/services/monitoring_source_catalog.py` (100) — 常量字典，0 引用
4. `app/services/translation/cache.py` (140) — `TranslationCacheStore` 类 0 命中
5. `app/services/page_cache.py` (67) — `PageCacheService` 类 0 命中，功能已被 `cache_registry.py` 完成
6. `app/services/data_quality.py` (98) — 仅 2 个测试 import，**删前需同步测试**
7. `app/services/macro/healthcheck.py` (121) — CLI 脚本（`__main__`），仅 1 个测试 import 私有函数
8. `app/services/strategy_unified/contracts.py` (438) — 归类争议，最终归为 🟠 内部支撑（unified_service.py 真实使用其中 4 个函数）

**🟡 唯一产品决策点**：
- `monitoring_decision_review.py` (103) → endpoint `/monitoring/decision-brief/history` 完整，但前端 0 引用 → 决策：建 UI 还是删 endpoint？

## 2. API 端点处置分类（来自域 B 报告）

| 处置 | 数量 | 备注 |
|---|---|---|
| 🟢 **可安全删除** | **13 个** | 见下表 |
| 🟡 **需前端补 UI / 删 endpoint（产品决策）** | 6 个 | 见下表 |
| 🟠 **内部/运维端点（保留）** | 4 个 | `/health/ready`、`/marketevents` 别名、translation sync 端点 |
| 🔵 **别名/兼容端点（保留）** | 4 个 | `/etf/*` 兼容路径 |
| 🔴 **暂时保留** | 1 个 | `/strategy/decision` — 证据不足 |

**🟢 可立即删除清单**（共 13 个 endpoint）：

| METHOD | 路径 | 来源 | 证据 |
|---|---|---|---|
| GET | `/health` | health.py:8 | docker-compose / Dockerfile / 前后端 0 引用 |
| GET | `/health/live` | health.py:24 | 同上 |
| POST | `/auth/login` | auth.py:15 | single_user_mode 跳过，前端 0 引用 |
| GET | `/auth/me` | auth.py:49 | 同上 |
| POST | `/market-prices/marks` | market_prices.py:36 | 仅写用，前端无入口 |
| GET | `/market-prices/candles` | market_prices.py:68 | 前端走 `/marketdata/candles` 别名 |
| GET | `/market-prices/providers/gateio/time` | market_prices.py:97 | 0 引用 |
| GET | `/market-prices/cache/marks/latest` | market_prices.py:106 | 前端走非 cache 路径 |
| GET | `/market-prices/cache/book-ticker/latest` | market_prices.py:124 | 0 引用 |
| GET | `/market-prices/cache/candles/latest` | market_prices.py:143 | 0 引用 |
| DELETE | `/indicators/policies/{id}` | indicators.py:172 | 0 引用（POST/GET 配套也都在 🟡） |
| POST | `/market-events` | market_events.py:63 | 前端走 `/marketevents` 别名 |
| GET | `/alerts/final-decision` | monitoring.py:411 | bundle 已含，前端 0 独立调用 |

**🟡 产品决策点**（6 个 endpoint，建 UI 还是删？）：

1. `POST /indicators/calculate` (indicators.py:29) — 与 `/indicators/refresh` 功能重叠
2. `GET /indicators/raw` (indicators.py:81) — 前端 0 引用
3. `GET /indicators` (indicators.py:99) — 前端 0 引用（用 `observations`）
4. `GET /indicators/catalog` (monitoring.py:151) — 前端 0 引用
5. `GET /indicators/monitoring-policies` (monitoring.py:299) — 前端 0 引用
6. `GET /alerts/rules` (monitoring.py:310) — 前端 0 引用
7. `GET /monitoring/decision-brief/history` (monitoring.py:498) — 见上节 service
8. `POST /monitoring/risk-evaluate` (monitoring.py:541) — 测试依赖，无前端 UI
9. `POST /strategy/decision/snapshot` (strategy.py:201) — 别名，与 `/strategy/signals` 重叠
10. `POST /strategy/refresh` (strategy.py:140) — `api.refreshStrategyBundle` 声明但未调
11. `GET /bootstrap/seed` (bootstrap.py:16) — `api.seedDemo` 声明但未调

> 上述 6 个是**真正需要用户决策**的（每条 = "建 UI" 或 "删 endpoint" 二选一）。

## 3. CSS 孤儿类分类（来自域 C 报告）

| 处置 | 数量 | 估算行数 |
|---|---|---|
| 🟢 **可安全删除** | **261 个类** | **~5,500 行**（~59% of styles.css） |
| 🟡 **已知即将启用（黄金 V2 spec）** | 24 个 | 0 额外 |
| 🟠 **可能是别名/兼容** | 4 个 | 0 额外 |
| 🔴 **暂时保留** | 0 个 | — |

**按前缀统计 🟢 可删**：

| 前缀 | 数量 | 备注 |
|---|---|---|
| `.macro-` | 60 | 大量 V1 命名错配（如 `.macro-month-grid` vs 实际用的 `.calendar-grid`） |
| `.strategy-` | 56 | 全部 V1 类（V1.7 已迁 V2 命名） |
| `.structure-` | 42 | V1 detail/diagnostics 全死 |
| `.monitoring-` | 25 | `.monitoring-pane*` V1 命名（V2 用 `panel`） |
| `.analysis-` | 25 | V1 残留 |
| `.etf-` | 24 | 剔除动态生成的 `.etf-positive/-negative` |
| `.btc-` | 16 | 旧版密度变体（实际由后端 chart_layout 注入） |
| `.gold-` | 13 | 其他（非 V2 spec 启用） |

**关键发现 1：宏观日历整组命名错配**
- `styles.css:683-820` 定义 `.macro-month-grid/.macro-month-day.*` 整组
- 但 `macro_calendar.js:92-123` 实际用 `.calendar-day/.calendar-grid/.calendar-dot`（line 2511-2556）
- 137 行可安全删除

**关键发现 2：OR 兼容 selector 风险**
- `.strategy-plan-card` 与 `.strategy-overview-card` 共用 selector
- `.strategy-plan-card` 在 `renderTradePlans.js:35` 实际使用，删除需先解 selector 合并

**关键发现 3：动态生成类的识别**
- `.btc-card-span-{4,6,8,12}` / `.btc-chart-density-{hero,standard,compact,surface}` 由后端 `chart_builder.py` 注入
- `.etf-state-color--{on-target,off-target,...}` 由 `etfStateTextClass()` 动态产出
- 这些**必须保留**（看似孤儿实则动态生成）

## 4. 前端 page 升级价值评估（来自域 D 报告）

| page | 行数 | API 数 | 处置 | ROI |
|---|---|---|---|---|
| `structure.js` | 1240 | 2 | 🟢 **强烈推荐升级** | **高** |
| `gold_allocation.js` | 468 | 2 | 🟢 **强烈推荐升级** | **高**（V2 spec 已就绪） |
| `monitoring.js` | 1192 | 4-6 | 🟡 谨慎升级 | 中 |
| `alerts.js` | 780 | 3 | 🟡 谨慎升级 | 中 |
| `ashare_etf.js` | 538 | 3 | 🟠 当前合适 | 低 |
| `macro_calendar.js` | 270 | 2 | 🔴 不推荐 | 极低 |

**🟢 强烈推荐 — 升级理由**：

#### structure.js（1240 行 / 2 API）
- 后端 `/structure/tab/bundle` 返回 **5 字段** (`snapshot / candles / events / alerts / diagnostics`)
- 前端**只消费 snapshot + candles**，完全忽略 events / alerts / diagnostics
- 升级方向（无需新 API，纯显示）：
  1. 加 `bundle.events` 时间线侧栏
  2. 加 `bundle.alerts` chip 列表
  3. 加 `bundle.diagnostics` 一行小字带 tooltip

#### gold_allocation.js（468 行 / 2 API）
- 已有 V2 spec（`2026-07-06-gold-allocation-page-v2-design.md`，方案 B 锁定）
- 升级方向（spec 已明列）：V2 决策带 + 7 模块卡 + 2 趋势图 + 保留执行子区块

---

## 5. 处置路线图（按风险/收益排序）

### 🟢 第 1 梯队 — 立即清理（纯收益，零风险）

**子项 1A — 死代码删除**（2-3 小时）
- 删 7 个 service（保留 `data_quality.py` 等带测试的 2 个到子项 1B 处理）
- 删 13 个孤儿 endpoint
- 改对应的 `__init__.py` 导出
- 改对应的 `api/router.py` 装配
- 跑全套 pytest 验证

**子项 1B — 测试与死代码同步**（1 小时）
- 同步删除 `tests/test_data_quality_and_decision.py` 和 `tests/test_chip_structure.py` 中对 `data_quality.py` 的 import
- 删除 `data_quality.py` 和 `macro/healthcheck.py`
- 跑测试

**子项 1C — CSS 孤儿类清理**（2-3 小时）
- 删 261 个孤儿类（~5,500 行）
- **保留**：黄金 V2 spec 启用的 24 个、OR 兼容 selector 中的活类（`.strategy-plan-card`）、动态生成类
- 跑静态分析 + 视觉冒烟（开每个 page 走一遍）

### 🟡 第 2 梯队 — 启用资产（4-8 小时，分多次 PR）

**子项 2A — 黄金页 V2 实施**（已锁定，~6-8 小时）
- 入口 spec: `2026-07-06-gold-allocation-page-v2-design.md`
- 重写 `gold_allocation.js` 468→~1100-1200 行
- 启用 styles.css 7868-8495 行的 24 个 `gold-` 类
- 扩展 `test_gold_frontend_static.py`

**子项 2B — structure.js 启用 bundle events/alerts/diagnostics**（~2-3 小时）
- 解包 `bundle.events` 时间线侧栏
- 加 `bundle.alerts` chip
- 加 `bundle.diagnostics` tooltip

### 🔵 第 3 梯队 — 产品决策（需用户回复）

| 决策项 | 选项 |
|---|---|
| `monitoring_decision_review` + `/monitoring/decision-brief/history` | A. 建 monitoring 历史时间线 / B. 删 endpoint + service |
| `/indicators/calculate` vs `/indicators/refresh` | A. 保留两个（计算 vs 刷新） / B. 合并 / C. 都删 |
| `/alerts/final-decision` 独立 endpoint | A. 保留（管理面板用） / B. 删（bundle 已含） |
| `POST /strategy/refresh` 声明未调 | A. 删 api wrapper / B. 加 strategy 页刷新按钮 |
| `GET /bootstrap/seed` 声明未调 | A. 删 / B. 加演示数据按钮 |
| `GET /strategy/decision` 证据不足 | A. 问团队 / B. 删 |

### 🔴 第 4 梯队 — 不推荐

- `ashare_etf.js` 升级 — 任务本质决定 3 API 足够
- `macro_calendar.js` 升级 — 月历场景 2 API 合理

---

## 6. 风险与回滚

| 阶段 | 风险 | 回滚方式 |
|---|---|---|
| 1A-1C 清理 | 漏改 `__init__.py` 导出导致循环 import | 单次提交，单文件 revert |
| 1B 测试同步 | 测试发现 `data_quality.py` 还有价值 | 恢复服务+调整测试 |
| 2A 黄金 V2 | 后端 `facts`/`warnings` 字符串含占位 | 接受现状，按既有行为展示 |
| 2B structure | bundle 字段可能缺数据 | 字段缺时降级为占位 |
| 3 产品决策 | 误删被未来功能依赖的 endpoint | 4 周观察期，git revert 即可 |

---

## 7. 不在本审计范围

- 移动端响应式问题
- i18n 翻译覆盖率
- 数据库 schema 死表/死列
- 性能 profile（独立任务）
- 安全审计（独立任务）

---

## 8. 决策记录

| 决策 | 默认建议 | 用户 override |
|---|---|---|
| 是否做第 1 梯队清理？ | ✅ 建议 | (待定) |
| 是否做黄金 V2 实施？ | ✅ 已有 spec | (待定) |
| 是否做 structure.js 启用？ | ✅ 建议（最高 ROI） | (待定) |
| 第 3 梯队 6 项产品决策 | 询问团队 | (待定) |
| 第 4 梯队 | ❌ 不做 | (待定) |
