# Regime-Aware Scoring Modes (V1.7.4) — Design Spec

- **Date**: 2026-07-02
- **Branch**: `main`
- **Status**: Design approved, awaiting user review → writing-plans

## 1. Problem Statement

### 1.1 现状

技术指标页（`analysis.js`）使用 `app/services/strategy_signal/scoring_engine.py` + `snapshot_builder.py` 计算方向分数（`long_score` / `short_score`）。权重表 `app/monitoring/configs/market_strategy_signal_config_v17.json:23-50` 包含 8 个 sub-score：

| sub-score | 权重 (long) |
|---|---|
| `mtf_trend_bullish` | 0.18 |
| `bullish_structure` | 0.18 |
| `bullish_momentum` | 0.16 |
| `volume_proxy_confirmation` | 0.10 |
| `divergence_support_long` | 0.10 |
| `long_risk_reward` | 0.10 |
| `regime_fit_long` | 0.10 |
| `execution_quality` | 0.08 |

### 1.2 问题

1. **震荡市无抑制**：ADX=15 仍加 15 分（仅 ≥25 时 +10）→ 假信号
2. **2 个 sub-score 浪费**： `volume_proxy_confirmation` 和 `divergence_support_*` 在 `snapshot_builder.py` 实际构造时**固定返回 50**（0 贡献），但权重表里各占 10% → 20% 权重浪费
3. **震荡市不是"无信号"**：用户问"区间震荡时怎么办"时，UI 显示"无方向"是错的——**应该是"高抛低吸模式"**（更适合 mean reversion 策略）
4. **加密 + 短 TF 应主动走 range 模式**：BTC 在 1h/15m 区间震荡频繁，但当前权重和股票一样

### 1.3 设计目标

1. **删除 2 个常量 sub-score**，重新归一化权重（解放 20% 权重）
2. **mode-aware 评分**：检测 regime + ADX + asset_class + TF → 选 weights 集合
3. **mode=range 时显示 UI 横幅**引导用户到形态结构页（不试图在 indicator 层做高抛低吸）
4. **加密 + 短 TF 默认 range 模式**（更符合加密市场短炒节奏）

---

## 2. Architecture

### 2.1 系统边界

**改动**：
- `app/services/strategy_signal/config_loader.py` — 双模式权重结构
- `app/services/strategy_signal/snapshot_builder.py` — mode-aware 评分
- `app/monitoring/configs/market_strategy_signal_config_v17.json` — 新权重定义
- `app/static/pages/analysis.js` — 状态条加 badge
- `app/static/styles.css` — badge 样式
- `tests/test_strategy_signal_*.py` — 新测试

**不动**：
- 形态结构页（`structure/`）— 已有 `rectangle_range` 模式识别（`classic.py:181`），不主动审计
- AI 策略页（`strategy_unified/`）— 它直接读 snapshot 结果，会自动受益
- 后端 service 层（`scoring_engine.py`）— 只改 `weighted_score` 函数支持 mode 参数

### 2.2 数据流

```
StrategySnapshotBuilder.build()
   ↓
detect_mode(regime, adx, asset_class, timeframe)
   ↓ returns "trend" | "range" | "transition"
   ↓
_build_trend_score(... mode)
_build_structure_score(... mode)
... (其他 sub-score 也按 mode 调)
   ↓
weighted_score(values, weights, mode)
   ↓
long_score / short_score
   ↓
UI: status bar shows badge if mode=="range"
```

### 2.3 关键设计决策

1. **震荡市 UI 引导到结构页**（不试图在 indicator 层做高抛低吸） — 用户确认
2. **状态条加 badge**（轻量，黄色 amber） — 用户确认
3. **删除 2 个 sub-score**（解放 20% 权重，重新归一化到 7 个有意义的 sub-score）
4. **mode 选择器 5 层决策**（regime > asset_class+TF > ADX > 默认）

---

## 3. Components

### 3.1 权重配置（`market_strategy_signal_config_v17.json`）

**新结构**：每个 sub-score 有 `trend` / `range` 两种权重

```json
{
  "long_weights_by_mode": {
    "trend": {
      "mtf_trend_bullish": 0.22,
      "bullish_structure": 0.22,
      "bullish_momentum": 0.18,
      "long_risk_reward": 0.13,
      "regime_fit_long": 0.15,
      "execution_quality": 0.10
    },
    "range": {
      "mtf_trend_bullish": 0.05,
      "bullish_structure": 0.05,
      "range_structure": 0.30,
      "low_directional_spread": 0.20,
      "long_risk_reward": 0.15,
      "regime_fit_long": 0.15,
      "execution_quality": 0.10
    }
  },
  "short_weights_by_mode": { /* 对称 */ },
  "neutral_weights": { /* 保留（震荡但非 range 的过渡态） */ }
}
```

注：
- `volume_proxy_confirmation` 和 `divergence_support_*` **完全删除**（不再在权重表中）
- `trend` 模式：mtf_trend + structure = 44% 权重（之前 36%）
- `range` 模式：range_structure + low_directional_spread = 50% 权重

### 3.2 Mode 选择器（`config_loader.py`）

```python
def detect_mode(regime: str, adx: float, asset_class: str, timeframe: str) -> str:
    """5 层决策，返回 'trend' | 'range' | 'transition'。"""
    regime_norm = str(regime or "").lower()
    if regime_norm in ("trend", "trending"):
        return "trend"
    if regime_norm in ("balance", "range", "ranging"):
        return "range"
    if regime_norm in ("transition", "shock"):
        return "transition"
    if asset_class == "crypto" and timeframe in ("1h", "15m"):
        return "range"
    if adx >= 25:
        return "trend"
    if adx < 20:
        return "range"
    return "transition"


def detect_asset_class(instrument_id: str) -> str:
    """检测 'crypto' / 'stock'。"""
    crypto_patterns = ("btc", "eth", "usdt-perp", "btc-usdt", "eth-usdt")
    inst_lower = (instrument_id or "").lower()
    if any(p in inst_lower for p in crypto_patterns):
        return "crypto"
    return "stock"
```

### 3.3 Mode-aware 评分（`snapshot_builder.py`）

```python
def _build_trend_score(indicators, *, mode: str = "trend"):
    """... existing EMA / ADX / VWAP logic ..."""
    bullish, bearish = ..., ...
    # 新增：mode-aware 折扣（实际上折扣在 weights 层处理；这里只算原始 sub-score）
    return clamp(bullish), clamp(bearish)


def _build_long_score(snapshot, mode: str, asset_class: str, timeframe: str) -> float:
    long_values = {k: snapshot[k] for k in long_weights[mode].keys() if k in snapshot}
    return weighted_score(long_values, long_weights[mode])
```

`scoring_engine.py:weighted_score` 接收 weights dict（mode 已确定），无需修改核心逻辑，只需传递 mode-specific weights。

### 3.4 UI 状态条 badge（`pages/analysis.js`）

```js
function renderModeBadge(mode) {
  if (mode !== "range") return "";  // 仅 range 显示
  return `
    <div class="status-mode-badge range-mode">
      <span>📊 区间震荡模式</span>
      <a class="status-mode-link" href="/structure-page">查看形态结构页 →</a>
    </div>
  `;
}
```

插入位置：`renderAnalysisLayout()` 中，状态条之后、metric 卡之前。

### 3.5 样式（`styles.css`）

```css
.status-mode-badge {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin: 12px 0;
  background: rgba(255, 215, 130, 0.18);
  border: 1px solid rgba(214, 138, 42, 0.35);
  border-radius: 8px;
  color: #5a4612;
  font-size: 14px;
}
.status-mode-badge .status-mode-link {
  margin-left: auto;
  color: #8a4d10;
  font-weight: 500;
  text-decoration: underline;
}
```

---

## 4. Data Flow Details

### 4.1 Mode 选择器输出示例

| regime | ADX | asset_class | timeframe | mode |
|---|---|---|---|---|
| trend | 30 | stock | 4h | trend |
| balance | 15 | stock | 4h | range |
| transition | 22 | stock | 4h | transition |
| unknown | 18 | crypto | 1h | range |
| unknown | 32 | crypto | 1h | trend |
| range | 25 | stock | 1d | range |

### 4.2 评分计算示例（震荡市 crypto 1h）

| sub-score | 值 | range 模式权重 | 贡献 |
|---|---|---|---|
| `mtf_trend_bullish` | 35 | 0.05 | 1.75 |
| `bullish_structure` | 40 | 0.05 | 2.0 |
| `range_structure` | 75 | **0.30** | 22.5 |
| `low_directional_spread` | 60 | **0.20** | 12.0 |
| `long_risk_reward` | 65 | 0.15 | 9.75 |
| `regime_fit_long` | 35 | 0.15 | 5.25 |
| `execution_quality` | 80 | 0.10 | 8.0 |
| **总 long_score** | | **1.00** | **61.25** |

vs 之前（删除 2 个 sub-score + 0 折扣）：
- long_score = trend(0.18) + structure(0.18) + momentum(0.16) + vol(0) + div(0) + RR(0.10) + regime(0.10) + exec(0.08) = 假设全 50 → 0.18+0.18+0.16+0+0+0.10+0.10+0.08 = 0.80 → 80

新方法在震荡市**不会**触发 58 阈值（除非所有 sub-score 都很强）。

---

## 5. Error Handling

| 失败场景 | 行为 |
|---|---|
| 缺 ADX | 默认 adx=20，触发 range 模式 |
| 缺 regime | 不匹配前三层 → 进入 ADX 判断 |
| 缺 instrument_id | asset_class = "stock"（默认）|
| 缺 timeframe | 默认 "1d"（不在短 TF 列表 → trend 模式）|
| Mode 选择器返回 "transition" | 走 neutral_weights 现有逻辑（保持向后兼容） |

---

## 6. Testing Strategy

### 6.1 单元测试

新增 `tests/test_regime_mode_detection.py`：

| 测试 | 描述 |
|---|---|
| `test_mode_regime_trend` | regime=trend → mode=trend |
| `test_mode_regime_balance` | regime=balance + ADX=15 → mode=range |
| `test_mode_regime_transition` | regime=transition → mode=transition |
| `test_mode_crypto_short_tf_defaults_range` | btc-usdt-perp + 1h → range |
| `test_mode_crypto_long_tf_no_default` | btc-usdt-perp + 4h → 不默认（按 ADX 决定）|
| `test_mode_high_adx_trend` | ADX=30 + unknown regime → trend |
| `test_mode_low_adx_range` | ADX=15 + unknown regime → range |
| `test_asset_class_btc_crypto` | "btc-usdt-perp" → crypto |
| `test_asset_class_aapl_stock` | "aapl" → stock |
| `test_weight_total_normalized` | 任何 mode 权重和 = 1.0 |
| `test_trend_mode_weights_emphasis_trend` | trend 模式 mtf_trend ≥ 0.18 |
| `test_range_mode_weights_emphasis_range` | range 模式 range_structure ≥ 0.25 |

修改 `tests/test_strategy_signal_snapshot.py`：

| 测试 | 描述 |
|---|---|
| `test_snapshot_uses_trend_mode_by_default` | 默认 mode=trend，权重表匹配 |
| `test_snapshot_uses_range_mode_when_detected` | regime=balance → mode=range 权重表 |
| `test_volume_proxy_zero_weight` | long_score 不含 volume_proxy 项 |
| `test_divergence_zero_weight` | long_score 不含 divergence 项 |

### 6.2 Playwright 集成测试

修改 `tests/test_strategy_degraded_frontend.py` 或新建 `tests/test_analysis_mode_badge.py`：

| 测试 | 描述 |
|---|---|
| `test_range_mode_badge_visible` | mock regime=balance + ADX=15 → mode=range，状态条显示 badge |
| `test_trend_mode_badge_not_visible` | mode=trend 时不显示 badge |
| `test_range_badge_links_to_structure_page` | badge 的"查看形态结构页 →" 链接到 /structure-page |

### 6.3 回归

- 现有 846+ 测试应全部通过
- Ruff 干净
- node --check OK
- Playwright V1.7.2 page guide 仍正常（monitoring-overview）

---

## 7. Backward Compatibility

- ✅ 现有 8 个 sub-score 名保留（`mtf_trend_*`, `bullish_structure`, `bullish_momentum`, `*_risk_reward`, `regime_fit_*`, `execution_quality`, `range_structure`, `low_directional_spread`）
- ✅ 新增 `long_weights_by_mode` 字典结构，向后兼容（保留 `long_weights` 作为 trend 默认）
- ✅ 删 2 个 sub-score 不会破坏现有 snapshot 输出（这两个值本来就是 0 贡献）
- ✅ 形态结构页不受影响（无相关改动）
- ✅ V1.7.2 page guide（monitoring-overview）无需更新

---

## 8. Files Affected

### 修改
- `trading-system-codex/app/monitoring/configs/market_strategy_signal_config_v17.json` — 新权重结构
- `trading-system-codex/app/services/strategy_signal/config_loader.py` — 加 `detect_mode()` + `detect_asset_class()` + 双模式权重
- `trading-system-codex/app/services/strategy_signal/snapshot_builder.py` — 接受 mode 参数
- `trading-system-codex/app/static/pages/analysis.js` — `renderModeBadge()` + 集成到 status bar
- `trading-system-codex/app/static/styles.css` — `.status-mode-badge` 样式
- `trading-system-codex/tests/test_strategy_signal_snapshot.py` — 更新现有测试

### 新增
- `trading-system-codex/tests/test_regime_mode_detection.py` — 12 个新测试
- `trading-system-codex/tests/test_analysis_mode_badge.py` — Playwright 集成测试（3 个）

---

## 9. Out of Scope

- 不在 indicator 层做"高抛低吸"信号（用户已确认：引导到形态结构页看图）
- 不审计形态结构页计算模块（已确认 `rectangle_range` 模式识别在 `classic.py:181` 存在）
- 不修改 AI 策略页（它直接读 snapshot 结果，自动受益于 mode 切换）
- 不修改 service scoring_engine.py 核心（仅传 mode-specific weights）
- 不持久化 mode 到缓存（每次评分实时计算）

---

## 10. Open Questions

None — design approved by user.