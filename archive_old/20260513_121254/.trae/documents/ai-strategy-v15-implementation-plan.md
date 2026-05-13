# AI 策略框架 v15 完整实现计划

## 一、需求分析

基于 `market_strategy_signal_rules_v15.py`、`market_strategy_signal_config_v15.json` 和 `ai_strategy_market_signal_framework_v15.md`，需要：

1. **新框架实现** - 参考三个参考文件，实现完整的 v15 框架
2. **差距分析** - 对照目标查看现况未完成的工作任务
3. **完成未实现功能** - 补充缺失的代码
4. **UI 重构** - 用户持仓输入不应占据页面重要位置

---

## 二、当前状态分析

### 2.1 现有代码 vs v15 需求对照

| 模块 | 当前实现 (v1.4) | v15 需求 | 差距 |
|------|----------------|----------|------|
| **策略状态** | 简单 Action 枚举 (NO_TRADE ~ RISK_OFF) | 17 种状态机 | 需要全新状态机 |
| **策略类型** | 无特定类型 | 12 种入场策略类型 | 需要识别引擎 |
| **评分体系** | 5 因子加权 | 8 因子 long_score + 8 因子 short_score | 需要重构评分 |
| **Penalty 项** | conflict_level 惩罚 | 5 种专项惩罚 | 需要扩展 |
| **策略方案** | 通用 PositionPlan | 每种策略类型独立 Plan | 需要模板化 |
| **用户持仓** | 占据重要位置 | 不应占据重要位置 | 需要 UI 重构 |
| **配置文件** | ai_strategy_rules_config_v14.json | market_strategy_signal_config_v15.json | 新建 |

### 2.2 已实现部分

- ✅ `app/services/strategy/snapshot_builder.py` - 快照构建
- ✅ `app/services/strategy/decision_rules.py` - 规则引擎基础
- ✅ `app/services/strategy/orchestrator.py` - 编排器
- ✅ `app/api/v1/endpoints/strategy.py` - API 端点
- ✅ 数据库表 `strategy_decision`, `strategy_signal`, `strategy_signal_outcome`

### 2.3 缺失部分

- ❌ `MarketStrategySignalEngine` 核心引擎
- ❌ 17 种策略状态机
- ❌ 12 种策略类型识别
- ❌ v15 评分公式实现
- ❌ 5 种专项惩罚
- ❌ 策略方案模板
- ❌ v15 配置文件
- ❌ 前端 v15 UI 组件

---

## 三、需要修改的文件

### 3.1 后端 Python

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/services/strategy/decision_rules.py` | 重构 | 新增 v15 引擎 |
| `app/services/strategy/orchestrator.py` | 扩展 | 新增 v15 调用 |
| `app/schemas/strategy.py` | 扩展 | 新增 v15 Schema |
| `app/api/v1/endpoints/strategy.py` | 扩展 | 新增 v15 API |
| `app/monitoring/configs/` | 新建 | v15 配置文件 |

### 3.2 前端

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/static/pages/strategy.js` | 重构 | UI 布局重构 |
| `app/static/core/api.js` | 扩展 | v15 API 调用 |
| `app/static/styles.css` | 扩展 | v15 样式 |

### 3.3 数据库

| 表 | 修改 | 说明 |
|---|------|------|
| `strategy_decision` | 扩展字段 | 新增 strategy_state, pattern_type, components_json |
| `strategy_signal` | 扩展字段 | 新增 entry_conditions_json, invalidation_criteria_json |

---

## 四、需要新增的文件

### 4.1 后端新增

```
app/services/strategy/
├── market_strategy_signal_engine_v15.py  # 核心引擎 (新)
├── market_strategy_signal_config_v15.json # 配置文件 (新)
├── strategy_pattern_recognizer.py        # 策略类型识别 (新)
└── strategy_signal_state_machine.py      # 状态机 (新)
```

### 4.2 前端新增

```
app/static/
├── components/
│   ├── strategy-v15-hero.js     # 主显示组件
│   ├── strategy-state-badge.js  # 状态徽章
│   └── strategy-signal-card.js   # 信号卡片
└── strategy-v15.css              # v15 样式
```

### 4.3 数据库迁移

```
alembic/versions/
└── 0010_strategy_v15.py         # v15 表结构迁移
```

---

## 五、详细实现步骤

### 步骤 1: 创建 v15 配置文件

创建 `app/monitoring/configs/market_strategy_signal_config_v15.json`:

```json
{
  "version": "market_strategy_signal_v15.0.0",
  "weights": {
    "long_score": {
      "mtf_trend_bullish": 0.18,
      "bullish_structure": 0.18,
      "bullish_momentum": 0.14,
      "bullish_flow": 0.14,
      "derivatives_long_confirmation": 0.10,
      "execution_quality": 0.08,
      "long_risk_reward": 0.10,
      "regime_fit_long": 0.08
    },
    "short_score": {...}
  },
  "penalties": {
    "funding_crowding": 8,
    "oi_price_divergence": 6,
    "cvd_divergence": 5,
    "late_entry_risk": 4,
    "event_risk": 10
  },
  "thresholds": {
    "direction_confidence": {...},
    "risk_reward": {...},
    "execution": {...}
  },
  "state_transitions": {...},
  "pattern_templates": {...}
}
```

### 步骤 2: 创建核心引擎

创建 `app/services/strategy/market_strategy_signal_engine_v15.py`:

- `StrategySignalState` - 17 种状态枚举
- `StrategyPatternType` - 12 种策略类型
- `StrategyInputs` - 输入数据类
- `MarketStrategySignalEngine` - 核心引擎类

### 步骤 3: 创建状态机

创建 `app/services/strategy/strategy_signal_state_machine.py`:

- 状态转换逻辑
- 状态持久化

### 步骤 4: 创建策略类型识别器

创建 `app/services/strategy/strategy_pattern_recognizer.py`:

- 识别 12 种策略类型
- 生成对应 entry_conditions, invalidation_criteria

### 步骤 5: 更新 Schema

更新 `app/schemas/strategy.py`:

- 新增 `StrategyV15DecisionSchema`
- 新增 `StrategyV15SignalCardSchema`

### 步骤 6: 更新 API

更新 `app/api/v1/endpoints/strategy.py`:

- 新增 `/strategy/v15/bundle` 端点
- 新增 `/strategy/v15/decision` 端点

### 步骤 7: 更新 Orchestrator

更新 `app/services/strategy/orchestrator.py`:

- 新增 v15 引擎调用

### 步骤 8: 创建数据库迁移

创建 `alembic/versions/0010_strategy_v15.py`:

- 扩展 strategy_decision 表
- 扩展 strategy_signal 表

### 步骤 9: 重构前端 UI

重构 `app/static/pages/strategy.js`:

- 策略状态为主显示 (40% 高度)
- 持仓输入最小化 (右上角收起)
- 信号卡片化展示
- 渐进式披露 (详情折叠)

---

## 六、UI 布局设计

### 6.1 重构原则

1. **策略状态为主** - 屏幕上方展示当前状态和评分
2. **持仓输入最小化** - 右上角收起按钮，仅显示状态
3. **信号卡片化** - 每个策略类型独立卡片
4. **渐进式披露** - 详情默认折叠

### 6.2 新布局结构

```
+------------------------------------------------------------------+
|  [Logo]    AI Strategy v15       [持仓: flat ▼] [收起]            |
+------------------------------------------------------------------+
|                                                                   |
|  +----------------------+  +----------------------+              |
|  |    STRATEGY STATE    |  |    DIRECTION SCORES   |              |
|  |   LONG_STRATEGY_ACTIVE| |  Long: 72  Short: 35 |              |
|  |   Pattern: breakout   | |  Neutral: 15          |              |
|  |   Confidence: 78%     | |  Direction: 0.52       |              |
|  +----------------------+  +----------------------+              |
|                                                                   |
|  +------------------------------------------------------------------+
|  |                  SCORE COMPONENTS BAR                          |
|  |  [MTF ████████░░ 72%] [Struct ██████░░░░ 58%] [Mom ███████░░] |
|  +------------------------------------------------------------------+
|                                                                   |
|  +------------------------+  +------------------------+           |
|  |  LONG SIGNAL CARDS    |  |  SHORT SIGNAL CARDS    |           |
|  |  [breakout_long    ▼] |  |  (no signals)         |           |
|  |  Entry: $67,000       |  |                        |           |
|  |  Stop:  $65,800       |  |                        |           |
|  |  TP:   $69,500        |  |                        |           |
|  +------------------------+  +------------------------+           |
|                                                                   |
|  [展开详情 ▼] Risk Gates | Entry Conditions | Invalidation        |
+------------------------------------------------------------------+
```

---

## 七、API 设计

### 7.1 新增端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/strategy/v15/bundle` | GET | 获取 v15 策略包 |
| `/strategy/v15/decision` | GET | 获取 v15 决策 |
| `/strategy/v15/signal` | GET | 获取当前信号 |

### 7.2 请求格式

```python
# GET /api/v1/strategy/v15/bundle?instrument_id=btc-usdt-perp&timeframe=1d&position_side=flat
```

### 7.3 响应格式

```json
{
  "strategy_state": "LONG_STRATEGY_ACTIVE",
  "pattern_type": "breakout_long",
  "long_score": 72.5,
  "short_score": 35.2,
  "neutral_score": 15.0,
  "dominant_direction": "long",
  "direction_confidence": 0.52,
  "confidence_score": 78.0,
  "components": {
    "mtf_trend_bullish": 72,
    "bullish_structure": 68,
    ...
  },
  "penalties": {...},
  "long_signals": [...],
  "short_signals": [...],
  "gates": [...],
  "explain": [...]
}
```

---

## 八、验证步骤

1. **后端验证**
   - 运行 `python -m pytest tests/test_strategy_decision_rules.py`
   - 测试 v15 引擎输出
   - 验证 API 端点

2. **前端验证**
   - 访问 `/strategy` 页面
   - 验证状态显示正确
   - 验证持仓输入最小化

3. **集成验证**
   - 数据流从 snapshot → engine → API → frontend
   - 评分计算一致性

---

## 九、实施优先级

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| 1 | 创建 v15 配置文件 | P0 |
| 1 | 创建核心引擎 | P0 |
| 2 | 创建状态机和识别器 | P1 |
| 2 | 更新 Schema 和 API | P1 |
| 3 | 数据库迁移 | P2 |
| 3 | 前端 UI 重构 | P2 |
| 4 | 集成测试 | P3 |