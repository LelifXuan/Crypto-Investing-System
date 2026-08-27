# V2.1 更新说明 — 从 V1.6 到 V2.1 的焕新

> 本文件记录 V1.6 → V2.1 之间的核心变化（301 个 commit：88 frontend / 36 docs / 29 test / 20 backend / 18 macro / 6 fix / 6 config / 3 infra）。
> 系统全貌见 [`README.md`](./README.md)。

---

## 一、整体判断

V1.6 是一个"衍生品数据接入 + 发布加固"的版本；V2.1 已是**三大资产域完整的研究决策工作台**。
变化主线：**后端从"数据管道"进化到"决策引擎"，前端从"信息展示"进化到"编辑刊物式研究终端"**。

---

## 二、后端 — 从数据管道到决策引擎

### 1. 统一策略引擎（V1.7.0 核心）

- **`strategy_unified`**：多时间框架方向裁决、证据链、宏观/链上/衍生品 regime、风控闸门、机会扫描器。
- **MarketContextBuilder** 注入真实字段（`market_data / derivatives_features / chip_features / onchain_features / freshness_breakdown`），修复历史空字段漏洞。
- **错误兜底**：`/strategy/unified` 永不抛错——失败时返回 HTTP 200 + degraded payload（4 endpoint 并行 + `Promise.allSettled`）。
- **`freshness="due"` 状态** + 2 小时硬陈旧回退（`btc_derivatives_hard_stale_max_seconds=7200`）。

### 2. 宏观体系升级（V1.7.3/1.7.5）

- **MacroScoringEngine** 独立抽取 + 7 层评分（新增 `fed_operations` 第 7 层）。
- **Bayesian 触发价值**：`risk_reward_score_ev`（EV = P(win) × RR，不再封顶 rr=90）+ `setup_probability`（贝叶斯后验）+ `vol_compression`（多周期分位压缩检测）。
- **指标净化**：7 个可用指标（删 3 个 FRED 不兼容 PLACEHOLDER）；修正 `fed_soma_treasury` 符号 WSHOMCB → WSHOTSL（FRED API 实测）。
- 5 个 stub provider 标记 `implemented=False`，`NotImplementedError` 单独分类。

### 3. 黄金衍生品重构（V2.0 关键）

- **替换 Gate.io** → 6 端点多源聚合（Bybit + OKX + Binance × PAXG/XAUT）+ USD 加权资金费 + `asyncio.gather` 并发。
- **CFTC COT 磁盘持久化**：周报 baseline 进 `data/cftc/`（git 跟踪，7 天 TTL），冷启动不再阻塞下载。
- **三层缓存**：内存 120s → 磁盘 6h last-known-good → 实时回退（失败保留旧值，标注"实时抓取不可用"）。
- 黄金工作台 V5 页面：决策 + 技术 + 衍生品 + 治理四块合一，分析页视觉对齐。

### 4. A股 ETF 完整闭环（V1.8 起）

- 行情：东方财富多 CDN 兜底 + Sina K 线 fallback。
- 模拟：定投 + 季度再平衡（延迟 N 交易日后移）、HALO Rolling-252-Cov 策略回放、DCA 手数修正（100→1 手）。
- 净值曲线 + 双轴收益率视图（左 % 右 元）+ 现金回报曲线 + 一次性买入基准对比。

### 5. 数据层与可靠性

- SQLite 单写边界 + writer queue；`OperationalError` 立即 rollback。
- 每日首页预热（`daily_first_page_prewarm` middleware）+ `POST /strategy/prewarm`。
- 事件溯源 + 幂等键（`eventing` 模型）。

---

## 三、前端 — 编辑刊物式研究终端

### 1. 设计系统全面落地

- **统一 dropdown 组件**（`ui/dropdown.js`）：替换全站 20+ 原生 `<select>`（analysis 2 / structure 5 / knowledge 4 / btc 8 / ashare 1 / market-events 1），`tests/test_no_native_select_remaining.py` 静态守卫。
- **统一 chip / button 组件**（`dom.js mountChip/mountButton`）+ 17 个 chart 专属 token（`getComputedStyle` 联动）。
- **sticky thead + tooltip Escape**（可访问性）。
- **动效体系**：motion token（`--ease-drawer` iOS 曲线 + 120/180/220/240ms 阶梯）、按压反馈、页面进入/退出过渡、reduced-motion 降级。
- **警戒色/状态卡专业化**：删除 emoji 与文本箭头，改为内嵌 SVG + 圆角幽灵按钮。

### 2. 页面重构

| 页面 | 变化 |
|---|---|
| AI 策略 | `strategy.js` 拆 11 子模块；4 endpoint 并行 + 兜底；证据追踪自然语言卡；市场操作卡重设计 |
| 黄金配置 | V4→V5 两次重设计（Monet 玻璃卡 → 分析页视觉对齐）；hero + workbench + 治理 |
| A股 ETF | 执行模式条 7 等宽单元格、equity-curve 模块、双轴收益率、顶部精简 |
| BTC 衍生品 | 期权墙视觉权重分层、标准到期日锚点叠加、证据网格 4×2、表格字号/对齐优化、`step=any` 修复 |
| 形态结构 | 系统 chip 方向着色、通道多边形历史扩展、区域多边形/摆动路径延伸至最新 K 线 |
| 市场事件 | 日历重设计 + 分类颜色 + 翻译状态 + 加载体验 |
| 知识百科 | chip 压缩（`i N 页可用` popover）、editorial 重设计、词条去重净化 |

### 3. SPA 与实例检查

- SPA 路由队列（防重复点击丢导航）、骨架加载、进入/退出动画、滚动复位。
- `verify_pages.py` 重构：9 页冷启动 + SPA 切换 + 截图（2560×1440）+ console/page error 收集。

---

## 四、验证体系 — 从"跑测试"到"门禁矩阵"

V1.6 时代主要是 `pytest` + 基础 verify_pages。V2.1 建立了一整套**可执行设计门禁**：

| 门禁 | 新增能力 |
|---|---|
| `verify_pages.py` | 全 9 页实例检查（冷启动 + SPA + 错误收集 + 截图） |
| `a11y_scan.py` | WCAG 对比度/ARIA/标题层级扫描 |
| `a11y_visual_diff.py` | 与 baseline 的 SSIM + 像素级视觉回归 |
| `responsive_check.py` | 5 档断点渲染/溢出检查 |
| `perf_gate.py` | 长任务/LCP/CLS/包体积/DOM 复杂度 |
| `motion_verify.py` | 动效 token 阶梯 + reduced-motion 合规 |
| `css_audit.py` | 死代码/Token 覆盖/硬编码色（**增量门禁**：基线 + `--rebase`） |
| `stress_test.py` | 快速切换压力测试 |

AGENTS.md 增加硬性门禁：架构/工作流改动必须全量 verify_pages，修复任何页面后重跑全量。

---

## 五、知识百科内容治理

- **词条净化**：移除 3 个"页面使用指南"词条 + 7 个系统内部词条（数据源/健康/缓存类），知识百科回归"研究术语"职责。
- **内容修正**（2026-08 审计）：修复 Put/Call Wall 对冲方向错误、IORB 利率走廊上下限颠倒、SRF 时代错配；A股 ETF 词条补专属场景文案（消除"BTC 语境污染"兜底）。
- 审计结论沉淀到 `source/docs/UI_UX_AUDIT_2026-07-31.md` §21。

---

## 六、工程与仓库

- **设计系统 skill**：`.agents/skills/design-system/`（token 表 + 组件规范 + 动画配方 + 验证门禁）固化设计决策。
- **文件架构清理**：reports 336M→1.7M、screenshots 116M→4.7M；删除死模块（macro_derived.js）、临时脚本、一次性审计工具；`.zcode/` 私有文件 gitignore。
- **版本号**：`app/__init__.py __version__`（单一来源，测试钉住一致性）。

---

## 七、V1.6 → V2.1 核心能力对比

| 维度 | V1.6 | V2.1 |
|---|---|---|
| 资产域 | Crypto（BTC 为主） | Crypto + 黄金 + A股 ETF |
| 策略引擎 | 单一信号 | 统一策略（多周期 + regime + 闸门 + Bayesian EV） |
| 黄金 | Gate.io 单源 | 6 端点多源 + CFTC + 三层缓存 |
| 宏观 | 基础指标池 | 7 层评分 + 贝叶斯 + fed_operations |
| ETF | — | 行情/模拟/净值完整闭环 |
| 前端 | 信息展示 | 编辑刊物式终端 + 统一组件 + 动效 |
| 验证 | pytest + 基础检查 | 8 门禁矩阵 + 实例检查 |
| 知识库 | 含使用指南/系统内部词条 | 纯研究术语 + 内容审计 |
