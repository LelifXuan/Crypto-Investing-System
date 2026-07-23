## 三个独立改造任务

### Task 1：架构清理（最小破坏路径）

**死代码删除（无 caller）**：
1. `app/services/decision/` —— 仅有 `__init__.py` 引用不存在的 `multi_timeframe.py` 模块；唯一引用方是 module-level skipped 的 `tests/test_data_quality_and_decision.py`。删除整个包。
2. `app/services/portfolio/` —— `RotationAssessment` dataclass 仅被 `app/services/risk.py:9` 引用作类型注解，且从未被赋值。删除包 + 清理 `risk.py` 中的字段。
3. `app/services/execution/` —— `ExecutionLiquidityEngine` 仅被 skipped 测试引用，未接入 active trade path。删除包（注意 `risk.py` 也有 `from .execution` import）。
4. `app/services/etf_quotes.py` —— 兼容性 shim，零调用方。删除。
5. `tests/test_data_quality_and_decision.py` —— module-level skip 且对应的模块不存在。删除。

**版本化配置收敛（保留当前版本，删除旧版）**：
6. `app/monitoring/configs/macro_data_sources.v1.json` vs `.v2.json` —— 经查 `app/services/macro/source_registry.py` 当前仅引用 v2。删除 v1。
7. `app/monitoring/configs/market_strategy_signal_config_v16.json` vs `_v17.json` —— 确认 `config_loader.py` 当前加载 v17。删除 v16。

**翻译子系统清理**：
8. `app/services/translation/providers/router.py` 中的 `local_glossary` 分支返回 `None`（死代码）。删除该分支。

**验证**：
- `python -m pytest tests/ -x -q`（确认无回归）
- `python -m compileall app/`（确认无 import 残留）

预期删除 ~8 个文件，影响 < 50 行代码。

---

### Task 2：监控总览 10 个未获取指标

**分四类修复**：

#### A. 1 项"等待发布"——失业率 (US Unemployment Rate)

`indicator_monitoring.py:1113-1163` 的 `pending_release` 分支：找不到 BLS 日历事件就 pending。

**修复**：在 `macro_indicator_api_map.v1.json` 的 `unemployment_rate.sources` 列表里追加 FRED `UNRATE` 作为二级回退源。当 `pending_release` 状态下回退路径用 FRED 拿月度数。

不动 `indicator_catalog.yaml`（保留 BLS 日历路径作为 primary）。

#### B. 6 项"缓存未命中"——FED ops 指标

缺失指标：`fed_iorb` / `fed_on_rrp_rate` / `fed_soma_treasury` / `fed_soma_mbs` / `fed_srf_usage` / `fed_discount_window`

**修复**（按 `fed_balance_sheet` lines 1867–1889 模式）：
1. `indicator_catalog.yaml`：追加 6 个 `IndicatorDefinition`，每个 `source_provider: fred`, `source_kind: raw_series`, `external_symbol: <FRED series>`：
   - `fed_iorb` → `IORB`
   - `fed_on_rrp_rate` → `RRPONTSYAWARD`
   - `fed_soma_treasury` → `WSHOMCB`
   - `fed_soma_mbs` → `MBS10Y`（注：SOMA MBS 在 FRED 上通常用 `WSHOMCB` 拆分或 `MBS` 系列；用最稳的 `MBS10Y` 或 `WSHOMCB-MBS`；执行时按 FRED 可查的实际 series 调整）
   - `fed_srf_usage` → `RPTSYD`
   - `fed_discount_window` → `WLCFLPCL`
2. `refresh_policies.yaml`：在 `macro:` block 追加 6 条策略，每日 1 次 cron（这些 series 大多仅在工作日更新）。
3. **需要用户配置 `FRED_API_KEY`** 到 `runtime/config/portable.env`（FRED 免费申请，https://fred.stlouisfed.org/docs/api/api_key.html）。

#### C. 1 项"未配置数据源"——FED TGA NET CHANGE 4W

map 写了 `source: fred_derived, transform: weekly_diff_rolling_4w`，但 provider registry 没有 `fred_derived`，catalog 也无此 indicator。

**修复**（最简方案：在 overview 层做派生，不动 provider）：
1. `indicator_catalog.yaml`：追加 `fed_tga_net_change_4w`，`source_provider: fred`, `source_kind: derived`, `calc_params: { upstream: tga, formula: weekly_diff_rolling_4w }`, `is_enabled: true`。
2. `refresh_policies.yaml`：每日 1 次 cron。
3. `app/services/macro_overview.py:_indicator_read()`：扩展派生分支，复用已有的 `_derived_indicator_read()` 模式，按 `formula: weekly_diff_rolling_4w` 从 `tga` observation 计算滚动 4 周差。
4. 也可选择：让 `indicator_monitoring.py:_transform_macro_result()`（line 1288-1325）的 transform switch 支持该 transform——这样直接走统一管道。**采用第二种**，与现有 transform 系统保持一致。

#### D. 2 项"数据源请求失败"——HYG + USD/CNY

`tiingo.py:66` 和 `openexchangerates.py:30` 在密钥缺失时抛 `AuthMissing`。

**修复**：
1. **需要用户配置** `TIINGO_API_KEY` 和 `OPENEXCHANGERATES_APP_ID` 到 `runtime/config/portable.env`（两个都免费申请）。
2. 若网络受限（中国大陆），需要 `runtime/config/proxy_state.json` 中启用 `proxy_detection`（已有声明，需在 `portable_macro_never_empty_policy.v2.json` 已配置）。

**用户需要提供的密钥**（在执行前会暂停确认）：
- `FRED_API_KEY`（FRED，免费，30 秒申请）
- `TIINGO_API_KEY`（Tiingo，免费层 50 symbols/day）
- `OPENEXCHANGERATES_APP_ID`（OpenExchangeRates，免费层 1000 req/月）

> 注：Fed TGA NET CHANGE 4W 派生指标用 FRED `WTREGEN`（已有 upstream `tga`），不需额外密钥。

**验证**：执行 `IndicatorMonitoringService.run_due_policies()` 后，"未获取指标" 应从 10 降至 0；`MacroSourceHealth` 各行 `status="live"`。

---

### Task 3：AI 策略触发条件绝对时间戳

**问题**：当前文案 `"有效期：未来 20 根 15M K线"` 和 `"下一检查：下一根 4H 收盘"` 在策略生成时完全可以换算成 ISO 时间。

**前端修改**（`app/static/pages/strategy/renderExecutionPlan.js:64-79`）：
```js
function triggerText(plan, decision) {
  if ((plan.order_type || decision.order_type) === "MARKET") {
    return plan.price_protection?.reason || decision.price_protection?.reason || "市价保护已通过";
  }
  const conditions = plan.activation_conditions?.length
    ? plan.activation_conditions
    : decision.activation_conditions || [];

  // Primary path: backend-supplied absolute timestamp
  const validIso = plan.valid_until_iso || decision.valid_until_iso || "";
  const validText = validIso
    ? `有效期至 ${formatIsoShort(validIso)}`
    : (function () {
        const m = String(plan.valid_until || decision.valid_until || "").match(/^([^:]+):(\d+)_bars$/);
        return m ? `有效期：未来 ${m[2]} 根 ${m[1].toUpperCase()} K线` : "";
      })();

  const nextIso = decision.next_check_at_iso || "";
  const nextText = nextIso
    ? `下一检查：${formatIsoShort(nextIso)}`
    : formatLegacyNextCheck(decision.next_check);

  return [...conditions, validText, nextText ? `下一检查：${nextText}` : ""]
    .filter(Boolean)
    .join("；") || "无需额外触发";
}

function formatIsoShort(iso) {
  // "2026-07-21T18:00:00+00:00" → "2026-07-21 18:00 UTC"
  return `${iso.slice(0, 16).replace("T", " ")} UTC`;
}

function formatLegacyNextCheck(raw) {
  return String(raw || "")
    .replace("next_4h_close", "下一根 4H 收盘")
    .replace("next_1h_close", "下一根 1H 收盘");
}
```

注意：上面的 `下一检查` 前缀有重复，需要简化（写成单一变量 `nextText` 后再统一拼接）。最终代码形如：
```js
return [...conditions, validText, nextText].filter(Boolean).join("；") || "无需额外触发";
```

**同步更新 3 处其它引用**：
- `app/static/pages/strategy/renderTradeDecision.js:48`
- `app/static/pages/strategy/renderEvidenceStack.js:76`
- `app/static/pages/strategy/renderMarketOperation.js:131`

把这 4 个文件都改用同一个 `formatNextCheck(decision, op)` 辅助函数（提取到 `renderExecutionPlan.js` 同目录的 `formatHelpers.js` 或 inline 在每个文件）。

**后端 schema 扩展**：

`app/services/strategy_unified/contracts.py` —— `TradePlan`（line 173-216）新增：
```python
valid_until_iso: str = ""
next_check_at_iso: str = ""
```

`app/services/strategy_unified/trade_decision.py` —— `TradeDecision`（line 11-49）新增：
```python
valid_until_iso: str = ""
next_check_at_iso: str = ""
```

`direction_resolution.py` 的 `OperationCard`（line 116-130）和 `DirectionResolutionResult`（line 151-167）：
```python
next_check_at_iso: str = ""
```

**后端计算逻辑**：

在 `trade_decision.py` 顶部加 helper：
```python
from datetime import datetime, timedelta, timezone
import math

UTC = timezone.utc

_BAR_HOURS = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24, "1w": 168, "1M": 720, "30d": 720}

def _bars_to_iso(now: datetime, timeframe: str, bars: int) -> str:
    delta_h = bars * _BAR_HOURS.get(timeframe, 1)
    return (now + timedelta(hours=delta_h)).isoformat()

def _next_close_iso(now: datetime, timeframe: str = "4h") -> str:
    secs = _BAR_HOURS.get(timeframe, 4) * 3600
    boundary = math.ceil(now.timestamp() / secs) * secs
    return datetime.fromtimestamp(boundary, tz=UTC).isoformat()
```

修改 `trade_decision.py:253-256`：
```python
now = datetime.now(UTC)
bars = int(thresholds.get("setup_valid_bars", {}).get(timeframe, 20))
valid_until=f"{timeframe}:{bars}_bars",
valid_until_iso=_bars_to_iso(now, timeframe, bars),
```

修改 `trade_decision.py:_decision()` 接收 `next_check_at_iso` 参数并写入 dataclass。在所有 `self._decision(...)` 调用点（line 82+ 共 9 处）传递一个默认值 `_next_close_iso(datetime.now(UTC), "4h")`。

修改 `direction_resolution.py:194/218/250/428/664-677` 的 `next_check_for_module` / `resolve`：根据 module TF 计算对应 `_next_close_iso(now, tf)`。

**统一 service 修复**：

`app/services/strategy_unified/unified_service.py:492-497`：
```python
@staticmethod
def _next_check_time(contexts: Mapping[str, Any]) -> str | None:
    for context in contexts.values():
        event_features = getattr(context, "event_features", None)
        if isinstance(event_features, Mapping) and event_features.get("next_check_time"):
            return str(event_features["next_check_time"])
    # NEW: 派生 fallback
    return _next_close_iso(datetime.now(UTC), "4h")
```

`app/services/strategy_unified/cross_horizon.py:287`：
```python
next_check_time: next_check_time or _next_close_iso(now, "4h"),
```

**`market_context.py:240`** 也补：
```python
event_features["next_check_time"] = _next_close_iso(datetime.now(UTC), tf)
```
保证 `renderEventWatch.js:14` 也获得绝对时间戳。

**验证**：
- `python -m pytest tests/ -x -q`（确认 backend schema 改动不破坏 snapshot test）
- 刷新 AI 策略页，确认 "有效期至 YYYY-MM-DD HH:MM UTC" 和 "下一检查：YYYY-MM-DD HH:MM UTC" 格式正确
- 旧版前端缓存的相对文案能优雅降级（plan/decision 有 `valid_until_iso` 时用 ISO，没有时退回原相对文案）

---

### 执行顺序与依赖

1. **Task 1（清理）** —— 完全独立，可立即执行
2. **Task 3（绝对时间戳）** —— 独立，纯后端 + 前端
3. **Task 2（监控指标）** —— 依赖用户提供 3 个 API key

建议顺序：1 → 3 → 2（Task 2 会要求输入密钥）。

### 文件改动清单

| 任务 | 修改 | 删除 |
|---|---|---|
| Task 1 | `app/services/risk.py`（清理 dead import/字段） | `app/services/decision/`、`app/services/portfolio/`、`app/services/execution/`、`app/services/etf_quotes.py`、`tests/test_data_quality_and_decision.py`、`macro_data_sources.v1.json`、`market_strategy_signal_config_v16.json` |
| Task 2 | `app/monitoring/configs/indicator_catalog.yaml`、`refresh_policies.yaml`、`macro_indicator_api_map.v1.json`、`app/services/indicator_monitoring.py`（新增 transform 分支）、`runtime/config/portable.env` | —— |
| Task 3 | `app/services/strategy_unified/contracts.py`、`trade_decision.py`、`direction_resolution.py`、`unified_service.py`、`cross_horizon.py`、`market_context.py`、`app/static/pages/strategy/renderExecutionPlan.js`、`renderTradeDecision.js`、`renderEvidenceStack.js`、`renderMarketOperation.js`（新增 helper + ISO 路径） | —— |

### 验收命令

```bash
# Task 1 + Task 3 验证
python -m pytest tests/ -x -q

# Task 1 编译验证
python -m compileall app/

# Task 2 验证：手动触发 macro refresh + curl /api/v1/monitoring/overview
# 预期 "未获取指标" 从 10 → 0（前提：FRED/Tiingo/OpenExchangeRates 三个 key 已配置）
```