# CHANGELOG

## v1.7.1 (2026-07-07)

### 黄金配置页 V2 升级

- **多空标签**：核心/派生指标卡右上角标签从"可用/偏低"改为 5 档多空判断（强势看多 / 看多 / 中性 / 看空 / 强势看空）。新增 `_bias_for_indicator()` 后端函数 + 5 档 CSS 类。
- **宏观指标**：新增 4 个核心宏观卡（real_yield_10y / DXY / CPI YoY / VIX）。每个卡显示多空标签 + bias_reason + 数据源。后端新增 `_gold_macro_snapshot()` 函数实现黄金视角的多空判断（含 CPI 二维表 / VIX 流动性冲击例外 / DXY 危机例外）。
- **设计语言**：页面从 4 段并列升级到 9 段递进（Hero 决策 → 4 宏观 → 7 模块 → 图表 → XAUT/黄金坑 → 执行 → 核心/派生指标 → 数据治理）。新增 `.gold-bottom-group` 二级容器（沿用 BTC bottom-group 模式）与 `.gold-decision-card[data-tone]` 4 色状态。

### 后端

- `app/services/gold_dca_dip.py`: `_indicator_card()` 新增 `bias` 字段；新增 `_bias_for_indicator()` 函数
- `app/services/gold_macro_adapter.py`: 新增 `_gold_macro_snapshot()` 函数
- `app/services/gold_allocation_engine.py`: `AllocationPlan` 新增 `macro_payload` 字段；`to_dict()` 暴露 `gold_macro_snapshot`
- `app/schemas/gold_allocation.py`: `GoldAllocationPlanResponse` 新增 `gold_macro_snapshot` 字段

### 前端

- `app/static/pages/gold_allocation.js`: 9 段递进重写（hero / decision / macro / modules / charts / xaut / execution / indicators / governance）；新增 `biasLabel` / `renderMacroStrip` / `renderMacroCard` / `renderDecisionGrid` / `renderModuleSection` / `renderChartSection` / `renderGovernanceSection` / `renderModuleCard` 函数；`loadExecutionPlan` 拉取 `/gold/allocation`
- `app/static/styles.css`: 新增 ~122 行 CSS（7 个多空 chip + 二级容器 + 4 宏观卡 + 流动性冲击警告）

### 测试

- `tests/test_gold_dca_dip_engine.py`: 新增 6 个 `_bias_for_indicator` 测试
- `tests/test_gold_macro_adapter.py`: 新建文件，6 个 `_gold_macro_snapshot` 测试
- `tests/test_gold_allocation_engine.py`: 新增 1 个 `gold_macro_snapshot` 集成测试
- `tests/test_gold_frontend_static.py`: 新增 7 个 V2 DOM 结构断言

### 已知问题 / Follow-up

- 强档阈值在 spec 文本"lower*0.7 / upper*1.3"对 negative lower 存在语义歧义。Implementer 做了语义化解读（lower≥0 时 *0.7，lower<0 时 *1.3，向 strong 方向延伸 30%）。建议未来 spec 修订时明确化。
- 图表区（5 段）目前是占位卡，真实图表实现可在 v1.7.2 实施。
- `_gold_macro_snapshot` 中 `bias_reason` 中文长字符串与流动性冲击阈值 (25/105/2.0) 硬编码在函数体内。可在未来 Task 提取为常量以减少漂移风险。