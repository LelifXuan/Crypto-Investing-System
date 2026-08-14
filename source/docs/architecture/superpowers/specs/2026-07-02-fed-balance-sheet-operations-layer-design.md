# Fed Balance Sheet Operations Layer — Design Spec

- **Date**: 2026-07-02
- **Branch**: `main`
- **Status**: Design approved, awaiting user review → writing-plans

## 1. Problem Statement

### 1.1 现状
`MacroOverviewService.build_overview()` (`app/services/macro_overview.py`) 当前有 6 层：
1. `rates_policy` (Fed Funds Rate 政策利率)
2. `inflation` (CPI/PCE/breakevens)
3. `labor_market` (NFP/unemployment/claims)
4. `liquidity_credit` (4 个 Fed BS 指标 + HY/IG spreads)
5. `cross_asset_confirmation` (spx/qqq/dxy/etc)
6. `event_window` (FOMC calendar)

`macro_indicator_api_map.v1.json` 有 44 个 indicators，**只有 4 个直接绑定 Fed 资产负债表**：
- `fed_balance_sheet`
- `bank_reserves`
- `reverse_repo`
- `tga`

### 1.2 问题
**美联储实际在做的是 BS 操作（QE/QT/回购工具），但其监测面板只显示"政策目标"（CPI/NFP/Fed Funds Rate）**。关键操作类指标缺失：
- **Tier 1（高优先，必须加）**：IORB / ON RRP rate / SOMA 分解 / SRF 使用 / Discount Window / BTFP
- **Tier 2（高价值，公式/算法衍生）**：SOMA 持仓平均久期 / TGA 净变动 / 净流动性（运行时计算）/ FIMA / QT cap

这意味着系统能"测温"（CPI/NFP/PMI）但不能"测压"（银行挤兑、TGA 抽水、回购工具激活）。

### 1.3 设计目标
1. 新增第 7 层 `fed_operations`，专门追踪 Fed BS 操作（直接面板 + 衍生指标）
2. **运行时计算** 衍生指标（net liquidity = reserves - RRP - TGA），不改数据层
3. 新增 ~10 个 Tier 1+2 指标到 `macro_indicator_api_map.v1.json` + `macro_scoring_registry.v1.json`
4. 知识百科新增 3-4 个概念词条（IORB corridor / Net liquidity / SOMA / 回购工具）

---

## 2. Architecture

### 2.1 系统边界
- **新增层 + 新增配置**（不重构现有 6 层）
- Tier 1 指标（6 个）添加到 `macro_indicator_api_map.v1.json` + `macro_scoring_registry.v1.json`
- Tier 2 指标（4 个）— 3 个新数据 + 1 个（net_liquidity）前端运行时计算
- 新增 `fed_operations` 层到 `macro_overview.py`
- 新增 3-4 个 `term()` 条目到 `knowledge.js`
- 不动现有 liquidity_credit 层的 4 个 Fed BS 指标

### 2.2 数据流
```
IndicatorMonitoringService.sync_fed_operations()
       ↓  写入 indicator_observations (新 indicators)
MacroOverviewService.build_overview()
       ↓
   fed_operations layer
       ↓
   调 scoring_engine 评估每个新指标
       ↓
   输出 layer score (0-100)
       ↓
MacroOverviewResponse.fed_operations = LayerRead(...)
       ↓
前端 macro 页面显示新层（"7. Fed Operations"）
       ↓
前端 knowledge page 显示新词条（IORB corridor 等）
```

### 2.3 关键设计决策
1. **新增第 7 层 `fed_operations`**（用户选择）— 不动现有 6 层
2. **Tier 2 net_liquidity 运行时计算**（用户选择）— 不存数据库
3. **不重命名现有 liquidity_credit 层**（保持向后兼容）
4. **新数据源 FRED**（已有 macro_provider 集成）— 无后端代码改动，只需配置
5. **新 scoring formula 复用现有公式**（`direct_linear` / `inverse_linear` / `range_mid` / `display_only`）

---

## 3. Components

### 3.1 配置层 (`app/monitoring/configs/macro_indicator_api_map.v1.json`)

新增 10 个 indicator entries（Tier 1: 6 + Tier 2 原始数据: 3 + 1 衍生）：

| indicator_key | 监测内容 | FRED series | tier |
|---|---|---|---|
| `fed_iorb` | IORB（利率走廊上限） | `IOER` 或 `IORB` | 1 |
| `fed_on_rrp_rate` | ON RRP rate（利率走廊下限） | `RRPONTSYAWARD` | 1 |
| `fed_soma_treasury` | SOMA 持有国债 | `WSHOMCB` 或 `WTREGEN` | 1 |
| `fed_soma_mbs` | SOMA 持有 MBS | `WSFSEAML` | 1 |
| `fed_srf_usage` | Standing Repo Facility 使用 | `RPTSYD` 或 `RRPTSYD` | 1 |
| `fed_discount_window` | Discount Window 借款 | `WLCFLPCL` 或 `DPDCBS` | 1 |
| `fed_soma_avg_duration` | SOMA 持仓平均久期 | `WSHOMAVERAGE` 或计算 | 2 |
| `fed_tga_net_change_4w` | TGA 4 周净变动（衍生） | WTREGEN 滚动 4w | 2 |
| `fed_fima` | FIMA Repo Pool（外国央行 RRP） | `WLFNARIAL` | 2 |
| `fed_qt_cap` | QT 月度 cap（衍生） | Treasury 公告 | 2 |

`net_liquidity` 不在此表（运行时计算）。

### 3.2 Scoring 层 (`app/monitoring/configs/macro_scoring_registry.v1.json`)

每个新 indicator 配一个 entry：

```json
{
  "indicator_key": "fed_iorb",
  "aliases": ["iorb", "interest_on_reserve_balances"],
  "formula_id": "inverse_linear",
  "unit": "%",
  "thresholds": {"low": 4.0, "high": 5.5},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "Fed 利率走廊上限宽松",
  "bearish_label": "Fed 利率走廊上限偏紧"
}
```

Scoring 公式（`higher_value_bias`）：
- `iorb` / `on_rrp_rate` / `qt_cap` / `tga_net_change_4w`：inverse_linear（高 = 利空）
- `soma_treasury` / `soma_mbs` / `soma_avg_duration` / `fima`：direct_linear（高 = 利好，BS 扩张）
- `srf_usage` / `discount_window`：inverse_linear with `display_only` 显示（高 = 危险，但仅供警示，不打分）

### 3.3 Layer 层 (`app/services/macro_overview.py`)

在 `LAYER_LABELS` (现 6 层) 中新增第 7 层：

```python
LAYER_LABELS = {
    ...
    "liquidity_credit": {"label_cn": "流动性与信用", "indicators": [...]},
    "fed_operations": {
        "label_cn": "Fed 资产负债表操作",
        "indicators": [
            "fed_balance_sheet", "bank_reserves", "reverse_repo", "tga",  # 已有 4 个
            "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
            "fed_srf_usage", "fed_discount_window",
            "fed_soma_avg_duration", "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
        ],
    },
    "cross_asset_confirmation": {...},
    "event_window": {...},
}
```

注：4 个已有 BS 指标从 `liquidity_credit` 移到 `fed_operations`（更准确）。`liquidity_credit` 保留 HY/IG/spreads/M2 等非 Fed 指标。

### 3.4 前端运行时计算 — `net_liquidity`

在 `app/static/pages/knowledge.js` 或新的 `app/static/core/macro_derived.js`：

```js
// 在前端从 layer.fed_operations 指标列表中提取并计算
function computeNetLiquidity(indicators) {
  const find = (key) => indicators.find(i => i.indicator_key === key);
  const reserves = find('bank_reserves')?.value_num;
  const rrp = find('reverse_repo')?.value_num;
  const tga = find('tga')?.value_num;
  if (reserves == null || rrp == null || tga == null) return null;
  return reserves - rrp - tga;
}
```

在 `monitoring-overview` 页面顶部显示 `net_liquidity: $X.X Tn`（带历史趋势小图）。

### 3.5 知识百科新增 4 个词条

`app/static/core/knowledge.js` 新增：

| term id | term | 一句话 |
|---|---|---|
| `fed_balance_sheet_operations` | 资产负债表操作 | 实际 Fed 政策工具 |
| `iorb_corridor` | IORB / ON RRP 利率走廊 | Fed 通过此走廊控制短端利率 |
| `net_liquidity` | 净流动性 | Reserves - RRP - TGA，crypto 牛熊分水岭 |
| `standing_repo_facility` | Standing Repo Facility / Discount Window | 银行系统压力的早期信号 |

放在现有 `dataQualityItems` 或新 `fedOperations` family 中。

### 3.6 测试 (`tests/test_fed_operations_layer.py` 新增)

1. `test_fed_operations_layer_in_macro_overview` — 第 7 层存在
2. `test_10_new_indicators_in_api_map` — 配置文件含 10 个新 entry
3. `test_4_existing_bs_indicators_moved_to_fed_operations` — liquidity_credit 不再有这 4 个
4. `test_net_liquidity_calculation_correct` — 前端计算正确性
5. `test_fed_operations_scoring_not_broken` — 新指标不破坏现有 layer 评估

---

## 4. Data Flow Details

### 4.1 新增 layer 形状

```json
"fed_operations": {
  "layer_key": "fed_operations",
  "label_cn": "Fed 资产负债表操作",
  "score": 55,
  "bias": "中性偏紧",
  "indicators": [
    {
      "indicator_key": "fed_balance_sheet",
      "value_num": 7100000.0,  // $7.1T
      "value_text": "$7.10T",
      "score": 60,
      "bias": "扩张中",
      "is_scored": true,
      "freshness_state": "fresh"
    },
    // ... 13 个指标
  ],
  "summary": "Fed BS 缩表中，IORB 5.40% 紧但 ON RRP 5.25% 走廊完整，净流动性 $2.5T 偏低"
}
```

### 4.2 监控总览页面渲染

前端 `monitoring-overview` 页面 `macro_overview` 区块下：
- 现有 6 层
- **新增第 7 层 "Fed 资产负债表操作"**
- 每层显示 score + 关键指标 (3 个)，可展开看全部
- 顶部新增 **Net Liquidity 卡片**（运行时计算）

### 4.3 衍生指标 net_liquidity 计算细节

```js
// 三种状态：
// - 完整数据：显示 "净流动性: $X.X Tn" + 历史趋势
// - 部分缺失：显示 "净流动性: 数据不完整" + 列出缺失的子指标
// - 完全缺失：隐藏卡片
```

### 4.4 Knowledge 词条示例

```js
term("iorb_corridor", "IORB / ON RRP 利率走廊", {
  category: "monetary",
  family: "fed-operations",
  level: "advanced",
  display_mode: "full",
  importance: "core",
  aliases: ["iorb", "interest_on_reserve_balances", "on_rrp_rate", "reverse_repo_rate"],
  definition: "Fed 通过 IORB（利率走廊上限）和 ON RRP rate（利率走廊下限）控制联邦基金利率。IORB 是银行放钱给 Fed 的利率，ON RRP rate 是市场（货币基金）放钱给 Fed 的利率。",
  why_it_matters: "当 IORB 接近 ON RRP rate 时，利率走廊坍塌，金融机构无利可图，流动性紧张。2008/2020/2023 都有此信号。",
  formula: "走廊宽度 = IORB - ON RRP rate。正常约 10-15 bp。",
  useful_when: ["FOMC 决议日", "回购市场异动", "货币基金 YTD 收益异常"],
  thresholds: ["走廊宽度 < 5 bp → 警告", "IORB - EFFR > 10 bp → 银行压力"],
  risk_note: "2023 年 3 月 SVB 危机时走廊从 +10 bp 收窄到 +5 bp，2 天后 BTFP 紧急启用。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["fed_balance_sheet_operations", "bank_reserves", "reverse_repo"],
  tags: ["monetary", "fed-operations", "corridor"]
})
```

---

## 5. Error Handling

| 失败场景 | 行为 |
|---|---|
| 某个新 indicator 数据缺失 | layer 评估仍能完成（其它指标正常） |
| FRED API 调用失败 | provider 已有 fallback，indicator 显示 `data_status=missing` |
| net_liquidity 任一子指标缺失 | 前端显示 "数据不完整"+ 列出缺失项 |
| 配置文件 JSON 错误 | 在 macro_overview service 启动时报错（已有 schema 校验） |
| 新 layer 不被前端识别 | 前端 `KNOWN_LAYERS` 列表需要同步更新 |

---

## 6. Testing Strategy

### 6.1 单元测试
- `tests/test_fed_operations_layer.py` (NEW) — 5 个测试
- 现有 macro overview / scoring engine 测试不应破坏

### 6.2 集成测试
- `tests/test_macro_overview.py` 验证 `fed_operations` 在响应里
- `tests/test_indicator_monitoring.py` 验证新 indicator key 被 sync 接受

### 6.3 端到端
- 启动 backend → `/monitoring-overview` 页面显示 7 层（含 fed_operations）
- 知识百科 `/knowledge-page` 显示 4 个新词条
- `net_liquidity` 卡片显示在 monitoring 顶部

### 6.4 回归
- 831 + 现有 11 个 V1.7.2 测试 = 842 passed
- Ruff 干净
- node --check JS 干净

---

## 7. Backward Compatibility

- ✅ 现有 6 层 macro overview 不破坏（fed_operations 是新增第 7 层）
- ✅ 现有 4 个 BS 指标 (`fed_balance_sheet`/`bank_reserves`/`reverse_repo`/`tga`) 从 `liquidity_credit` 移到 `fed_operations` — 这意味着 `liquidity_credit` 不再有它们
- ⚠️ 任何依赖 `liquidity_credit` 包含这 4 个的代码可能受影响 — 但前端 `macro_overview` 渲染只按 layer_key 迭代，无硬编码字段依赖
- ✅ 知识百科 70+ 词条无影响
- ✅ V1.7.2 页面指南（monitoring-overview）只列 layer 名（"macro_overview"），不指定具体指标 — 不需要更新

---

## 8. Files Affected

### 修改
- `app/monitoring/configs/macro_indicator_api_map.v1.json` — 加 10 个 indicator
- `app/monitoring/configs/macro_scoring_registry.v1.json` — 加 10 个 scoring entry
- `app/services/macro_overview.py` — 加 `fed_operations` 到 LAYER_LABELS
- `app/static/core/knowledge.js` — 加 4 个 term() 条目
- `app/static/pages/monitoring.js` 或类似 — 显示 fed_operations layer + net_liquidity 卡片

### 新增
- `tests/test_fed_operations_layer.py` — 5 个测试
- （可选）`app/static/core/macro_derived.js` — net_liquidity 计算

---

## 9. Out of Scope

- 不实现"过去 10 年历史回放"图表（高级功能）
- 不实现自动危机预警（需要 ML，超出范围）
- 不实现 BTFP 启用/停用自动检测（需要 Fed 公告解析）
- 不实现 SOMA 持仓详细分类（按 CUSIP）— 已有 SOMA Treasury/MBS 总量即可

---

## 10. Open Questions

None — design approved by user.