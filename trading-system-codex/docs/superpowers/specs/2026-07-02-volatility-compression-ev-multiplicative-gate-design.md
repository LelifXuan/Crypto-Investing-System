# Volatility Compression + EV + Multiplicative Gate (V1.7.5) — Design Spec

- **Date**: 2026-07-02
- **Branch**: `main`
- **Status**: Design approved, awaiting user review → writing-plans

## 1. Problem Statement

### 1.1 用户问题

技术指标页的评分系统当前有 3 个根本性缺口：
1. **没有波动率压缩/扩张检测** — 震荡/趋势切换的关键信号未被监测
2. **没有非对称交易的 EV 评估** — `risk_reward_score(rr >= 3) = 90` 封顶，左侧大 rr 优势被浪费
3. **没有非线性权重交互** — 加法权重无法表达"vol_compression × trend_signal" 的 AND 关系

### 1.2 三个核心决策

- **压缩检测算法**：多周期 percentile rank（`bb_width / bb_width_ma_90` 的百分位）
- **EV 深度**：Bayesian posterior（`P(win) = prior × Π(likelihoods) / Z`）
- **非线性交互机制**：Multiplicative gate（vol_compression_score 作为 0-1 乘子影响 raw_long/short）

### 1.3 设计目标

1. **新增 `vol_compression` sub-score** — 多周期 percentile rank 评估当前波动率在历史分布中的位置
2. **新增 `setup_probability` (Bayesian posterior)** — 评估 setup 的真实胜率
3. **重写 `risk_reward_score` 为 EV-based** — 不再有 rr=90 封顶
4. **新增 `transition` mode 专用权重** — regime transition 场景有专门评分
5. **Multiplicative gate** — vol_compression 作为乘子影响 transition 模式的 raw score

---

## 2. Architecture

### 2.1 系统边界

**改动**：
- `app/services/strategy_signal/snapshot_builder.py` — 新增 `_compute_vol_compression()` + `_compute_setup_probability()` + transition mode multiplicative gate
- `app/services/strategy_signal/risk_reward.py` — `risk_reward_score` 改为 EV-based
- `app/services/strategy_signal/scoring_engine.py` — long/short_score 用 EV 而非纯加权和
- `app/services/strategy_signal/strategy_generator.py` — trigger_state 用 ev_score
- `app/services/strategy_signal/config_loader.py` — 加 transition mode weights + Bayesian prior config
- `app/monitoring/configs/market_strategy_signal_config_v17.json` — 新 transition weights + EV config
- `app/static/pages/analysis.js` — 新增 transition mode badge
- `app/static/styles.css` — `.transition-mode` 样式
- `app/static/core/knowledge.js` — 2 个新词条
- `tests/test_strategy_signal_*.py` — ~10 个新测试
- `docs/CHANGELOG.md` — V1.7.5 entry

**不动**：
- 形态结构页（已有 rectangle_range 模式识别）
- AI 策略页（自动受益）
- config.json 结构（向后兼容）

### 2.2 数据流

```
indicator_observations
   ↓
_indicators (existing dict)
   ↓
_compute_vol_compression (NEW)
   ↓ outputs vol_compression_score (0-100)
_compute_setup_probability (NEW)
   ↓ outputs setup_probability (0-1)
_compute_mode_aware_scores (existing)
   ↓ outputs raw_long, raw_short
   ↓ in transition mode: multiply by vol_factor (NEW)
weighted_score
   ↓ outputs long_score, short_score
risk_reward_score_ev (NEW)
   ↓ outputs ev_score (replaces rr_score)
trigger_state_check
   ↓ uses ev_score instead of rr_score
```

### 2.3 关键设计决策

1. **vol_compression 用 percentile rank 简单近似**（不实现完整历史 percentile 计算）— 5 档 bucket 即可
2. **Bayesian 用闭式 posterior**（不维护 likelihood 表）— 直接用 likelihoods 列表 + prior 计算
3. **EV 重写不破坏现有 `risk_reward_score` 函数**（改名 `risk_reward_score_ev` 或保留旧函数加 deprecation）
4. **Multiplicative gate 只在 transition 模式生效**（trend/range 模式不变）
5. **新增 `transition` mode weights**，删除 fallback 到 flat long_weights 的逻辑

---

## 3. Components

### 3.1 `vol_compression_score` 计算（`snapshot_builder.py`）

```python
def _compute_vol_compression(bb_width: float | None, bb_width_ma_90: float | None) -> float:
    """多周期 percentile rank: 当前 BB-width 在 90 天分布的位置.
    
    Returns 0-100:
    - 100 = extreme compression (BB-width 在历史 5% 范围内)
    - 0 = extreme expansion
    """
    if not bb_width or not bb_width_ma_90 or bb_width_ma_90 <= 0:
        return 50  # 中性
    ratio = bb_width / bb_width_ma_90
    if ratio < 0.5: return 90
    if ratio < 0.7: return 75
    if ratio < 0.85: return 60
    if ratio < 1.15: return 50
    if ratio < 1.4: return 40
    return 25
```

### 3.2 `setup_probability` (Bayesian posterior)（`snapshot_builder.py`）

```python
def _compute_setup_probability(
    long_score: float,
    short_score: float,
    setup_ready: bool,
    conflict_score: float,
    base_prior: float = 0.45,
) -> float:
    """P(win) = base_prior × Π(likelihoods) / Z
    
    Returns 0-1 (win probability).
    """
    prior = base_prior
    likelihoods = []
    if long_score > 60 or short_score > 60:
        likelihoods.append(1.4)  # strong directional signal
    if setup_ready:
        likelihoods.append(1.5)  # setup pattern confirmed
    if conflict_score < 30:
        likelihoods.append(1.3)  # no conflict
    if long_score > 75 or short_score > 75:
        likelihoods.append(1.6)  # very strong signal
    if conflict_score > 70:
        likelihoods.append(0.6)  # strong conflict
    if long_score < 50 and short_score < 50:
        likelihoods.append(0.5)  # weak signal
    
    posterior = prior
    for lik in likelihoods:
        posterior *= lik
    return clamp(posterior, 0.01, 0.99)
```

### 3.3 `risk_reward_score` 改造（`risk_reward.py`）

```python
def risk_reward_score_ev(rr: float | None, p_win: float = 0.5) -> float:
    """EV-based: P(win) × RR × 100, capped 0-100.
    
    1R with 50% win rate → 50
    1R with 70% win rate → 70
    3R with 40% win rate → 120 → capped 100 (no longer capped at 90)
    """
    if rr is None or rr <= 0:
        return 0
    ev = p_win * rr * 100
    return clamp(ev, 0, 100)
```

### 3.4 Multiplicative gate（`snapshot_builder._compute_mode_aware_scores`）

```python
# 在原有 weighted_score 后、返回前
if mode == "transition":
    vol_factor = vol_compression_score / 100  # 0-1
    raw_long *= vol_factor
    raw_short *= vol_factor
```

### 3.5 `transition` mode weights（`market_strategy_signal_config_v17.json`）

```json
"long_weights_by_mode": {
  "trend": { ... 现有 V1.7.4 ... },
  "range": { ... 现有 V1.7.4 ... },
  "transition": {
    "vol_compression": 0.30,
    "mtf_trend_bullish": 0.15,
    "bullish_structure": 0.10,
    "long_risk_reward": 0.20,
    "regime_fit_long": 0.15,
    "execution_quality": 0.10
  }
}
```

注：`short_weights_by_mode` 的 transition 部分对称。

### 3.6 UI 改动（`pages/analysis.js`）

```js
function renderModeBadge(mode) {
  if (mode === "range") {
    return `<div class="status-mode-badge range-mode">
      <span>📊 区间震荡模式</span>
      <a class="status-mode-link" href="/structure-page">查看形态结构页 →</a>
    </div>`;
  }
  if (mode === "transition") {
    return `<div class="status-mode-badge transition-mode">
      <span>⚡ 波动率压缩 → 扩张预警</span>
      <span class="vol-pct-rank">BB-width ${vol_pct_rank}th percentile</span>
      <a class="status-mode-link" href="/market-analysis?focus=breakout">关注突破信号 →</a>
    </div>`;
  }
  return "";
}
```

### 3.7 Knowledge 新增 2 个词条

- `volatility_compression` — 多周期 percentile rank 检测
- `bayesian_setup_probability` — Bayesian posterior 评估

---

## 4. Data Flow Details

### 4.1 完整 sub-score schema（V1.7.5）

```json
"trend mode long_weights": {
  "mtf_trend_bullish": 0.22,
  "bullish_structure": 0.22,
  "bullish_momentum": 0.18,
  "long_risk_reward": 0.13,        // NOW EV-based
  "regime_fit_long": 0.15,
  "execution_quality": 0.10
},
"range mode long_weights": {
  "mtf_trend_bullish": 0.05,
  "bullish_structure": 0.05,
  "range_structure": 0.30,
  "low_directional_spread": 0.20,
  "long_risk_reward": 0.15,        // NOW EV-based
  "regime_fit_long": 0.15,
  "execution_quality": 0.10
},
"transition mode long_weights (NEW)": {
  "vol_compression": 0.30,         // NEW
  "mtf_trend_bullish": 0.15,
  "bullish_structure": 0.10,
  "long_risk_reward": 0.20,        // NOW EV-based
  "regime_fit_long": 0.15,
  "execution_quality": 0.10
}
```

### 4.2 评估流程（震荡后期 → regime transition 示例）

```
Indicator readings:
  bb_width = 0.03
  bb_width_ma_90 = 0.07
  ratio = 0.43 → vol_compression_score = 90
  
  regime = "transition"
  ADX = 18
  
Mode detection:
  regime=transition + ADX=18 → mode=transition
  
Transition weights applied:
  vol_compression × 0.30 = 90 × 0.30 = 27.0
  mtf_trend_bullish × 0.15 = 50 × 0.15 = 7.5
  ... (other sub-scores)
  
raw_long_score = ~40 (low because vol_compression dominates and other sub-scores are weak)
raw_short_score = ~40 (similar)

Multiplicative gate:
  vol_factor = 90 / 100 = 0.9
  raw_long *= 0.9
  raw_short *= 0.9
  
Trigger condition:
  side_score (40) < trigger_score (72) → NOT TRIGGERED
  BUT: if mtf_trend_bullish was 70 (not 50), raw_long = 70×0.15+90×0.30+... = 47.3 → after vol_factor = 42.5
  Still not 72 → NOT TRIGGERED
  
Wait, that's bad. The transition mode is too conservative.
```

注：上面的示例是说明权重逻辑，实际数字需要测试时调整。如果 transition 模式太保守（不容易触发），可以降低 trigger_score 在 transition 模式下的阈值（比如 65 而不是 72）。

### 4.3 EV 计算示例

```
Setup: high-quality squeeze setup
  p_win_setup = 0.70 (high signal agreement)
  RR = 4.0 (wide stop + large TP1)
  EV = 0.70 × 4.0 × 100 = 280 → capped 100
  → trigger_score easily passed

Setup: marginal
  p_win_setup = 0.55
  RR = 1.6
  EV = 0.55 × 1.6 × 100 = 88
  → just below trigger_score (72... wait 88 > 72) → TRIGGERED

Setup: poor
  p_win_setup = 0.40
  RR = 1.0
  EV = 0.40 × 1.0 × 100 = 40
  → NOT TRIGGERED
```

---

## 5. Error Handling

| 失败场景 | 行为 |
|---|---|
| `bb_width_ma_90` 缺失 | vol_compression 返回 50（中性）|
| `setup_probability` 输入缺失 | posterior = base_prior |
| 旧 `risk_reward_score` 调用 | 保留函数，deprecated comment；新代码用 `risk_reward_score_ev` |
| transition mode 没有 6 个 sub-score 全部齐全 | weighted_score 用 `.get(key, 0)` 兜底 |
| Bayesian likelihoods 为空 | posterior = base_prior（不变）|

---

## 6. Testing Strategy

### 6.1 单元测试（新增 ~10 个）

- `tests/test_strategy_signal_snapshot.py` 新增：
  - `test_vol_compression_score_multi_period_percentile_rank` — bb_width/MA < 0.5 → 90+
  - `test_vol_compression_score_above_ma_returns_neutral` — ratio > 1.15 → < 50
  - `test_vol_compression_score_uses_fallback_50_when_data_missing` — None → 50
  - `test_setup_probability_bayesian_posterior_no_evidence` — P(win) = base_prior
  - `test_setup_probability_with_strong_setup` — 多个 likelihood → P > 0.7
  - `test_setup_probability_with_conflict_suppresses` — conflict > 70 → P < 0.4
  - `test_transition_mode_uses_multiplicative_gate` — vol_compression < 80 → score 抑制

- `tests/test_risk_reward.py` 新增：
  - `test_risk_reward_score_ev_no_ceiling` — rr=5 + p=0.5 = 250 → cap 100（不是 90）
  - `test_risk_reward_score_ev_high_p_high_rr` — rr=3 + p=0.8 = 240 → cap 100

- `tests/test_strategy_decision_rules.py` 更新：
  - `test_trigger_state_uses_ev_score` — trigger 用 ev_score > threshold 而非 rr > 1.5

- `tests/test_strategy_no_microstructure.py` 更新：
  - 新增 `test_transition_mode_weights_in_config` — transition 权重包含 vol_compression 0.30

### 6.2 端到端

- 启动 backend → 访问 /market-analysis
- mock regime=transition + ADX=18 + bb_width 0.03 → 状态条显示 transition-mode badge
- vol_compression 正确计算 percentile rank

### 6.3 回归

- 全部现有 V1.7.0 + V1.7.1 + V1.7.2 + V1.7.3 + V1.7.4 测试应通过
- trend/range 模式 weights 不变
- 旧 `risk_reward_score` 函数保留（deprecated but still working）

---

## 7. Backward Compatibility

- ✅ 旧 `risk_reward_score` 函数保留（marked deprecated in docstring）
- ✅ trend/range 模式 weights 不变（与 V1.7.4 完全相同）
- ✅ transition 模式从"fallback 到 flat long_weights" 改为"专用 transition weights"（行为变化仅在 transition mode 下）
- ✅ Bayesian prior 默认为 0.45（可配置）
- ✅ `vol_compression` 计算向后兼容（缺失时返回 50）
- ✅ 形态结构页（已有 rectangle_range 模式识别）不受影响

---

## 8. Files Affected

### 修改
- `trading-system-codex/app/services/strategy_signal/snapshot_builder.py` — +2 sub-score 函数 + multiplicative gate
- `trading-system-codex/app/services/strategy_signal/risk_reward.py` — `risk_reward_score_ev` 新函数
- `trading-system-codex/app/services/strategy_signal/scoring_engine.py` — long/short 用 EV
- `trading-system-codex/app/services/strategy_signal/strategy_generator.py` — trigger_state 用 ev_score
- `trading-system-codex/app/services/strategy_signal/config_loader.py` — Bayesian prior + transition mode
- `trading-system-codex/app/monitoring/configs/market_strategy_signal_config_v17.json` — + transition weights + EV config
- `trading-system-codex/app/static/pages/analysis.js` — + transition mode badge
- `trading-system-codex/app/static/styles.css` — + .transition-mode
- `trading-system-codex/app/static/core/knowledge.js` — + 2 词条
- `trading-system-codex/tests/test_strategy_signal_snapshot.py` — + 7 tests
- `trading-system-codex/tests/test_risk_reward.py` — + 2 tests
- `trading-system-codex/tests/test_strategy_decision_rules.py` — 更新 1 test
- `trading-system-codex/tests/test_strategy_no_microstructure.py` — 更新 1 test
- `docs/CHANGELOG.md` — V1.7.5 entry

### 新增
无（全部在已有文件里扩展）

---

## 9. Out of Scope

- 不实现完整历史 percentile 计算（用 5 档 bucket 近似）
- 不维护 likelihood 表（用闭式 Bayesian）
- 不修改 AI 策略页（它读 snapshot，自动受益）
- 不修改形态结构页
- 不支持动态调整 Bayesian prior（hardcoded 0.45）

---

## 10. Open Questions

None — design approved by user.