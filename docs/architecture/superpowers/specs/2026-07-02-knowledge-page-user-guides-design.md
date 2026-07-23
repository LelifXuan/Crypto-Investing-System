# 知识百科：页面级用户指南 — 设计 Spec

- **Date**: 2026-07-02
- **Branch**: `main`
- **Status**: Design approved, awaiting user review → writing-plans

## 1. Problem Statement

### 1.1 现状
知识百科页（`/knowledge-page`）当前是**纯术语词典**：
- `app/static/core/knowledge.js:23-46` 定义 `term(id, label, options)` 工厂
- 70+ 词条、7 段（技术指标/形态结构/告警筹码/宏观/数据质量/A股ETF/BTC衍生品）
- 卡片默认只显示 `term + summary + tags + 展开按钮`
- 展开后看 8 个字段（`definition / why_it_matters / formula / how_to_use / useful_when / thresholds / risk_note / example`）
- 后端只是空壳路由 `/knowledge-page` (`app/web/router.py:104-106`)，全部内容在前端常量

### 1.2 用户反馈
"目前的知识百科页还不足以成为本系统的说明书一样的指引文本"

→ 需要把"术语词典"扩展为"**术语词典 + 页面使用指南**"的双结构。

### 1.3 设计目标
1. 用户打开任意页面卡住时，能在百科里找到对应页面的"何时看、看什么、如何解读"
2. 每个页面指南都是结构化的：purpose / when-to-use / walkthrough / data-lineage / caveats
3. 与现有术语词典不破坏 — 7 段术语 + 新增 1 段页面指南
4. 跨页 tooltip 仍工作（保留 `findKnowledgeTerm` API）

---

## 2. Architecture

### 2.1 系统边界
- **本次改动仅前端**（无后端 schema 改动、无 DB schema 改动）
- 新增字段全部 optional，向后兼容
- 现有 70+ term 条目不受影响（无字段必填）

### 2.2 数据流
```
User opens /knowledge-page
       ↓
SPA → renderKnowledge() in pages/knowledge.js
       ↓
build allSections (新增 pageGuides 段)
       ↓
for each item in pageGuides:
  item.type === "guide"
    → renderGuideCard(item) (新组件)
    → 使用 callout 样式 + 默认展开
   else (existing):
    → renderTermCard(item) (现有)
       ↓
用户看到术语 + 指南两套卡片；术语默认收起、指南默认展开
```

### 2.3 关键设计决策
1. **复用 `term()` 工厂**（不新建第二个工厂）—— 通过 `type: "guide"` 区分，渲染层根据 type 选模板
2. **指南内容放在 `knowledge.js` 配置里**（不是单独 markdown 文件）—— 与现有模式一致，发布流程不变
3. **第一批只做 3 篇指南**（monitoring-overview / ai-strategy / btc-derivatives）—— 验证 schema/template，剩余 6 篇（market-analysis / market-structure / market-events / macro-calendar / ashare-etf / gold-allocation）后续单独跟进
4. **不创建独立页面**（避开顶部 nav 多一个 tab 的影响）—— 全部塞进 `/knowledge-page` 现有入口

---

## 3. Components

### 3.1 Schema 扩展 (`app/static/core/knowledge.js`)

**term() 工厂新增字段**（默认值为空，opt-in）：

| 字段 | 类型 | 默认 | 用途 |
|---|---|---|---|
| `type` | `"term" \| "guide"` | `"term"` | 决定渲染模板 |
| `purpose` | string | `""` | 一句话说明页面做什么 |
| `when_to_use` | string[] | `[]` | 何时打开这个页面 |
| `page_walkthrough` | string[] | `[]` | 进入后按顺序看什么 |
| `data_lineage` | string[] | `[]` | 上游数据按管线顺序 |
| `caveats` | string[] | `[]` | 页面**不**展示什么 |
| `related_pages` | string[] | `[]` | 关联的 page_ids（如 `ai-strategy`, `monitoring-overview`） |

**所有新字段 optional**——现有 70+ term 条目不需要任何修改。

### 3.2 新增 `pageGuidesSections`（在 `knowledge.js:1389` 附近）

```js
const pageGuidesItems = [
  term("monitoring-overview", "监控总览使用指南", {
    type: "guide",
    purpose: "在 5 分钟早盘或重大事件前，快速判断当前市场风险敞口。",
    when_to_use: [
      "早盘 (UTC 0:00 / 北京 8:00) 复盘上一日收盘",
      "FOMC、CPI、非农等重大宏观事件前后",
      "BTC 单日波动 >5% 需要快速定位原因时",
    ],
    page_walkthrough: [
      "顶部 'Terminal Summary' - 三行核心简报 (市场/指引/风险)",
      "中间 'Macro Overview' - 6 层宏观评分 (rates/inflation/labor/...)",
      "下方 'Alert Events' - 当前未平仓事件窗口",
    ],
    data_lineage: [
      "MacroOverviewService → macro_overview",
      "MonitoringDashboardService → 事件聚合",
      "IndicatorMonitoringService → 实时 cache",
    ],
    caveats: [
      "不展示 tick-level 数据",
      "15 分钟内缓存可能与实时有秒级偏差",
    ],
    related_pages: ["ai-strategy", "btc-derivatives", "macro-calendar"],
    tags: ["guide", "monitoring"],
  }),
  // ai-strategy, btc-derivatives 类似...
];

const pageGuidesSection = {
  id: "page-guides",
  title: "页面使用指南",
  description: "每个页面的使用时机、阅读顺序、数据依赖与注意点",
  items: pageGuidesItems,
};
```

需要把 pageGuidesSection 加到 `knowledgeSections` 数组。

### 3.3 渲染层 (`app/static/pages/knowledge.js`)

**新增 `renderGuideCard(item)`** 与现有 `renderTermCard(item)` 并列：

- 标题旁加 `📘 使用指南` 角标
- **默认展开**所有字段（与 term 卡片相反）
- 字段分 4 区块，**callout 颜色**：
  - 蓝色区块：purpose + when_to_use（"何时用"）
  - 绿色区块：page_walkthrough（"看什么顺序"）
  - 橙色区块：data_lineage（"数据从哪来"）
  - 红色区块：caveats（"不展示什么"）
- 底部一行 button："前往此页面 →" 链到 `appState.PAGE_TITLES["<id>"]` 对应的 `/<id>-page` 路由

**在 `renderKnowledgeLayout` 的 `filteredSections` 输出**自动包含 `pageGuidesSection`（与术语段落同流程）。

**section chips**也加入"📘 页面指南"快速跳转 chip（与现有 7 个并列）。

### 3.4 样式 (`app/static/styles.css`)

追加 `~80 行` 新样式：
- `.knowledge-guide-card` — 与 `.knowledge-v2-card` 同结构但默认展开
- `.knowledge-guide-purpose` — 蓝色 callout
- `.knowledge-guide-walkthrough` — 绿色 callout + `<ol>` 列表
- `.knowledge-guide-lineage` — 橙色 code-style 列表
- `.knowledge-guide-caveats` — 红色 callout
- `.knowledge-guide-tag` — 📘 角标

### 3.5 测试 (`tests/test_knowledge_catalog.py`)

**新增**：
- `test_page_guides_required_fields`：每个 `type="guide"` 条目必须包含：`purpose` 长度 ≥ 10 / `when_to_use` 至少 1 项 / `page_walkthrough` 至少 2 项 / `data_lineage` 至少 1 项 / `caveats` 至少 1 项 / `related_pages` 至少 1 项
- `test_three_core_pages_have_guides`：monitoring-overview / ai-strategy / btc-derivatives 三个页面必须有 guide
- `test_guide_related_pages_reference_existing_pages`：`related_pages` 值必须是已知 `PAGE_TITLES` key

**不修改**：
- `test_knowledge_catalog_schema_seed_terms_and_utf8`（现有 term 约束）
- `test_knowledge_alias_lookup_normalizes_common_variants`
- `test_tooltip_is_concise_and_links_to_knowledge`
- `test_btc_derivatives_terms_are_available_to_dashboard_tooltips`

---

## 4. Data Flow Details

### 4.1 完整 schema 示例 (monitoring-overview guide)

```json
{
  "id": "monitoring-overview",
  "term": "监控总览使用指南",
  "aliases": ["monitoring-guide", "monitoring-overview-guide"],
  "category": "guide",
  "family": "user-guide",
  "level": "basic",
  "display_mode": "full",
  "importance": "core",
  "type": "guide",
  "purpose": "在 5 分钟早盘或重大事件前，快速判断当前市场风险敞口。",
  "when_to_use": [
    "早盘 (UTC 0:00 / 北京 8:00) 复盘上一日收盘",
    "FOMC、CPI、非农等重大宏观事件前后",
    "BTC 单日波动 >5% 需要快速定位原因时"
  ],
  "page_walkthrough": [
    "顶部 'Terminal Summary' - 三行核心简报",
    "中间 'Macro Overview' - 6 层宏观评分",
    "下方 'Alert Events' - 当前事件窗口"
  ],
  "data_lineage": [
    "MacroOverviewService.build_overview() → macro_overview",
    "MonitoringDashboardService.get_bundle() → terminal_summary",
    "IndicatorMonitoringService.sync_*() → monitoring_dashboard"
  ],
  "caveats": [
    "不展示 tick-level 数据",
    "15 分钟内缓存可能与实时有秒级偏差",
    "宏观事件窗口在事件结束后 5 分钟内可能显示 'pre_event'"
  ],
  "example": "",
  "page_refs": ["monitoring-overview"],
  "related_terms": ["terminal_summary", "macro_overview", "alert_events"],
  "related_pages": ["ai-strategy", "btc-derivatives", "macro-calendar"],
  "tags": ["guide", "monitoring"]
}
```

### 4.2 3 篇首批指南清单

| id | 关联 page_refs | 预估字数 |
|---|---|---|
| `monitoring-overview` | monitoring-overview | ~250 |
| `ai-strategy` | ai-strategy | ~350 |
| `btc-derivatives` | btc-derivatives | ~280 |

### 4.3 用户在 /knowledge-page 看到的 UI

```
顶部 hero
  ↓
三张 metric 卡：目录版本 / 词条总数 / 当前匹配
  ↓
5 项过滤工具栏（与现有完全一致）
  ↓
7 个 section chips + 新增 "📘 页面指南" chip
  ↓
[术语词典 7 段] (现有)
  - 默认收起，点"展开详情"看 8 字段
[页面指南 1 段] (新)
  - 默认展开
  - 4 区块 callout: 何时用 / 看什么 / 数据从哪来 / 注意点
  - 底部"前往此页面 →"按钮
```

---

## 5. Error Handling

| 失败场景 | 行为 |
|---|---|
| `purpose`/`when_to_use` 等字段缺失 | 渲染时该区块隐藏，无 JS 错误 |
| `related_pages` 引用未知 page_id | 不出现"前往此页面"按钮，仅作为文本相关引用 |
| 用户清空所有过滤 | "📘 页面指南"段仍展示所有 guide |
| 跨页跳转（点击"前往此页面 →"）| 标准 SPA 路由跳转，行为与导航一致 |

---

## 6. Testing Strategy

### 6.1 单元测试（pytest + Node ESM eval）
- `tests/test_knowledge_catalog.py` 新增 3 个测试
  - `test_page_guides_required_fields`
  - `test_three_core_pages_have_guides`
  - `test_guide_related_pages_reference_existing_pages`

### 6.2 视觉验证
- 启动 backend → 访问 `/knowledge-page`
- 确认 "📘 页面指南" 段显示 3 张卡片，默认展开，含 4 区块
- 过滤工具栏关键词（如 "strategy"）能正确筛出 ai-strategy guide

### 6.3 回归
- 现有 70+ term 条目不受影响（schema optional）
- 跨页 tooltip（`knowledgeTooltip`）正常工作
- `findKnowledgeTerm()` API 仍可被其它页面调用

---

## 7. Backward Compatibility

- ✅ 所有新字段 optional，老 term 条目无 breaking change
- ✅ `term()` 工厂默认值兼容，老的 70+ term 仍然能工作
- ✅ `knowledge.js:1390-1455` 现有 lookup/search API 不变
- ✅ 测试 `test_knowledge_catalog.py` 现有 4 个测试不受影响
- ✅ 跨页 tooltip（`dom.js:213-217`）调用 `findKnowledgeTerm`，仍能找到 type="term" 的条目

---

## 8. Files Affected

### 修改
- `trading-system-codex/app/static/core/knowledge.js` — term() 工厂 + 新增 `pageGuidesSections` + 3 篇 guide 条目
- `trading-system-codex/app/static/pages/knowledge.js` — `renderGuideCard()` + section chips + 过滤兼容
- `trading-system-codex/app/static/styles.css` — guide 样式
- `trading-system-codex/tests/test_knowledge_catalog.py` — 3 个新测试

### 新增
无（全部在已有文件里扩展）

---

## 9. Out of Scope

- 不写其余 6 篇 guide（market-analysis / market-structure / market-events / macro-calendar / ashare-etf / gold-allocation）—— 留作后续单独 spec
- 不修改跨页 tooltip 的视觉
- 不创建新的独立页面或顶部 nav tab
- 不支持 markdown 渲染（保持 JS 配置风格）
- 不更新现有 term 条目以填充 `related_pages`（保留向后兼容）

---

## 10. Open Questions

None — design approved by user.