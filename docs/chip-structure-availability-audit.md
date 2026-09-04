# 筹码结构：数据可用性与市场风险语义审计

审计日期：2026-08-31。仅代码追踪与无 I/O 最小调用，不改市场计算、DTO、数据库或 provider。
这是后续业务修复输入，不是该模块已验收声明。

## 结论与优先级

**高优先级业务债务，不能通过补类型或删 skip 解决。** 当前兼容服务的无数据分支将
`state=missing` 同时标记为 `risk_score=100 / risk_label=extreme`。该分值不仅存在于展示：
旧 FinalDecision 路径把它变成 `risk_score_extreme` 冲突，且权限选择先处理冲突，导致
`action=no_trade` 与 `trade_permission=observe` 并存。尚未证明这会触发真实下单；本审计
不把 legacy permission 等同于 canonical execution permission。

无数据库、无网络的最小调用：以空 candles 调用 `ChipStructureService._missing_payload`，
再调用 `FinalDecisionService._conflicts`、`_final_action`、`_trade_permission`。实际结果：
`missing → 100/extreme → [risk_score_extreme] → no_trade / observe`，资金上限仍为 0。
此输出仅作为问题证据，未加入“应当如此”的回归断言。

## 已确认的消费链

| 消费位置 | 实际传播 / 保护 | 影响与限制 |
| --- | --- | --- |
| `app/services/chip_structure.py` | 优先读 StructureSnapshot；无快照读缓存 K 线；少于 20 根进入 missing | 缺失数据被编码为极端市场风险；不是外部真实风险事实 |
| `app/services/market_context.py` | `chip_structure` 与 `chip_features` 原样携带风险字段 | analyze 正常返回即把依赖写为 fresh、时间用 now；没有检查 chip.state=missing，存在假新鲜度 |
| `app/services/final_decision.py` | build 透传 risk；`_conflicts` 对 >=80 增加冲突；`_trade_permission` 优先处理冲突 | 明确影响 legacy 决策解释与权限字符串；缺失应受可用性门禁，而非极端风险推断 |
| `app/services/alerts_bundle.py` | refresh 调用 FinalDecision 并发布；read 返回缓存中的 final_decision | 可通过已发布快照传播；新 refresh 的 chip_structure 本身为 None，不能误称新快照仍填满旧 chip 卡片 |
| `app/api/v1/endpoints/monitoring.py` | alerts `/final-decision` 优先返回已有快照，缺失时 build | API 可达；后续修复必须处理 LKG 与旧已发布字段的兼容，不覆盖历史事实 |
| `app/services/analysis_bundle.py` | 构建时调用 FinalDecision 并包含结果 | 后端快照可携带 legacy 字段；当前 Analysis JS 未发现直接读取 risk_score/risk_label 的引用 |
| `app/services/monitoring_dashboard.py` 与 `terminal_summary_engine.py` | 旧 alerts.chip_structure 可作为最后 proxy；强制低置信度 / is_proxy，结构模块不据此贡献方向 | 已有保护必须保留；不能笼统宣称总览将100直接显示为全局市场风险 |
| `app/services/strategy_unified/` | 结构输入来自 components.structure_overall；MTF 使用 strategy scores，并记录 chip 来源；依赖元数据可传播 | 未发现直接消费 chip.risk_score 的 canonical 下单分支；freshness 污染仍需专项门禁验证 |
| `app/static/pages/alerts.js` | 旧渲染器将 extreme 显示为“风险极高” | 当前 `/alerts-page` 是 Strategy 兼容路由，旧 alerts.js 非正式导航页；这是潜在 legacy 消费，不是已复现的六页 UI 故障 |

## 旧测试合同分类

| 分类 | 合同 | 处理 |
| --- | --- | --- |
| 仍需保留 | analyze 的 instrument/timeframe 身份、UTC、缓存读取、不因微观证据不足放开 futures、数据缺失不得形成真实市场结论 | 后续使用当前 facade 的真实输入写测试，不恢复旧私有实现 |
| 当前实现已无 | TimeframeSnapshot、_build_timeframe_snapshot、_latest_observations、四周期 snapshot map 注入 | 不能仅补 import；旧夹具与现实现不兼容 |
| 当前未提供能力 | accumulation/distribution confirmed、false break 及基于 CVD/OI/depth 的旧联合判断 | 作为产品/算法历史能力记录，不为解除 skip 重建计算 |
| 当前缺口 | missing 与 market risk 分离；真实来源时间；权限优先级；失败时保留 LKG；旧快照的兼容解释 | 独立业务修复，应先确定可用性合同再写回归 |

`tests/test_chip_structure.py` 的模块级 skip 本轮保留；数量“1 skip”不代表只有一条断言缺失，
整个旧测试模块均未执行。不得把兼容服务的现状当作算法等价证明。

## 下一轮修复输入（尚未实施）

1. 明确 system_availability、market_risk 与 execution permission 的独立语义；无输入时不给市场风险分值。
2. 修复 MarketContext 的 freshness 取值和 FinalDecision 权限优先级；不得因修复放宽资金/合约许可。
3. 遍历已发布快照、alerts API、Analysis、Monitoring、Unified 的转换点，先读 LKG，再按真实状态更新。
4. 用最小 fixture 覆盖 missing、stale+LKG、真实风险升高、异常、恢复和冲突；比较 canonical 与 legacy 输出。
5. 审查仍在使用的旧合同后再决定替换哪些测试；不删除失败断言来获得绿色报告。

这项修复可能涉及业务语义与兼容政策，必须另立实施计划；本轮未授权改变任何计算。
