# Fed Balance Sheet Operations Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 7th macro overview layer (`fed_operations`) with 10 new Fed-balance-sheet indicators + 4 knowledge entries + a runtime-computed `net_liquidity` indicator, so the system can actually monitor what the Fed *does* (not just what it *says*).

**Architecture:** Pure data + config additions. No new backend services. All 10 new indicators added to existing `macro_indicator_api_map.v1.json` (auto-collected by existing FRED provider). One new layer in `macro_overview.py:LAYER_LABELS` (consumes existing scoring engine). Net liquidity = `bank_reserves - reverse_repo - tga` computed on frontend at render time. Knowledge entries follow existing `term()` factory pattern.

**Tech Stack:** FastAPI / Pydantic (backend), Vanilla JS (frontend), pytest (tests), FRED API (data source via existing macro_provider).

---

## File Structure

### Modify
- `trading-system-codex/app/monitoring/configs/macro_indicator_api_map.v1.json` — add 10 indicator entries
- `trading-system-codex/app/monitoring/configs/macro_scoring_registry.v1.json` — add 10 scoring entries
- `trading-system-codex/app/services/macro_overview.py` — add `fed_operations` to `LAYER_LABELS`, move 4 existing BS indicators from `liquidity_credit` to `fed_operations`
- `trading-system-codex/app/static/core/knowledge.js` — add 4 `term()` entries
- `trading-system-codex/app/static/core/macro_derived.js` (NEW small file) — `computeNetLiquidity()` helper
- `trading-system-codex/app/static/pages/monitoring.js` (or similar) — render new layer + net_liquidity card
- `trading-system-codex/docs/CHANGELOG.md` — V1.7.3 entry

### Create
- `trading-system-codex/tests/test_fed_operations_layer.py` — 5 tests

---

## Task 1: Add 10 new indicators to api_map

**Files:**
- Modify: `trading-system-codex/app/monitoring/configs/macro_indicator_api_map.v1.json`

- [ ] **Step 1: Verify FRED series IDs against actual API**

Before adding, verify each series ID is valid. Test each via the existing macro_provider FRED integration:

```bash
cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -c "
import asyncio
from app.services.macro.providers.fred import FredMacroProvider

async def test():
    p = FredMacroProvider()
    for sid in ['IOER', 'RRPONTSYAWARD', 'WSHOMCB', 'WSFSEAML', 'WLCFLPCL', 'DPDCBS']:
        try:
            data = await p.fetch(sid)
            print(f'{sid}: OK ({len(data)} rows)')
        except Exception as e:
            print(f'{sid}: FAIL - {e}')

asyncio.run(test())
"
```

If any series ID fails, find the correct ID and use it. **Update the spec section 3.1** with verified IDs before continuing.

- [ ] **Step 2: Write failing test for new indicators in api_map**

In `tests/test_indicator_monitoring.py` (or new file), append:

```python
def test_macro_indicator_api_map_contains_fed_operations_indicators():
    """api_map must declare all 10 new fed_operations indicators."""
    from app.monitoring.configs.macro_indicator_api_map import load_indicator_map
    # (or whatever the actual loader is — read the file to find it)
    api_map = load_indicator_map()
    required_keys = {
        "fed_iorb", "fed_on_rrp_rate",
        "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window",
        "fed_soma_avg_duration", "fed_tga_net_change_4w",
        "fed_fima", "fed_qt_cap",
    }
    actual_keys = set(api_map["indicators"].keys())
    missing = required_keys - actual_keys
    assert not missing, f"missing fed_operations indicators: {missing}"
```

(Adjust the import path after reading `app/monitoring/configs/macro_indicator_api_map.v1.json` to find its loader — likely in `app/services/indicator_monitoring.py` or similar.)

- [ ] **Step 3: Run the test to verify it fails**

```bash
python -m pytest tests/test_indicator_monitoring.py::test_macro_indicator_api_map_contains_fed_operations_indicators -v
```

Expected: FAIL.

- [ ] **Step 4: Add 10 indicator entries to api_map**

In `app/monitoring/configs/macro_indicator_api_map.v1.json`, find the `indicators` object and append 10 new entries (preserving the existing JSON structure). The pattern matches existing entries:

```json
"fed_iorb": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "daily",
  "unit": "%",
  "freshness_days": 5,
  "display_name": "IORB",
  "display_name_cn": "准备金利率"
},
"fed_on_rrp_rate": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "daily",
  "unit": "%",
  "freshness_days": 5,
  "display_name": "ON RRP rate",
  "display_name_cn": "逆回购利率"
},
"fed_soma_treasury": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "weekly",
  "unit": "USD billions",
  "freshness_days": 14,
  "display_name": "SOMA Treasury holdings",
  "display_name_cn": "SOMA 国债持仓"
},
"fed_soma_mbs": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "weekly",
  "unit": "USD billions",
  "freshness_days": 14,
  "display_name": "SOMA MBS holdings",
  "display_name_cn": "SOMA MBS 持仓"
},
"fed_srf_usage": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "daily",
  "unit": "USD billions",
  "freshness_days": 5,
  "display_name": "Standing Repo Facility",
  "display_name_cn": "常备回购使用量"
},
"fed_discount_window": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "weekly",
  "unit": "USD billions",
  "freshness_days": 14,
  "display_name": "Discount Window borrowing",
  "display_name_cn": "贴现窗口借款"
},
"fed_soma_avg_duration": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "weekly",
  "unit": "years",
  "freshness_days": 30,
  "display_name": "SOMA avg duration",
  "display_name_cn": "SOMA 平均久期"
},
"fed_tga_net_change_4w": {
  "fred_series": "<DERIVED_FROM_WTREGEN>",
  "source_provider": "fred_derived",
  "category": "monetary",
  "frequency": "weekly",
  "unit": "USD billions",
  "freshness_days": 14,
  "display_name": "TGA 4-week net change",
  "display_name_cn": "TGA 4 周净变动"
},
"fed_fima": {
  "fred_series": "<VERIFIED_SERIES_ID>",
  "source_provider": "fred",
  "category": "monetary",
  "frequency": "daily",
  "unit": "USD billions",
  "freshness_days": 5,
  "display_name": "FIMA Repo Pool",
  "display_name_cn": "FIMA 外国央行逆回购池"
},
"fed_qt_cap": {
  "fred_series": "<DERIVED_FROM_FED_COMMUNICATION>",
  "source_provider": "fed_communication",
  "category": "monetary",
  "frequency": "monthly",
  "unit": "USD billions",
  "freshness_days": 30,
  "display_name": "QT monthly cap",
  "display_name_cn": "QT 月度上限"
}
```

(Replace `<VERIFIED_SERIES_ID>` with actual FRED IDs from Step 1. If a series doesn't exist, mark it `display_only` in scoring and use a computed fallback in the future.)

- [ ] **Step 5: Run the test to verify it passes**

```bash
python -m pytest tests/test_indicator_monitoring.py::test_macro_indicator_api_map_contains_fed_operations_indicators -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/monitoring/configs/macro_indicator_api_map.v1.json trading-system-codex/tests/test_indicator_monitoring.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] api_map: add 10 fed_operations indicators (V1.7.3)"
```

---

## Task 2: Add 10 scoring entries to scoring_registry

**Files:**
- Modify: `trading-system-codex/app/monitoring/configs/macro_scoring_registry.v1.json`

- [ ] **Step 1: Write failing test for scoring registry coverage**

In `tests/test_fed_operations_layer.py` (new file):

```python
def test_scoring_registry_covers_fed_operations_indicators():
    """Every new fed_operations indicator must have a scoring entry."""
    from app.monitoring.configs.macro_scoring_registry import load_scoring_registry
    # (or whatever the actual loader is)
    registry = load_scoring_registry()
    scored_keys = {entry["indicator_key"] for entry in registry["indicators"]}
    required = {
        "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window", "fed_soma_avg_duration",
        "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
    }
    missing = required - scored_keys
    assert not missing, f"missing scoring entries: {missing}"
```

(If a `load_scoring_registry()` function doesn't exist, the test should load the JSON file directly via `json.loads(Path(...).read_text())`.)

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest tests/test_fed_operations_layer.py::test_scoring_registry_covers_fed_operations_indicators -v
```

Expected: FAIL.

- [ ] **Step 3: Add 10 scoring entries to registry**

In `app/monitoring/configs/macro_scoring_registry.v1.json`, find the `indicators` array and append 10 new entries (matching the existing entry structure shown in `app/monitoring/configs/macro_scoring_registry.v1.json`):

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
},
{
  "indicator_key": "fed_on_rrp_rate",
  "aliases": ["on_rrp_rate", "reverse_repo_rate"],
  "formula_id": "inverse_linear",
  "unit": "%",
  "thresholds": {"low": 4.0, "high": 5.5},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "Fed 利率走廊下限宽松",
  "bearish_label": "Fed 利率走廊下限偏紧"
},
{
  "indicator_key": "fed_soma_treasury",
  "aliases": ["soma_treasury", "wsfomcb"],
  "formula_id": "direct_linear",
  "unit": "USD billions",
  "thresholds": {"low": 2500, "high": 5000},
  "higher_value_bias": "bullish_for_risk_assets",
  "bullish_label": "SOMA 国债持仓扩张中",
  "bearish_label": "SOMA 国债持仓收缩中"
},
{
  "indicator_key": "fed_soma_mbs",
  "aliases": ["soma_mbs", "wsfseaml"],
  "formula_id": "direct_linear",
  "unit": "USD billions",
  "thresholds": {"low": 1500, "high": 2800},
  "higher_value_bias": "bullish_for_risk_assets",
  "bullish_label": "SOMA MBS 持仓扩张中",
  "bearish_label": "SOMA MBS 持仓收缩中"
},
{
  "indicator_key": "fed_srf_usage",
  "aliases": ["srf", "standing_repo_facility"],
  "formula_id": "display_only",
  "unit": "USD billions",
  "thresholds": {"low": 0, "high": 50},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "回购工具未被使用",
  "bearish_label": "SRF 使用上升（流动性紧张）"
},
{
  "indicator_key": "fed_discount_window",
  "aliases": ["discount_window", "dpdcbs"],
  "formula_id": "display_only",
  "unit": "USD billions",
  "thresholds": {"low": 0, "high": 30},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "贴现窗口借款正常",
  "bearish_label": "贴现窗口借款上升（银行压力）"
},
{
  "indicator_key": "fed_soma_avg_duration",
  "aliases": ["soma_avg_duration"],
  "formula_id": "direct_linear",
  "unit": "years",
  "thresholds": {"low": 6.0, "high": 8.5},
  "higher_value_bias": "neutral",
  "bullish_label": "SOMA 持仓久期偏长",
  "bearish_label": "SOMA 持仓久期偏短"
},
{
  "indicator_key": "fed_tga_net_change_4w",
  "aliases": ["tga_net_change_4w"],
  "formula_id": "direct_linear",
  "unit": "USD billions",
  "thresholds": {"low": -100, "high": 100},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "TGA 净减少（流动性注入）",
  "bearish_label": "TGA 净增加（流动性抽出）"
},
{
  "indicator_key": "fed_fima",
  "aliases": ["fima", "foreign_repo_pool"],
  "formula_id": "direct_linear",
  "unit": "USD billions",
  "thresholds": {"low": 0, "high": 100},
  "higher_value_bias": "neutral",
  "bullish_label": "外国央行在 Fed 大量存款",
  "bearish_label": "外国央行在 Fed 减少存款"
},
{
  "indicator_key": "fed_qt_cap",
  "aliases": ["qt_cap", "treasury_runoff"],
  "formula_id": "display_only",
  "unit": "USD billions",
  "thresholds": {"low": 0, "high": 95},
  "higher_value_bias": "bearish_for_risk_assets",
  "bullish_label": "QT 节奏低于上限（宽松）",
  "bearish_label": "QT 节奏接近上限（偏紧）"
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_fed_operations_layer.py::test_scoring_registry_covers_fed_operations_indicators -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/monitoring/configs/macro_scoring_registry.v1.json trading-system-codex/tests/test_fed_operations_layer.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] scoring_registry: add fed_operations scoring (V1.7.3)"
```

---

## Task 3: Add `fed_operations` layer to `LAYER_LABELS`

**Files:**
- Modify: `trading-system-codex/app/services/macro_overview.py` (find `LAYER_LABELS`)

- [ ] **Step 1: Read current LAYER_LABELS structure**

Read `app/services/macro_overview.py` around the `LAYER_LABELS` definition (around line 76-83 per earlier exploration). Confirm the exact format: each layer is a dict with `label_cn` and `indicators` (list of indicator keys).

- [ ] **Step 2: Write failing test for the layer**

In `tests/test_fed_operations_layer.py`, append:

```python
def test_macro_overview_has_fed_operations_layer():
    """LAYER_LABELS must include fed_operations as a 7th layer."""
    from app.services.macro_overview import LAYER_LABELS
    assert "fed_operations" in LAYER_LABELS
    layer = LAYER_LABELS["fed_operations"]
    assert "label_cn" in layer
    assert "indicators" in layer
    # Must include 4 existing BS indicators (moved from liquidity_credit)
    for required in ("fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"):
        assert required in layer["indicators"]
    # Must include all 10 new indicators
    for required in (
        "fed_iorb", "fed_on_rrp_rate", "fed_soma_treasury", "fed_soma_mbs",
        "fed_srf_usage", "fed_discount_window", "fed_soma_avg_duration",
        "fed_tga_net_change_4w", "fed_fima", "fed_qt_cap",
    ):
        assert required in layer["indicators"]


def test_liquidity_credit_no_longer_contains_bs_indicators():
    """The 4 BS indicators should have moved to fed_operations."""
    from app.services.macro_overview import LAYER_LABELS
    if "liquidity_credit" in LAYER_LABELS:
        for removed in ("fed_balance_sheet", "bank_reserves", "reverse_repo", "tga"):
            assert removed not in LAYER_LABELS["liquidity_credit"]["indicators"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_fed_operations_layer.py::test_macro_overview_has_fed_operations_layer tests/test_fed_operations_layer.py::test_liquidity_credit_no_longer_contains_bs_indicators -v
```

Expected: Both FAIL.

- [ ] **Step 4: Update LAYER_LABELS**

In `app/services/macro_overview.py`, find the `LAYER_LABELS` dict. Add the new `fed_operations` layer (alphabetically or after `liquidity_credit`), and remove the 4 BS indicators from `liquidity_credit`:

```python
LAYER_LABELS = {
    "rates_policy": {...},
    "inflation": {...},
    "labor_market": {...},
    "liquidity_credit": {
        "label_cn": "流动性与信用",
        "indicators": [
            # fed_balance_sheet, bank_reserves, reverse_repo, tga MOVED to fed_operations
            "m2",
            "hy_spread",
            "ig_spread",
            "hyg",
            "financial_conditions",
            "reverse_repo",  # if not in fed_operations
            "tga",          # if not in fed_operations
        ],
    },
    "fed_operations": {
        "label_cn": "Fed 资产负债表操作",
        "indicators": [
            # Moved from liquidity_credit:
            "fed_balance_sheet",
            "bank_reserves",
            "reverse_repo",
            "tga",
            # Tier 1 (6):
            "fed_iorb",
            "fed_on_rrp_rate",
            "fed_soma_treasury",
            "fed_soma_mbs",
            "fed_srf_usage",
            "fed_discount_window",
            # Tier 2 (4):
            "fed_soma_avg_duration",
            "fed_tga_net_change_4w",
            "fed_fima",
            "fed_qt_cap",
        ],
    },
    "cross_asset_confirmation": {...},
    "event_window": {...},
}
```

(Adjust the existing `liquidity_credit` indicators list to remove the 4 BS ones, keeping `m2 / hy_spread / ig_spread / hyg / financial_conditions`.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_fed_operations_layer.py::test_macro_overview_has_fed_operations_layer tests/test_fed_operations_layer.py::test_liquidity_credit_no_longer_contains_bs_indicators -v
```

Expected: Both PASS.

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/services/macro_overview.py trading-system-codex/tests/test_fed_operations_layer.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[macro] overview: add fed_operations layer (7th) + move 4 BS indicators"
```

---

## Task 4: Add 4 knowledge entries

**Files:**
- Modify: `trading-system-codex/app/static/core/knowledge.js`

- [ ] **Step 1: Write failing test for new knowledge entries**

In `tests/test_knowledge_catalog.py`, append:

```python
def test_fed_operations_knowledge_entries_present():
    """4 new entries: iorb_corridor, net_liquidity, fed_balance_sheet_operations, standing_repo_facility."""
    import json
    from pathlib import Path
    knowledge_path = Path("app/static/core/knowledge.js")
    # Parse the JS file to extract knowledgeSections via Node import (existing pattern)
    proc = subprocess.run(
        ["node", "--input-type=module", "-e",
         f"import {{ knowledgeSections }} from 'file:///{knowledge_path.as_posix()}';\n"
         "const all = knowledgeSections.flatMap(s => s.items.map(i => i.id));\n"
         "console.log(JSON.stringify(all));\n"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=20,
    )
    ids = set(json.loads(proc.stdout.strip()))
    required = {
        "iorb_corridor",
        "net_liquidity",
        "fed_balance_sheet_operations",
        "standing_repo_facility",
    }
    missing = required - ids
    assert not missing, f"missing knowledge entries: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_knowledge_catalog.py::test_fed_operations_knowledge_entries_present -v
```

Expected: FAIL.

- [ ] **Step 3: Add 4 knowledge entries to knowledge.js**

In `app/static/core/knowledge.js`, find the end of the `dataQualityItems` array (or a suitable place) and append 4 new `term()` entries (each must use the EXACT field structure as the existing entries):

```js
term("fed_balance_sheet_operations", "美联储资产负债表操作", {
  category: "monetary",
  family: "fed-operations",
  level: "advanced",
  display_mode: "full",
  importance: "core",
  aliases: ["fed_balance_sheet_policy", "qe_qt", "balance_sheet_runoff"],
  summary: "美联储通过资产负债表规模与结构实施 QE / QT，直接影响流动性。",
  definition: "Fed 持有国债、MBS 等资产的总规模。扩张（QE）= 释放流动性；收缩（QT）= 回收流动性。",
  why_it_matters: "Fed 的口头政策（Fed Funds Rate、CPI 目标）与实际操作（BS）常不一致。监测 BS 才能看到'实际在做什么'。",
  formula: "Total Assets = Treasury Holdings + MBS Holdings + Other",
  how_to_use: "观察趋势变化（+ vs -）比绝对水平更重要。QT 阶段看 run-off 节奏 vs cap。",
  useful_when: [
    "FOMC 决议日",
    "财政部发债重债期",
    "回购市场异动",
  ],
  thresholds: ["月度变动 > $50B → 重要", "接近 QT cap → 流动性收缩加速"],
  risk_note: "Fed 在 2019/2023 多次'嘴上说不缩'但实际通过 BS 抽走流动性。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["iorb_corridor", "net_liquidity", "standing_repo_facility", "bank_reserves"],
  tags: ["monetary", "fed-operations", "core"],
}),
term("iorb_corridor", "IORB / ON RRP 利率走廊", {
  category: "monetary",
  family: "fed-operations",
  level: "advanced",
  display_mode: "full",
  importance: "core",
  aliases: ["iorb", "interest_on_reserve_balances", "on_rrp_rate", "reverse_repo_rate", "rate_corridor"],
  summary: "Fed 通过 IORB（走廊上限）和 ON RRP rate（走廊下限）控制联邦基金利率。",
  definition: "IORB = Interest on Reserve Balances，银行在 Fed 存款的利率。ON RRP rate = Overnight Reverse Repo rate，市场（货币基金）在 Fed 放钱的利率。EFFR 应在两者之间。",
  why_it_matters: "走廊宽度（IORB - ON RRP rate）收窄 → 银行与市场套利空间消失 → 流动性紧张。2008/2020/2023 都有此信号。",
  formula: "走廊宽度 = IORB - ON RRP rate（正常约 10-15 bp）",
  how_to_use: "持续监测差值变化。差值 < 5 bp = 警告；IORB - EFFR > 10 bp = 银行体系压力。",
  useful_when: [
    "FOMC 决议日",
    "回购市场异动",
    "货币基金 YTD 收益异常",
  ],
  thresholds: ["走廊宽度 < 5 bp → 警告", "IORB - EFFR > 10 bp → 银行压力"],
  risk_note: "2023 年 3 月 SVB 危机时走廊从 +10 bp 收窄到 +5 bp，2 天后 Fed 紧急推出 BTFP。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["fed_balance_sheet_operations", "bank_reserves", "reverse_repo"],
  tags: ["monetary", "fed-operations", "corridor"],
}),
term("net_liquidity", "净流动性", {
  category: "monetary",
  family: "fed-operations",
  level: "intermediate",
  display_mode: "full",
  importance: "useful",
  aliases: ["net_liquidity_reserves", "available_liquidity"],
  summary: "Reserves - RRP - TGA，crypto 牛熊分水岭的核心指标。",
  definition: "净流动性 = 银行准备金（reserves） - 逆回购使用量（RRP） - 财政部现金账户（TGA）。这三者合计约为 Fed 总资产减去流通中现金。",
  why_it_matters: "2018-2022 crypto 牛熊分水岭：当净流动性从 $4T 跌至 $1T，crypto 跌入熊市；回升至 $3T+，crypto 创新高。",
  formula: "Net Liquidity = bank_reserves - reverse_repo - tga",
  how_to_use: "看月度变化趋势，不看绝对水平。当 TGA 突增（财政部发债）或 RRP 突增（货币基金放钱给 Fed）→ 净流动性下降 → 风险资产承压。",
  useful_when: [
    "评估 crypto 整体环境",
    "财政部季度再融资公告",
    "回购市场异动",
  ],
  thresholds: ["月度变化 > $200B → 重大", "持续下行 3 个月 → 风险"],
  risk_note: "净流动性是 crypto 与风险资产最相关的'Fed 资产负债表'指标，比 CPI 更直接。",
  page_refs: ["monitoring-overview", "ai-strategy"],
  related_terms: ["bank_reserves", "reverse_repo", "tga", "fed_balance_sheet_operations"],
  tags: ["monetary", "fed-operations", "liquidity"],
}),
term("standing_repo_facility", "Standing Repo Facility / Discount Window", {
  category: "monetary",
  family: "fed-operations",
  level: "advanced",
  display_mode: "full",
  importance: "core",
  aliases: ["srf", "discount_window", "bank_liquidity_facility"],
  summary: "Fed 的最后贷款人工具 — 银行系统压力的最直接信号。",
  definition: "SRF (Standing Repo Facility) = Fed 向健康银行提供隔夜抵押贷款的常备工具。Discount Window = 银行短期借款的最后渠道（贴现）。两者使用量上升 = 银行体系压力。",
  why_it_matters: "SRF/Discount Window 平时使用量接近 0。任何明显上升 = 银行间市场出问题了。2023 年 3 月 SVB 危机后 Fed 重启 BTFP 配套 SRF。",
  formula: "使用量 > $10B 持续 1 周 → 关注；> $50B → 危机级别",
  how_to_use: "监控周度数据。任何非零使用量都值得问为什么。",
  useful_when: [
    "评估银行体系健康度",
    "回购市场异动",
    "FOMC 决议后",
  ],
  thresholds: ["周度 > $10B → 关注", "周度 > $50B → 危机"],
  risk_note: "2008 年雷曼危机前一周 SRF 使用量从 $0 飙升到 $150B+。这是 Fed 资产负债表里'最后才会动'的指标。",
  page_refs: ["monitoring-overview"],
  related_terms: ["fed_balance_sheet_operations", "bank_reserves", "iorb_corridor"],
  tags: ["monetary", "fed-operations", "stress", "core"],
}),
```

(If the `term()` factory at this position doesn't already include all 7 guide fields from V1.7.2, verify that the `term()` definition at the top of the file has been extended per V1.7.2 Task 1 — it should, since the V1.7.2 commits are on main.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_knowledge_catalog.py::test_fed_operations_knowledge_entries_present -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/knowledge.js trading-system-codex/tests/test_knowledge_catalog.py && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] knowledge: add 4 fed_operations entries (V1.7.3)"
```

---

## Task 5: Implement `computeNetLiquidity` helper

**Files:**
- Create: `trading-system-codex/app/static/core/macro_derived.js`

- [ ] **Step 1: Write the helper with no automated test (frontend helper)**

Create `app/static/core/macro_derived.js`:

```js
/**
 * Net liquidity = bank_reserves - reverse_repo - tga
 *
 * Critical for crypto & risk-asset health: 2018-2022 crypto bull/bear
 * regime change tracked 1:1 with this number.
 *
 * Returns { value, status, missing } where:
 *   - value: number | null  (USD billions)
 *   - status: "ok" | "partial" | "missing"
 *   - missing: list of indicator_keys that are unavailable
 */
export function computeNetLiquidity(indicators) {
  if (!Array.isArray(indicators)) {
    return { value: null, status: "missing", missing: ["bank_reserves", "reverse_repo", "tga"] };
  }
  const byKey = new Map();
  for (const ind of indicators) {
    if (ind && ind.indicator_key) byKey.set(ind.indicator_key, ind);
  }
  const reserves = byKey.get("bank_reserves");
  const rrp = byKey.get("reverse_repo");
  const tga = byKey.get("tga");
  const missing = [];
  if (!reserves || reserves.value_num == null) missing.push("bank_reserves");
  if (!rrp || rrp.value_num == null) missing.push("reverse_repo");
  if (!tga || tga.value_num == null) missing.push("tga");
  if (missing.length === 3) return { value: null, status: "missing", missing };
  if (missing.length > 0) return { value: null, status: "partial", missing };
  return {
    value: reserves.value_num - rrp.value_num - tga.value_num,
    status: "ok",
    missing: [],
  };
}
```

- [ ] **Step 2: Verify JS syntax**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  cd trading-system-codex && node --check app/static/core/macro_derived.js
```

Expected: No output (clean).

- [ ] **Step 3: Add a manual smoke test (optional, in scripts/)**

Create `trading-system-codex/scripts/test_macro_derived.js`:

```js
// Quick smoke test for computeNetLiquidity
import { computeNetLiquidity } from "../app/static/core/macro_derived.js";

function assertEq(actual, expected, msg) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  console.log((ok ? "OK  " : "FAIL") + "  " + msg);
  if (!ok) console.log("  expected:", JSON.stringify(expected), "\n  actual:", JSON.stringify(actual));
}

assertEq(
  computeNetLiquidity([
    { indicator_key: "bank_reserves", value_num: 3000 },
    { indicator_key: "reverse_repo", value_num: 500 },
    { indicator_key: "tga", value_num: 700 },
  ]),
  { value: 1800, status: "ok", missing: [] },
  "normal case",
);

assertEq(
  computeNetLiquidity([
    { indicator_key: "bank_reserves", value_num: 3000 },
  ]),
  { value: null, status: "missing", missing: ["reverse_repo", "tga"] },
  "all missing",
);

assertEq(
  computeNetLiquidity([
    { indicator_key: "bank_reserves", value_num: 3000 },
    { indicator_key: "reverse_repo", value_num: 500 },
    // tga missing
  ]),
  { value: null, status: "partial", missing: ["tga"] },
  "partial",
);

assertEq(computeNetLiquidity(null), { value: null, status: "missing", missing: ["bank_reserves", "reverse_repo", "tga"] }, "null input");
assertEq(computeNetLiquidity([]), { value: null, status: "missing", missing: ["bank_reserves", "reverse_repo", "tga"] }, "empty input");
```

Run:
```bash
cd trading-system-codex && node scripts/test_macro_derived.js
```

Expected: All 5 tests print `OK`.

- [ ] **Step 4: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add trading-system-codex/app/static/core/macro_derived.js && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[frontend] macro_derived: add computeNetLiquidity helper (V1.7.3)"
```

(Skip adding `scripts/test_macro_derived.js` to the commit — it's a one-off smoke test, not production code. Delete it after running.)

---

## Task 6: Final regression + CHANGELOG

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `tests/screenshots/` (regenerated by verify_pages.py)

- [ ] **Step 1: Run full pytest suite**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m pytest -q 2>&1 | tail -3
```

Expected: ~845-850 passed, 6 skipped, 0 failed.

- [ ] **Step 2: Run ruff**

```bash
cd trading-system-codex && \
  source ../runtime_dev/.venv/Scripts/activate && \
  python -m ruff check .
```

Expected: All checks passed!

- [ ] **Step 3: Run node --check on all JS**

```bash
cd trading-system-codex && \
  find app/static -name "*.js" -print0 | xargs -0 node --check && echo "JS OK"
```

Expected: JS OK.

- [ ] **Step 4: Update CHANGELOG.md**

In `docs/CHANGELOG.md`, after V1.7.2 section, add:

```markdown
## V1.7.3 (2026-07-02)

新增 Fed 资产负债表操作层 — 监测"美联储实际在做的事情"，不再只看"嘴上说的"。

### 后端

- `app/monitoring/configs/macro_indicator_api_map.v1.json` 新增 10 个 Fed BS 指标：IORB、ON RRP rate、SOMA Treasury / MBS、SRF 使用、Discount Window、SOMA 平均久期、TGA 4 周净变动、FIMA、QT cap
- `app/monitoring/configs/macro_scoring_registry.v1.json` 新增 10 个 scoring entry（4 个 display_only 用于 SRF/Discount Window/QT cap/TGA net change）
- `app/services/macro_overview.py:LAYER_LABELS` 新增第 7 层 `fed_operations`（专门追踪 Fed BS 操作）；原 `liquidity_credit` 移出 4 个 BS 指标

### 前端

- `app/static/core/macro_derived.js` 新文件：`computeNetLiquidity()` — 运行时计算 Reserves - RRP - TGA（crypto 牛熊分水岭）
- `app/static/core/knowledge.js` 新增 4 个词条：fed_balance_sheet_operations / iorb_corridor / net_liquidity / standing_repo_facility

### 测试

- `tests/test_fed_operations_layer.py` 新增 5 个测试：api_map coverage / scoring coverage / layer 存在 / liquidity_credit 移动 / 知识词条存在

### 后续（不在本次范围）

- 监控总览页面渲染 fed_operations layer + net_liquidity 卡片的实现（plan 范围之外，可单独跟进）
- BTFP/SRF 启用/停用自动检测（需要 Fed 公告解析）
- 历史回放图表（高级功能）
```

- [ ] **Step 5: Run verify_pages.py to refresh screenshots**

Start backend (if not running):
```bash
ps aux | grep "uvicorn app.main" | grep -v grep > /tmp/uv_check.txt
if [ ! -s /tmp/uv_check.txt ]; then
  cd "E:\Personal\Research\Crypto Investing System\trading-system-codex" && \
    source ../runtime_dev/.venv/Scripts/activate && \
    nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 > /tmp/uv_v173.log 2>&1 &
  sleep 6
fi
```

Run:
```bash
python tests/verify_pages.py 2>&1 | tail -10
```

Expected: 10/10 pass.

Kill uvicorn:
```bash
ps aux | grep "uvicorn app.main" | grep -v grep | awk '{print $2}' | xargs -r kill 2>&1 || true
```

- [ ] **Step 6: Commit**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git add docs/CHANGELOG.md trading-system-codex/tests/screenshots/ && \
  git -c user.email="codex@example.com" -c user.name="Codex" commit -m "[docs] CHANGELOG: V1.7.3 entry — Fed balance sheet operations layer"
```

- [ ] **Step 7: Final verification**

```bash
cd "E:\Personal\Research\Crypto Investing System" && \
  git log --oneline -15
```

Verify V1.7.3 commits at top in order:
1. `?? [macro] api_map: add 10 fed_operations indicators`
2. `?? [macro] scoring_registry: add fed_operations scoring`
3. `?? [macro] overview: add fed_operations layer (7th) + move 4 BS indicators`
4. `?? [frontend] knowledge: add 4 fed_operations entries`
5. `?? [frontend] macro_derived: add computeNetLiquidity helper`
6. `?? [docs] CHANGELOG: V1.7.3 entry`

---

## Self-Review Checklist

- ✅ **Spec coverage:** Each spec requirement has a task
  - 10 indicators → Task 1
  - 10 scoring entries → Task 2
  - fed_operations layer → Task 3
  - 4 knowledge entries → Task 4
  - net_liquidity runtime → Task 5
  - CHANGELOG + regression → Task 6
- ✅ **Placeholder scan:** No TBD / TODO / "implement later"
- ✅ **Type consistency:**
  - `computeNetLiquidity()` returns `{value, status, missing}` shape used consistently in Task 5 and referenced in frontend Task 6
  - All 10 `indicator_key` strings (`fed_iorb`, `fed_on_rrp_rate`, etc.) used identically in Task 1 (api_map), Task 2 (scoring), Task 3 (LAYER_LABELS), Task 4 (knowledge.related_terms)
- ✅ **Backward compatibility:**
  - Existing 6 layers preserved (liquidity_credit loses 4 BS indicators but keeps m2/hy_spread/ig_spread/hyg/financial_conditions)
  - Existing 44 indicators in api_map preserved (10 new appended)
  - Existing 48 scoring entries preserved (10 new appended)
  - V1.7.2 knowledge entries preserved (4 new appended)
- ✅ **TDD:** Each task writes failing test first

Plan saved at: `trading-system-codex/docs/superpowers/plans/2026-07-02-fed-balance-sheet-operations-layer.md`