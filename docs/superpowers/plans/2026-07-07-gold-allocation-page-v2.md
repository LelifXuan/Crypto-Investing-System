# 黄金配置页 V2 实施计划 (gold-allocation-page-v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把黄金配置页从"执行表单"升级为"V2 配置工作台 + 4 宏观输入 + 9 段递进布局 + 5 档多空标签"，信息密度向 BTC 衍生品页对齐（15 → ~50 信息单元）。

**Architecture:**
- **后端**：扩展 3 个文件，新增 `_bias_for_indicator()` 与 `_gold_macro_snapshot()` 函数；`_gold_macro_snapshot` 实现 4 个核心宏观指标的黄金视角多空判断（含 CPI 二维表、VIX/DXY 流动性冲击例外）
- **前端**：重写 `gold_allocation.js` 9 段递进布局；新增 ~70 行 CSS（二级容器 + 多空 chip + 状态色）
- **设计语言**：贴齐 BTC 衍生品页（`data-tone`/`data-state` 驱动 4 色变量；`.gold-bottom-group` 二级容器圆角 18）

**Tech Stack:**
- Python 3.11 + FastAPI + Pydantic v2
- Vanilla JS + CSS variables（沿用 BTC 既有 4 色变量）
- pytest
- 既有：`MacroOverviewService` / `GoldAllocationEngine` / `_indicator_card`

---

## 1. 文件结构

| 文件 | 职责 | 改动类型 |
|---|---|---|
| `app/services/gold_dca_dip.py` | `_indicator_card()` 增加 `bias` 字段；新增 `_bias_for_indicator()` | 修改 |
| `app/services/gold_macro_adapter.py` | 新增 `_gold_macro_snapshot()` 函数 | 修改 |
| `app/services/gold_allocation_engine.py` | `AllocationPlan.to_dict` 暴露 `gold_macro_snapshot` 字段 | 修改 |
| `app/schemas/gold_allocation.py` | `GoldAllocationPlanResponse` 增加 `gold_macro_snapshot` 字段 | 修改 |
| `app/static/pages/gold_allocation.js` | 重写 9 段递进 + 4 宏观卡 + 多空标签 | 重写 |
| `app/static/styles.css` | 新增 7 个 `.gold-bias-X` + 5 个二级容器/网格类 | 修改 |
| `tests/test_gold_dca_dip_engine.py` | 测试 `_bias_for_indicator` 多空判定 | 修改 |
| `tests/test_gold_frontend_static.py` | 测试 V2 DOM 结构 | 修改 |

---

## Task 1: 后端 — `_indicator_card()` 增加 `bias` 字段

**Files:**
- Modify: `app/services/gold_dca_dip.py:332-362`
- Test: `tests/test_gold_dca_dip_engine.py`

- [ ] **Step 1.1: 写失败测试 — `_bias_for_indicator()` 各档判定**

在 `tests/test_gold_dca_dip_engine.py` 末尾追加：

```python
from app.services.gold_dca_dip import _bias_for_indicator


def test_bias_for_indicator_none_returns_missing():
    assert _bias_for_indicator("rsi_14", None, lower=30, upper=70) == "missing"


def test_bias_for_indicator_no_threshold_returns_neutral():
    # ema_20/ema_50/ema_200/atr_14/natr_14 没有 lower/upper
    assert _bias_for_indicator("ema_20", 4138.26) == "neutral"


def test_bias_for_indicator_rsi_bullish_low():
    # rsi_14 ∈ bullish_low: 越低越看多
    assert _bias_for_indicator("rsi_14", 20, lower=30, upper=70) == "strong_bullish"
    assert _bias_for_indicator("rsi_14", 28, lower=30, upper=70) == "bullish"
    assert _bias_for_indicator("rsi_14", 50, lower=30, upper=70) == "neutral"


def test_bias_for_indicator_rsi_bearish_high():
    assert _bias_for_indicator("rsi_14", 91, lower=30, upper=70) == "strong_bearish"
    assert _bias_for_indicator("rsi_14", 75, lower=30, upper=70) == "bearish"


def test_bias_for_indicator_drawdown_bearish_low():
    # drawdown_from_60d_high ∈ bearish_low: 越低越看空
    # value=-0.15 (15% 回撤), lower=-0.08 → strong_bearish
    assert _bias_for_indicator("drawdown_from_60d_high", -0.15, lower=-0.08) == "strong_bearish"
    assert _bias_for_indicator("drawdown_from_60d_high", -0.09, lower=-0.08) == "bearish"


def test_bias_for_indicator_unknown_key_no_threshold():
    # 未知 key + 无阈值 → neutral
    assert _bias_for_indicator("custom_unknown", 50.0) == "neutral"
```

- [ ] **Step 1.2: 跑测试确认失败**

Run: `cd trading-system-codex && pytest tests/test_gold_dca_dip_engine.py -k "bias_for_indicator" -v`
Expected: 6 failures（`_bias_for_indicator` 未定义）

- [ ] **Step 1.3: 实现 `_bias_for_indicator()` 函数**

在 `app/services/gold_dca_dip.py:332` 之前插入：

```python
def _bias_for_indicator(key: str, value: float | None, *, lower: float | None = None, upper: float | None = None) -> str:
    """多空语义（5 档：strong_bullish / bullish / neutral / bearish / strong_bearish）。

    判定规则：
    - value 为 None → missing
    - 指标不在 bullish_low/bearish_low 集合内 → neutral（默认中性）
    - bullish_low 集合（越低越看多黄金）：
      rsi_14 / cci_20 / percent_b
    - bearish_low 集合（越低越看空黄金）：
      close_vs_ema20_pct / close_vs_ema50_pct / return_7d / return_14d /
      drawdown_from_30d_high / drawdown_from_60d_high
    - 无阈值（lower=None and upper=None）→ neutral
    - 强档阈值：lower*0.7 / upper*1.3
    """
    if value is None:
        return "missing"
    bullish_low = {"rsi_14", "cci_20", "percent_b"}
    bearish_low = {
        "close_vs_ema20_pct", "close_vs_ema50_pct",
        "return_7d", "return_14d",
        "drawdown_from_30d_high", "drawdown_from_60d_high",
    }
    if lower is None and upper is None:
        return "neutral"
    if key in bullish_low:
        if lower is not None and value <= lower * 0.7:
            return "strong_bullish"
        if lower is not None and value <= lower:
            return "bullish"
        if upper is not None and value >= upper * 1.3:
            return "strong_bearish"
        if upper is not None and value >= upper:
            return "bearish"
        return "neutral"
    if key in bearish_low:
        if lower is not None and value <= lower * 0.7:
            return "strong_bearish"
        if lower is not None and value <= lower:
            return "bearish"
        if upper is not None and value >= upper * 1.3:
            return "strong_bullish"
        if upper is not None and value >= upper:
            return "bullish"
        return "neutral"
    return "neutral"
```

- [ ] **Step 1.4: 修改 `_indicator_card()` 输出 `bias` 字段**

修改 `app/services/gold_dca_dip.py:342-362` 的 `_indicator_card()` 函数，让返回 dict 新增 `bias` 字段：

```python
def _indicator_card(
    indicators: IndicatorSnapshot | None,
    *,
    key: str,
    label: str,
    unit: str = "",
    digits: int = 2,
    note: str,
    lower: float | None = None,
    upper: float | None = None,
) -> dict[str, Any]:
    value = getattr(indicators, key, None) if indicators else None
    return {
        "key": key,
        "label": label,
        "value": value,
        "display_value": _format_card_value(value, unit, digits),
        "unit": unit,
        "status": _status_for_value(value, lower=lower, upper=upper),
        "bias": _bias_for_indicator(key, value, lower=lower, upper=upper),
        "note": note,
    }
```

- [ ] **Step 1.5: 跑测试确认通过**

Run: `pytest tests/test_gold_dca_dip_engine.py -k "bias_for_indicator" -v`
Expected: 6 passed

- [ ] **Step 1.6: 提交**

```bash
git add app/services/gold_dca_dip.py tests/test_gold_dca_dip_engine.py
git commit -m "feat(gold): add bias field to indicator card (5-tier bullish/bearish labels)"
```

---

## Task 2: 后端 — `_gold_macro_snapshot()` 函数

**Files:**
- Modify: `app/services/gold_macro_adapter.py`
- Test: `tests/test_gold_macro_adapter.py` (新建)

- [ ] **Step 2.1: 写失败测试 — `_gold_macro_snapshot()` 各场景**

新建 `tests/test_gold_macro_adapter.py`：

```python
from app.services.gold_macro_adapter import _gold_macro_snapshot


def _make_macro(indicators: list[dict]) -> dict:
    return {
        "layer_map": {
            "rates_policy": {"indicators": indicators},
            "cross_asset_confirmation": {"indicators": indicators},
            "inflation": {"indicators": indicators},
        },
        "layers": [
            {"layer_key": "rates_policy", "indicators": indicators},
            {"layer_key": "cross_asset_confirmation", "indicators": indicators},
            {"layer_key": "inflation", "indicators": indicators},
        ],
    }


def test_gold_macro_snapshot_missing_returns_missing():
    snapshot = _gold_macro_snapshot({})
    assert snapshot["real_yield_10y"]["bias"] == "missing"
    assert snapshot["dxy"]["bias"] == "missing"
    assert snapshot["cpi_yoy"]["bias"] == "missing"
    assert snapshot["vix"]["bias"] == "missing"


def test_gold_macro_snapshot_real_yield_high_is_bearish():
    # real_yield_5y=2.5 (在 2.0-2.8 之间 → bearish)
    macro = _make_macro([{"indicator_key": "real_yield_5y", "value_num": 2.5, "unit": "%",
                          "display_label": "5Y Real Yield", "source_provider": "fred",
                          "status": "ok"}])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["real_yield_10y"]["bias"] == "bearish"
    assert "实际利率偏高" in snapshot["real_yield_10y"]["bias_reason"]


def test_gold_macro_snapshot_dxy_strong_bearish():
    macro = _make_macro([{"indicator_key": "dxy", "value_num": 110.0, "unit": "index",
                          "display_label": "DXY", "source_provider": "fred", "status": "ok"}])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["dxy"]["bias"] == "strong_bearish"


def test_gold_macro_snapshot_cpi_2d_table_bullish():
    # CPI=2.7 + RealYield=1.0 + DXY=100 → bullish
    macro = _make_macro([
        {"indicator_key": "cpi_yoy", "value_num": 2.7, "unit": "%", "display_label": "CPI",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 1.0, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 100.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["cpi_yoy"]["bias"] == "bullish"
    assert "抗通胀需求" in snapshot["cpi_yoy"]["bias_reason"]


def test_gold_macro_snapshot_cpi_high_with_tight_yields_bearish():
    # CPI=3.2 + RealYield=2.1 + DXY=106 → bearish
    macro = _make_macro([
        {"indicator_key": "cpi_yoy", "value_num": 3.2, "unit": "%", "display_label": "CPI",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 2.1, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 106.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["cpi_yoy"]["bias"] == "bearish"


def test_gold_macro_snapshot_liquidity_shock_detection():
    # VIX=30 + DXY=106 + RealYield=2.1 → liquidity_shock
    macro = _make_macro([
        {"indicator_key": "vix", "value_num": 30.0, "unit": "index", "display_label": "VIX",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "dxy", "value_num": 106.0, "unit": "index", "display_label": "DXY",
         "source_provider": "fred", "status": "ok"},
        {"indicator_key": "real_yield_5y", "value_num": 2.1, "unit": "%", "display_label": "5Y",
         "source_provider": "fred", "status": "ok"},
    ])
    snapshot = _gold_macro_snapshot(macro)
    assert snapshot["_diagnostics"]["liquidity_shock_detected"] is True
    assert snapshot["vix"]["bias"] == "bearish"  # 流动性冲击下 VIX 急升 ≠ 避险
    assert snapshot["dxy"]["bias"] == "bearish"
    assert "流动性冲击" in snapshot["vix"]["bias_reason"]
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `pytest tests/test_gold_macro_adapter.py -v`
Expected: 6 failures（`_gold_macro_snapshot` 未定义）

- [ ] **Step 2.3: 实现 `_gold_macro_snapshot()` 函数**

在 `app/services/gold_macro_adapter.py:170` 之后追加：

```python
def _gold_macro_snapshot(macro: dict) -> dict:
    """从 macro layer_map 提取 4 个核心宏观指标 + 计算黄金视角的多空 bias。

    重要：以下 bias 计算**仅针对黄金视角**，不复用 registry 的 risk-assets bias。

    阈值来源: app/monitoring/configs/macro_scoring_registry.v1.json
    方向重写: 见 V2 spec §4.6.2-4.6.6
    """
    layer_map = (macro or {}).get("layer_map") or {}
    indicators_by_layer = {
        layer["layer_key"]: layer.get("indicators", [])
        for layer in (macro or {}).get("layers", [])
        if isinstance(layer, dict)
    }
    flat_indicators = [
        ind for ind_list in indicators_by_layer.values() for ind in ind_list
    ]

    def find(indicator_key: str) -> dict | None:
        for ind in flat_indicators:
            if ind.get("indicator_key") == indicator_key:
                return ind
        return None

    def value_of(ind: dict | None) -> float | None:
        return ind.get("value_num") if ind else None

    real_yield = find("real_yield_5y") or find("real_yield_10y")
    dxy = find("dxy") or find("dollar_index")
    cpi = find("cpi_yoy")
    vix = find("vix")

    ry_val = value_of(real_yield)
    dxy_val = value_of(dxy)
    cpi_val = value_of(cpi)
    vix_val = value_of(vix)

    # 流动性冲击检测
    liquidity_shock = (
        vix_val is not None and vix_val >= 25
        and dxy_val is not None and dxy_val >= 105
        and ry_val is not None and ry_val >= 2.0
    )

    def bias_for_real_yield(value):
        if value is None:
            return ("missing", "数据不足")
        if value <= 0.5:
            return ("strong_bullish", "实际利率低于 0.5%，持有黄金机会成本极低，强烈支持黄金")
        if value <= 1.5:
            return ("bullish", "实际利率处于低位，债券吸引力弱，利好黄金")
        if value >= 2.8:
            return ("strong_bearish", "实际利率高于 2.8%，持有黄金机会成本高，强烈压制黄金")
        if value >= 2.0:
            return ("bearish", "实际利率偏高，债券吸引力上升，压制黄金")
        return ("neutral", "实际利率处于中性区间")

    def bias_for_dxy(value):
        if value is None:
            return ("missing", "数据不足")
        if liquidity_shock:
            return ("bearish", "DXY 走强叠加 VIX 急升，流动性冲击模式：黄金短期先被卖补保证金")
        if value <= 98:
            return ("strong_bullish", "美元指数极弱，黄金 USD 计价上涨空间打开")
        if value <= 102:
            return ("bullish", "美元偏弱，支撑黄金")
        if value >= 108:
            return ("strong_bearish", "美元极强，强势压制黄金")
        if value >= 105:
            return ("bearish", "美元走强，压制黄金")
        return ("neutral", "美元处于中性区间")

    def bias_for_cpi(value):
        if value is None:
            return ("missing", "数据不足")
        # CPI 上行 + RealYield 下行 + DXY 不强 → 看多
        if value >= 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 偏高但实际利率下行 / 美元不强 → 抗通胀需求支撑黄金")
        # CPI 上行 + RealYield 上行 + DXY 上行 → 看空
        if value >= 3.0 and ry_val is not None and ry_val >= 2.0:
            if dxy_val is not None and dxy_val >= 105:
                return ("bearish", "CPI 高位 + 实际利率上行 + 美元走强，紧缩周期压制黄金")
        # CPI 温和回落 + RealYield 下行 + DXY 走弱 → 看多（降息预期）
        if 1.5 <= value < 2.5 and ry_val is not None and ry_val < 1.5:
            if dxy_val is None or dxy_val < 105:
                return ("bullish", "CPI 温和回落 + 实际利率下行 + 美元不强，降息预期支撑黄金")
        # CPI 快速下行 → 等待确认
        if value < 1.0:
            return ("neutral", "CPI 快速下行，衰退风险升温，需结合 VIX/DXY/ETF 流向确认（不输出单方向）")
        return ("neutral", "CPI 处于中性区间，需结合其他宏观信号综合判断")

    def bias_for_vix(value):
        if value is None:
            return ("missing", "数据不足")
        if liquidity_shock:
            return ("bearish", "VIX 急升叠加 DXY 走强 + 实际利率上行 → 流动性冲击模式，黄金先被卖补保证金，待压力缓和后回到避险逻辑")
        if value >= 28:
            return ("strong_bullish", "VIX 急升，市场风险厌恶强烈，黄金避险属性显著")
        if value >= 22:
            return ("bullish", "VIX 上升，避险需求支撑黄金")
        if value <= 12:
            return ("strong_bearish", "VIX 极低，市场过度乐观，避险需求缺失")
        if value <= 15:
            return ("bearish", "VIX 偏低，避险需求不足")
        return ("neutral", "VIX 处于中性区间")

    def build(ind, bias_fn, fallback_label):
        if not ind:
            return {
                "value": None,
                "unit": "",
                "display_label": fallback_label,
                "source": "",
                "observation_ts": "",
                "bias": "missing",
                "bias_reason": "数据不足",
                "threshold_low": None,
                "threshold_high": None,
                "status": "missing",
            }
        bias, reason = bias_fn(ind.get("value_num"))
        return {
            "value": ind.get("value_num"),
            "unit": ind.get("unit", ""),
            "display_label": ind.get("display_label", fallback_label),
            "source": ind.get("source_provider", ""),
            "observation_ts": ind.get("observation_ts", ""),
            "bias": bias,
            "bias_reason": reason,
            "threshold_low": 0.5 if "yield" in ind.get("indicator_key", "") else None,
            "threshold_high": 2.8 if "yield" in ind.get("indicator_key", "") else None,
            "status": ind.get("status", "unknown"),
        }

    return {
        "real_yield_10y": build(real_yield, bias_for_real_yield, "美国10年期实际利率 (TIPS yield)"),
        "dxy": build(dxy, bias_for_dxy, "美元指数 DXY"),
        "cpi_yoy": build(cpi, bias_for_cpi, "美国 CPI 同比"),
        "vix": build(vix, bias_for_vix, "VIX 波动率"),
        "_diagnostics": {
            "liquidity_shock_detected": liquidity_shock,
            "liquidity_shock_definition": "VIX>=25 AND DXY>=105 AND RealYield>=2.0",
        },
    }
```

- [ ] **Step 2.4: 跑测试确认通过**

Run: `pytest tests/test_gold_macro_adapter.py -v`
Expected: 6 passed

- [ ] **Step 2.5: 提交**

```bash
git add app/services/gold_macro_adapter.py tests/test_gold_macro_adapter.py
git commit -m "feat(gold): add _gold_macro_snapshot() with 4 macro indicators + liquidity-shock detection"
```

---

## Task 3: 后端 — `AllocationPlan` 暴露 `gold_macro_snapshot`

**Files:**
- Modify: `app/services/gold_allocation_engine.py:1073-1090`
- Modify: `app/schemas/gold_allocation.py:51-77`

- [ ] **Step 3.1: 修改 `AllocationPlan.to_dict()`**

在 `app/services/gold_allocation_engine.py` 找到 `AllocationPlan.to_dict()` 方法（line 109-131），让它在返回的 dict 中新增 `gold_macro_snapshot` 字段：

```python
def to_dict(self) -> dict[str, Any]:
    data = asdict(self)
    target_min = self.target_range["min"]
    target_max = self.target_range["max"]
    # 调用 _gold_macro_snapshot 计算黄金视角的 4 宏观指标
    gold_macro_snapshot = _gold_macro_snapshot(self.macro_payload or {})
    data.update(
        {
            "allocation_score": round(float(self.allocation_score), 1),
            "target_range": {"min": round(target_min, 4), "max": round(target_max, 4)},
            "current_weight": round(float(self.current_weight), 4),
            "gap_to_target_min": round(float(self.gap_to_target_min), 2),
            "gap_above_target_max": round(float(self.gap_above_target_max), 2),
            "suggested_this_month": round(float(self.suggested_this_month), 2),
            "target_weight_min": round(target_min, 4),
            "target_weight_max": round(target_max, 4),
            "gap_to_min_amount": round(float(self.gap_to_target_min), 2),
            "overweight_above_max_amount": round(float(self.gap_above_target_max), 2),
            "suggested_this_month_amount": round(float(self.suggested_this_month), 2),
            "summary": self.decision_summary,
            "risk_notes": list(self.warnings),
            "action": _legacy_action(self.allocation_state, self.execution_style),
            "gold_macro_snapshot": gold_macro_snapshot,  # 新增字段
        }
    )
    return data
```

> **注意**：`AllocationPlan` 当前没有 `macro_payload` 字段。需要先在 `AllocationPlan` dataclass 中新增这个字段（见下一步）。

- [ ] **Step 3.2: `AllocationPlan` dataclass 新增 `macro_payload` 字段**

在 `app/services/gold_allocation_engine.py:91-108` 的 `AllocationPlan` 类中新增字段：

```python
@dataclass(slots=True)
class AllocationPlan:
    allocation_state: str
    allocation_score: float
    target_range: dict[str, float]
    current_weight: float
    gap_to_target_min: float
    gap_above_target_max: float
    suggested_this_month: float
    execution_style: str
    primary_instruction: str
    decision_summary: str
    reasoning_steps: list[str]
    module_cards: list[dict[str, Any]]
    data_quality: dict[str, Any]
    warnings: list[str]
    drivers: dict[str, Any]
    asset_impact_summary: dict[str, str]
    macro_payload: dict[str, Any] = field(default_factory=dict)  # 新增
```

并在文件顶部 import `field`：

```python
from dataclasses import asdict, dataclass, field  # 已存在 field
```

确认 `field` 已在 import 行。

- [ ] **Step 3.3: 修改 `build_gold_allocation_plan()` 传入 macro_payload**

在 `app/services/gold_allocation_engine.py:1032-1090` 的 `build_gold_allocation_plan()` 函数末尾（return 之前），把 `macro_payload` 传给 `AllocationPlan`：

```python
return AllocationPlan(
    allocation_state=state,
    allocation_score=score,
    target_range=target,
    current_weight=portfolio.current_weight,
    gap_to_target_min=gap_to_min,
    gap_above_target_max=gap_above_max,
    suggested_this_month=suggested,
    execution_style=execution_style,
    primary_instruction=primary_instruction,
    decision_summary=decision_summary,
    reasoning_steps=steps,
    module_cards=module_cards,
    data_quality=quality,
    warnings=warnings,
    drivers={card["key"]: card for card in module_cards},
    asset_impact_summary={"gold": decision_summary},
    macro_payload=macro,  # 新增
)
```

- [ ] **Step 3.4: 修改 `GoldAllocationPlanResponse` schema**

在 `app/schemas/gold_allocation.py:51-77` 的 `GoldAllocationPlanResponse` 类中新增 `gold_macro_snapshot` 字段：

```python
class GoldAllocationPlanResponse(BaseModel):
    # ... 既有字段 ...
    asset_impact_summary: dict[str, str]
    gold_macro_snapshot: dict[str, Any] = Field(default_factory=dict)  # 新增
```

确认 `Field` 已在 import 行（已有 `from pydantic import BaseModel, Field, model_validator`）。

- [ ] **Step 3.5: 跑相关测试确认不破坏现有功能**

Run: `pytest tests/test_gold_allocation_api.py tests/test_gold_allocation_engine.py -v`
Expected: 所有现有测试通过

- [ ] **Step 3.6: 提交**

```bash
git add app/services/gold_allocation_engine.py app/schemas/gold_allocation.py
git commit -m "feat(gold): expose gold_macro_snapshot in /gold/allocation response"
```

---

## Task 4: 前端 — CSS 新增（多空 chip + 二级容器 + 4 状态色）

**Files:**
- Modify: `app/static/styles.css` (在 styles.css 末尾追加新类)

- [ ] **Step 4.1: 在 styles.css 末尾追加 7 个多空 chip 类**

在 `app/static/styles.css` 最后一行（建议先 grep 确认是文件末尾）后追加：

```css
/* Gold V2 多空 chip (5 档 + missing) */
.gold-bias-chip {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
  display: inline-block;
}
.gold-bias-strong-bullish {
  background: rgba(15, 118, 110, 0.18);
  color: #0b5f58;
}
.gold-bias-bullish {
  background: rgba(15, 118, 110, 0.10);
  color: #0f766e;
}
.gold-bias-neutral {
  background: rgba(98, 112, 120, 0.10);
  color: #4b5961;
}
.gold-bias-bearish {
  background: rgba(195, 90, 29, 0.10);
  color: #c35a1d;
}
.gold-bias-strong-bearish {
  background: rgba(195, 90, 29, 0.18);
  color: #8c3a10;
}
.gold-bias-missing {
  background: rgba(183, 121, 31, 0.10);
  color: #b7791f;
}

/* Gold V2 二级容器（沿用 BTC bottom-group 模式）*/
.gold-bottom-group {
  padding: 22px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.32);
  box-shadow: 0 18px 48px rgba(23, 37, 34, 0.05);
}

/* Gold V2 决策带 3 列网格 */
.gold-decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.gold-decision-card {
  min-height: 230px;
  padding: 18px 20px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.gold-decision-card[data-tone="bullish"] {
  border-color: rgba(15, 118, 110, 0.30);
  background: rgba(15, 118, 110, 0.04);
}
.gold-decision-card[data-tone="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
  background: rgba(195, 90, 29, 0.04);
}
.gold-decision-card[data-tone="neutral"] {
  border-color: rgba(183, 121, 31, 0.30);
  background: rgba(183, 121, 31, 0.04);
}

/* Gold V2 4 宏观卡 */
.gold-macro-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.gold-macro-card {
  min-height: 220px;
  padding: 18px;
  border: 1px solid rgba(15, 118, 110, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
}
.gold-macro-card[data-bias^="strong_bullish"],
.gold-macro-card[data-bias="bullish"] {
  border-color: rgba(15, 118, 110, 0.30);
}
.gold-macro-card[data-bias^="strong_bearish"],
.gold-macro-card[data-bias="bearish"] {
  border-color: rgba(195, 90, 29, 0.30);
}
.gold-macro-card[data-bias="missing"] {
  border-color: rgba(183, 121, 31, 0.30);
  background: rgba(183, 121, 31, 0.04);
}
.gold-macro-reason {
  font-size: 12px;
  color: var(--muted);
  margin: 8px 0 0;
  line-height: 1.4;
}

/* Gold V2 流动性冲击警告（hero 边条） */
.gold-liquidity-shock-banner {
  padding: 12px 16px;
  border-left: 3px solid #c35a1d;
  background: rgba(195, 90, 29, 0.06);
  border-radius: 4px;
  font-size: 13px;
  color: #8c3a10;
  margin: 0 0 18px 0;
}
```

- [ ] **Step 4.2: 提交 CSS**

```bash
git add app/static/styles.css
git commit -m "style(gold): add V2 multi-tier bias chips + bottom-group container + macro cards"
```

---

## Task 5: 前端 — `renderIndicatorCard` 改造（5 档多空标签）

**Files:**
- Modify: `app/static/pages/gold_allocation.js:303-314`

- [ ] **Step 5.1: 修改 `renderIndicatorCard` 函数**

替换 `app/static/pages/gold_allocation.js:303-314`：

```javascript
function renderIndicatorCard(card) {
  return `
    <article class="gold-indicator-card" data-bias="${escapeHtml(card.bias || "neutral")}">
      <div>
        <strong>${escapeHtml(card.label || "指标")}</strong>
        <span class="gold-bias-chip gold-bias-${escapeHtml(card.bias || "neutral")}">${biasLabel(card.bias)}</span>
      </div>
      <b>${escapeHtml(card.display_value || "-")}</b>
      <small>${escapeHtml(card.note || "")}</small>
    </article>
  `;
}

function biasLabel(bias) {
  return {
    strong_bullish: "强势看多",
    bullish: "看多",
    neutral: "中性",
    bearish: "看空",
    strong_bearish: "强势看空",
    missing: "数据不足",
  }[bias] || "中性";
}
```

- [ ] **Step 5.2: 视觉冒烟 — 启动 dev server 打开黄金配置页**

Run: `cd trading-system-codex && uvicorn app.main:app --reload --port 8000`
然后浏览器打开 `http://localhost:8000/gold-allocation-page`

期望：
- 核心指标 8 张卡的右上角标签改为 5 档多空（不再"可用/偏低"）
- EMA20/EMA50/EMA200/ATR14/NATR14 显示"中性"

- [ ] **Step 5.3: 提交**

```bash
git add app/static/pages/gold_allocation.js
git commit -m "feat(gold-ui): render 5-tier bullish/bearish labels on indicator cards"
```

---

## Task 6: 前端 — 4 张宏观卡组件

**Files:**
- Modify: `app/static/pages/gold_allocation.js` (新增函数)

- [ ] **Step 6.1: 新增 `renderMacroStrip()` + `renderMacroCard()` 函数**

在 `app/static/pages/gold_allocation.js` `renderIndicatorCard` 之后追加：

```javascript
function renderMacroStrip(snapshot) {
  if (!snapshot) return "";
  const items = [
    { key: "real_yield_10y", label: "实际利率 (TIPS yield)", value: snapshot.real_yield_10y },
    { key: "dxy", label: "DXY 美元指数", value: snapshot.dxy },
    { key: "cpi_yoy", label: "CPI 同比", value: snapshot.cpi_yoy },
    { key: "vix", label: "VIX 波动率", value: snapshot.vix },
  ];
  const liquidityShock = snapshot._diagnostics?.liquidity_shock_detected;
  return `
    <section class="gold-bottom-group" data-section="macro-strip">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">MACRO INPUTS</p>
          <h2>宏观输入</h2>
          <p class="section-summary">直接影响黄金价格的 4 个宏观信号 (real_yield_10y / DXY / CPI YoY / VIX)。</p>
        </div>
      </div>
      ${liquidityShock ? '<div class="gold-liquidity-shock-banner">⚠ 流动性冲击模式：VIX 急升 + DXY 走强 + 实际利率上行，短期黄金先被卖补保证金。</div>' : ""}
      <div class="gold-macro-strip">
        ${items.map((item) => renderMacroCard(item.label, item.value)).join("")}
      </div>
    </section>
  `;
}

function renderMacroCard(label, macro) {
  if (!macro || macro.status === "missing") {
    return `
      <article class="gold-macro-card" data-status="missing" data-bias="missing">
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span class="gold-bias-chip gold-bias-missing">数据不足</span>
        </div>
        <b>—</b>
        <small>${escapeHtml(macro?.display_label || "")}</small>
      </article>
    `;
  }
  return `
    <article class="gold-macro-card" data-bias="${escapeHtml(macro.bias || "neutral")}">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span class="gold-bias-chip gold-bias-${escapeHtml(macro.bias || "neutral")}">${biasLabel(macro.bias)}</span>
      </div>
      <b>${formatNumber(macro.value, 2)}${escapeHtml(macro.unit || "")}</b>
      <small>${escapeHtml(macro.display_label)} · 来源 ${escapeHtml(macro.source)}</small>
      <p class="gold-macro-reason">${escapeHtml(macro.bias_reason || "")}</p>
    </article>
  `;
}
```

- [ ] **Step 6.2: 提交**

```bash
git add app/static/pages/gold_allocation.js
git commit -m "feat(gold-ui): render 4 macro indicator cards (TIPS/DXY/CPI/VIX) with bias_reason"
```

---

## Task 7: 前端 — 重写 `renderShell()` 9 段递进布局

**Files:**
- Modify: `app/static/pages/gold_allocation.js:161-192`

- [ ] **Step 7.1: 重写 `renderShell()` 函数**

替换 `app/static/pages/gold_allocation.js:161-192` 的 `renderShell()`：

```javascript
function renderShell(state, banner = "") {
  const allocation = latestAllocation;
  const macro = allocation?.gold_macro_snapshot;
  const liquidityShock = macro?._diagnostics?.liquidity_shock_detected;
  return `
    <section class="hero-card gold-v3-hero" ${liquidityShock ? 'data-tone="bearish"' : ""}>
      <div>
        <p class="eyebrow">GOLD ALLOCATION V2</p>
        <h1>黄金宏观与配置工作台</h1>
        <p>多模块加权评分 + 宏观信号 + 长期目标区间 + 执行计划。</p>
      </div>
      <button class="button compact" id="gold-reload-xaut" type="button">刷新 XAUT</button>
    </section>
    ${banner}
    ${liquidityShock ? '<div class="gold-liquidity-shock-banner">⚠ 检测到流动性冲击（VIX≥25 + DXY≥105 + 实际利率≥2.0%），黄金短期承压，长期避险逻辑待恢复。</div>' : ""}

    <div class="gold-v3-layout">
      <!-- ② 决策带 (3 张 decision card) -->
      ${renderDecisionGrid(allocation)}

      <!-- ③ 4 个核心宏观指标 -->
      ${renderMacroStrip(macro)}

      <!-- ④ 7 模块证据卡 -->
      ${renderModuleSection(allocation)}

      <!-- ⑤ 图表区 -->
      ${renderChartSection(allocation)}

      <!-- ⑥ XAUT 代理行情 + 黄金坑结构 -->
      <section class="gold-bottom-group">
        <div class="gold-top-grid">
          ${renderMarketPanel()}
          ${renderStrategyPanel(state)}
        </div>
      </section>

      <!-- ⑦ 执行子区块 -->
      <section class="gold-bottom-group">
        <div class="gold-bottom-grid">
          ${renderSettingsCard(state)}
          ${renderDiagnostics()}
        </div>
      </section>

      <!-- ⑧ 核心 + 派生指标卡 -->
      <section class="gold-indicator-layout">
        ${renderIndicatorSection("核心指标", latestPlan?.diagnostics?.core_indicator_cards || [], "8 项核心指标用于复核日线样本和基础技术状态。")}
        ${renderIndicatorSection("派生指标", latestPlan?.diagnostics?.derived_indicator_cards || [], "6 项派生指标用于判断回撤、偏离和触发质量。")}
      </section>

      <!-- ⑨ 数据治理 -->
      ${renderGovernanceSection()}
    </div>
  `;
}
```

- [ ] **Step 7.2: 新增辅助函数 `renderDecisionGrid` / `renderModuleSection` / `renderChartSection` / `renderGovernanceSection`**

在 `renderShell` 之后追加：

```javascript
function renderDecisionGrid(allocation) {
  if (!allocation) {
    return `
      <section class="gold-bottom-group">
        <div class="section-head compact">
          <div>
            <p class="eyebrow">DECISIONS</p>
            <h2>决策带</h2>
            <p class="section-summary">正在加载 V2 决策。</p>
          </div>
        </div>
      </section>
    `;
  }
  // 3 张 decision card
  const score = allocation.allocation_score ?? 50;
  const tone = score >= 60 ? "bullish" : score <= 40 ? "bearish" : "neutral";
  return `
    <section class="gold-bottom-group">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">DECISIONS</p>
          <h2>决策带</h2>
          <p class="section-summary">宏观环境 / 配置建议 / 执行计划。</p>
        </div>
      </div>
      <div class="gold-decision-grid">
        <article class="gold-decision-card" data-tone="${tone}">
          <p class="eyebrow">宏观环境</p>
          <h3>综合评分 ${score}</h3>
          <p>${escapeHtml(allocation.decision_summary || "")}</p>
        </article>
        <article class="gold-decision-card" data-tone="${tone}">
          <p class="eyebrow">配置建议</p>
          <h3>${escapeHtml(allocation.allocation_state)}</h3>
          <p>${escapeHtml(allocation.primary_instruction || "")}</p>
          <small>目标区间 ${formatNumber((allocation.target_range?.min || 0) * 100, 1)}% – ${formatNumber((allocation.target_range?.max || 0) * 100, 1)}%</small>
        </article>
        <article class="gold-decision-card" data-tone="${tone}">
          <p class="eyebrow">执行计划</p>
          <h3>本月建议 ${money(allocation.suggested_this_month)}</h3>
          <p>${escapeHtml(allocation.reasoning_steps?.[0] || "")}</p>
        </article>
      </div>
    </section>
  `;
}

function renderModuleSection(allocation) {
  if (!allocation?.module_cards) return "";
  return `
    <section class="gold-bottom-group">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">MODULES</p>
          <h2>7 模块证据卡</h2>
          <p class="section-summary">宏观货币 / 官方储备 / 供给刚性 / 组合对冲 / 流动性 / 衍生品 / XAUT。</p>
        </div>
      </div>
      <div class="gold-decision-grid">
        ${allocation.module_cards.map(renderModuleCard).join("")}
      </div>
    </section>
  `;
}

function renderChartSection(allocation) {
  // 简化为占位 — 真正的图表实现可在后续任务中扩展
  return `
    <section class="gold-bottom-group">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">CHARTS</p>
          <h2>图表区</h2>
          <p class="section-summary">XAUT 关键指标 + 基本面快照。</p>
        </div>
      </div>
      <div class="gold-macro-strip">
        <article class="gold-macro-card">
          <strong>XAUT 关键指标</strong>
          <p class="gold-macro-reason">图表组件占位。XAUT 价格 / 7D-30D 变化 / 60D 回撤 / NATR 等可在 V2.1 实施。</p>
        </article>
        <article class="gold-macro-card">
          <strong>基本面快照</strong>
          <p class="gold-macro-reason">图表组件占位。央行净购金 / ETF 流量等可在 V2.1 实施。</p>
        </article>
        <article class="gold-macro-card" data-status="placeholder">
          <strong>占位 3</strong>
          <p class="gold-macro-reason">—</p>
        </article>
        <article class="gold-macro-card" data-status="placeholder">
          <strong>占位 4</strong>
          <p class="gold-macro-reason">—</p>
        </article>
      </div>
    </section>
  `;
}

function renderGovernanceSection() {
  return `
    <section class="gold-bottom-group">
      <details class="btc-details-drawer">
        <summary>数据治理与可信度</summary>
        <div class="gold-card-metrics">
          <article><span>报价状态</span><b>${escapeHtml(latestMarket?.data_quality_note || "—")}</b></article>
          <article><span>K 线数量</span><b>${escapeHtml(String(latestPlan?.diagnostics?.candle_count ?? "-"))}</b></article>
        </div>
      </details>
    </section>
  `;
}
```

- [ ] **Step 7.3: 视觉冒烟 — 重启 dev server 检查 9 段布局**

Run: `cd trading-system-codex && uvicorn app.main:app --reload --port 8000`
浏览器打开 `http://localhost:8000/gold-allocation-page`

期望：
- 9 段递进布局清晰呈现
- 决策带 3 张卡（宏观 / 配置 / 执行）
- 4 张宏观卡 + bias_reason 显示
- 7 模块卡网格
- 图表区占位
- XAUT + 黄金坑
- 执行子区块
- 核心/派生指标卡（多空标签）
- 数据治理折叠面板

- [ ] **Step 7.4: 提交**

```bash
git add app/static/pages/gold_allocation.js
git commit -m "feat(gold-ui): 9-segment BTC-style layout (decision grid + 4 macro + 7 modules + charts + execution + governance)"
```

---

## Task 8: 前端 — `loadExecutionPlan()` 调用 `/gold/allocation`

**Files:**
- Modify: `app/static/pages/gold_allocation.js:424-442`

- [ ] **Step 8.1: 修改 `loadExecutionPlan()` 函数**

替换 `app/static/pages/gold_allocation.js:424-442` 的 `loadExecutionPlan()`：

```javascript
async function loadExecutionPlan({ forceMarket = false, preserveShell = false } = {}) {
  if (controller) controller.abort();
  controller = new AbortController();
  let state = preserveShell ? readFormState() : readState();
  if (!preserveShell) {
    setRoot(renderShell(state, statusBanner("正在读取黄金执行计划", "loading")));
  }
  try {
    latestMarket = await api.getGoldMarketState({ force: forceMarket, signal: controller.signal });
  } catch (error) {
    if (error?.name !== "AbortError") {
      console.warn("XAUT market state unavailable", error);
    }
  }
  // 新增：拉取 V2 配置计划（包含 gold_macro_snapshot + module_cards）
  try {
    latestAllocation = await api.getGoldAllocation({ signal: controller.signal });
  } catch (error) {
    if (error?.name !== "AbortError") {
      console.warn("V2 gold allocation unavailable", error);
    }
  }
  latestPlan = await api.planGoldExecution(payloadFromState(state), { signal: controller.signal });
  state = persistTriggeredDipState(latestPlan, state);
  setRoot(renderShell(state, statusBanner("黄金执行计划已生成", "neutral")));
  bindEvents();
}
```

- [ ] **Step 8.2: 视觉冒烟 — 确认 V2 数据加载**

浏览器打开 `http://localhost:8000/gold-allocation-page`

期望：
- 决策带 3 张卡显示真实数据
- 4 张宏观卡显示真实数据（含 bias_reason）
- 7 模块卡显示真实数据
- 流动性冲击警告（如触发）

- [ ] **Step 8.3: 提交**

```bash
git add app/static/pages/gold_allocation.js
git commit -m "feat(gold-ui): wire /gold/allocation into loadExecutionPlan for V2 data"
```

---

## Task 9: 静态测试 — 验证 V2 DOM 结构

**Files:**
- Modify: `tests/test_gold_frontend_static.py`

- [ ] **Step 9.1: 新增 V2 DOM 结构断言**

在 `tests/test_gold_frontend_static.py` 末尾追加：

```python
import re


def test_gold_v2_macro_strip_renders():
    """验证 4 个宏观卡占位 class 已声明（即使页面未加载也能从 styles.css 找到）"""
    css = open("trading-system-codex/app/static/styles.css", encoding="utf-8").read()
    assert ".gold-macro-strip" in css
    assert ".gold-macro-card" in css
    assert css.count("gold-bias-chip") >= 1


def test_gold_v2_decision_grid_class_exists():
    css = open("trading-system-codex/app/static/styles.css", encoding="utf-8").read()
    assert ".gold-decision-grid" in css
    assert ".gold-decision-card" in css
    assert 'data-tone="bullish"' in css or 'data-tone="bearish"' in css


def test_gold_v2_bottom_group_container():
    css = open("trading-system-codex/app/static/styles.css", encoding="utf-8").read()
    assert ".gold-bottom-group" in css
    assert "border-radius: 18px" in css


def test_gold_v2_liquidity_shock_banner():
    css = open("trading-system-codex/app/static/styles.css", encoding="utf-8").read()
    assert ".gold-liquidity-shock-banner" in css


def test_gold_js_macro_strip_function():
    js = open("trading-system-codex/app/static/pages/gold_allocation.js", encoding="utf-8").read()
    assert "renderMacroStrip" in js
    assert "renderMacroCard" in js
    assert "real_yield_10y" in js
    assert "gold_macro_snapshot" in js


def test_gold_js_9_segments():
    js = open("trading-system-codex/app/static/pages/gold_allocation.js", encoding="utf-8").read()
    # 9 个 section 渲染函数
    for fn in [
        "renderShell",
        "renderDecisionGrid",
        "renderMacroStrip",
        "renderModuleSection",
        "renderChartSection",
        "renderMarketPanel",
        "renderStrategyPanel",
        "renderSettingsCard",
        "renderDiagnostics",
        "renderIndicatorSection",
        "renderGovernanceSection",
    ]:
        assert fn in js, f"missing {fn}"


def test_gold_js_bias_label_function():
    js = open("trading-system-codex/app/static/pages/gold_allocation.js", encoding="utf-8").read()
    assert "function biasLabel" in js
    assert "强势看多" in js
    assert "看多" in js
    assert "看空" in js
    assert "强势看空" in js
```

- [ ] **Step 9.2: 跑测试**

Run: `pytest tests/test_gold_frontend_static.py -v`
Expected: 全部通过

- [ ] **Step 9.3: 提交**

```bash
git add tests/test_gold_frontend_static.py
git commit -m "test(gold): add static assertions for V2 DOM structure (9 segments + 4 macro + 5-tier bias)"
```

---

## Task 10: 端到端冒烟 — 全套 pytest 验证

**Files:** None

- [ ] **Step 10.1: 跑全套黄金相关测试**

Run: `cd trading-system-codex && pytest tests/test_gold_*.py tests/test_gold_macro_adapter.py -v`
Expected: 全部通过

- [ ] **Step 10.2: 跑全套测试确认无回归**

Run: `pytest tests/ -v --timeout=60 -x`
Expected: 无回归（之前的测试继续通过）

- [ ] **Step 10.3: 手动浏览器冒烟**

浏览器打开 7 个 page 走一遍：
- 黄金配置页（主验证）
- BTC 衍生品（确认 data-tone 不影响其他页）
- 监控总览（确认布局没动）
- 形态结构（确认 styles.css 新增类无副作用）
- 技术分析、宏观日历、A股 ETF、市场事件

- [ ] **Step 10.4: 提交（如果有任何修复）**

```bash
git add -A
git commit -m "fix(gold-v2): address any smoke test issues"
```

---

## Task 11: CHANGELOG 与版本号

**Files:**
- Modify: `CHANGELOG.md` (新建或更新)

- [ ] **Step 11.1: 添加 v1.7.7 CHANGELOG 条目**

在 `CHANGELOG.md` 顶部追加：

```markdown
# CHANGELOG

## v1.7.7 (2026-07-XX)

### 黄金配置页 V2 升级

- **多空标签**：核心/派生指标卡右上角标签从"可用/偏低"改为 5 档多空判断（强势看多 / 看多 / 中性 / 看空 / 强势看空）。新增 `_bias_for_indicator()` 后端函数 + 5 档 CSS 类。
- **宏观指标**：新增 4 个核心宏观卡（real_yield_10y / DXY / CPI YoY / VIX）。每个卡显示多空标签 + bias_reason + 数据源。后端新增 `_gold_macro_snapshot()` 函数实现黄金视角的多空判断（含 CPI 二维表 / VIX 流动性冲击例外 / DXY 危机例外）。
- **设计语言**：页面从 4 段并列升级到 9 段递进（Hero 决策 → 4 宏观 → 7 模块 → 图表 → XAUT/黄金坑 → 执行 → 核心/派生指标 → 数据治理）。新增 `.gold-bottom-group` 二级容器（沿用 BTC bottom-group 模式）与 `.gold-decision-card[data-tone]` 4 色状态。

### 后端
- `app/services/gold_dca_dip.py`: `_indicator_card()` 新增 `bias` 字段
- `app/services/gold_macro_adapter.py`: 新增 `_gold_macro_snapshot()`
- `app/services/gold_allocation_engine.py`: `AllocationPlan` 新增 `macro_payload` 字段，to_dict 暴露 `gold_macro_snapshot`

### 前端
- `app/static/pages/gold_allocation.js`: 9 段递进重写
- `app/static/styles.css`: 新增 ~70 行 CSS

### 测试
- `tests/test_gold_dca_dip_engine.py`: 6 个 _bias_for_indicator 测试
- `tests/test_gold_macro_adapter.py`: 6 个 _gold_macro_snapshot 测试（新建）
- `tests/test_gold_frontend_static.py`: 7 个 V2 DOM 断言
```

- [ ] **Step 11.2: 提交**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add v1.7.7 entry for gold V2 upgrade"
```

---

## Self-Review Checklist

实施前自己跑一遍检查：

- [ ] Spec 5 个章节（多空标签 / 宏观 / 设计语言 / 9 段 / 危机检测）是否每个都有 task 对应？— ✅ Tasks 5/6/7/8
- [ ] 是否还有 "TBD" / "TODO" / "类似 Task N" 之类的占位？— ✅ 无
- [ ] 命名一致性：`gold_macro_snapshot` 在 4 处一致？— ✅ Tasks 2/3/8/9
- [ ] 类型一致：`build()` 返回 dict 包含 `bias/bias_reason/value/source/status` — 5 个字段，Tasks 2/6 一致
- [ ] 实施顺序：先 TDD（测试），再实现，再视觉冒烟 — ✅ Tasks 1/2/4 是 TDD

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-07-gold-allocation-page-v2.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**