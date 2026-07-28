# AGENTS.md

你正在实现一个交易系统管理平台。请严格遵守以下约束。

## 一、总目标

构建一个**以管理链路为核心**的交易系统，而不是先做超低延迟撮合系统。  
最少包含以下 6 个模块：

- 仓位管理
- 盈利计算
- 交易复盘
- 技术指标
- 市场价格
- 市场事件信息

## 二、实现优先级

1. 数据模型与数据库
2. 市场数据接入
3. 仓位管理
4. 盈利计算
5. 复盘分析
6. 技术指标
7. 市场事件
8. 观测、权限、审计

## 三、硬性约束

- 禁止用 float 存储金额、数量、价格，统一使用 decimal / numeric
- 所有时间统一使用 UTC，存储为 timestamptz 或 epoch_ms
- 交易事实必须 append-only，不允许直接覆盖历史事实
- 所有 PnL 输出必须带上口径版本 metadata
- API 设计优先 REST + OpenAPI，内部流式/高频接口可补充 gRPC
- 先保证正确性、可回放、可审计，再做性能优化
- 代码必须可测试，至少提供单元测试和集成测试骨架

## 四、领域规则

### 1. Fill 幂等
同一个 `(source, account_id, fill_id)` 只能入账一次。

### 2. 仓位成本法
第一版必须支持：
- AVG_COST
- FIFO

### 3. PnL 输出
至少包含：
- realized_pnl
- unrealized_pnl
- fees
- funding
- slippage_cost
- equity

### 4. 多币种
所有费用保留原始币种，同时支持折算到报告币种。

### 5. 市场数据
第一版只需要支持：
- candle
- best bid/ask
- mark price
- order book diff（可选）

### 6. 技术指标
第一版只实现：
- SMA
- EMA
- RSI
- MACD
- Bollinger Bands

### 7. 复盘
第一版只实现：
- 胜率
- 盈亏比
- 最大回撤
- 收益曲线
- 费用归因
- 品种贡献

## 五、工程风格

- 目录按模块拆分，避免一层 giant service
- 所有 handler / service / repository / domain model 分层明确
- 所有对外结构定义放在 schema / DTO 层
- 所有重要公式和边界条件要写注释
- 所有数据库变更必须有 migration 思维
- 所有新接口都要更新 OpenAPI 文档

## 六、验证工作流（强制）

每次修复完成后，必须执行以下验证步骤，**绝对禁止未经验证即汇报完成**：

### 验证流程

1. **语法检查**
   - JS 文件：`node --check <file>`
   - Python 文件：`python -c "import py_compile; py_compile.compile(...)"`

2. **数据连通性验证（涉及外部 API 时必须）**
   - 用 `curl` 或 `python -c "import httpx..."` 直接请求外部 API
   - 确认返回状态码和数据内容
   - 测试 direct + proxy 两种路径

3. **运行相关测试**
   - `python -m pytest tests/` 运行对应模块测试
   - 确认全部通过，不忽略任何失败

4. **日志验证（涉及后台 worker / 数据抓取时必须）**
   - 检查 `runtime_dev/source_runtime/runtime/logs/` 下最新日志
   - 确认有预期中的成功日志 / 错误日志
   - 没有日志输出 = 可能根本没跑到

5. **缓存/数据文件验证**
   - 检查缓存文件是否更新（时间戳、内容）
   - 确认数据字段不是全 null / 空

6. **实例检查（涉及架构 / 工作流 / 推理模块时必须）**
   - 见下方 §六.1「实例检查门禁」一节。
   - 适用条件见 §六.2「按改动类别分级的测试要求」。

### 验证清单模板

```
☐ 语法检查通过（JS + Python）
☐ 外部 API 连通性测试通过
☐ 相关 pytest 全部通过
☐ 日志中有预期输出
☐ 缓存/数据文件有有效内容
☐ 实例检查通过（仅架构/工作流/推理改动）
```

### 工作流集成

每次修改完成后，**必须**执行：

1. `node --check <每个改动的 JS 文件>`
2. `python -c "import py_compile; py_compile.compile('<file>', doraise=True)"`
3. `python -m pytest tests/ -q`（或相关测试模块）
4. **架构/工作流/推理改动**:额外跑 `python tests/verify_pages.py --pages <受影响>`
5. **全部通过后再汇报**，不得跳过验证步骤

### 六.1 实例检查门禁

**为什么需要**:JS 模块顶层 `import()` 解析、CDN 资源加载、动态 ESM 依赖、`window.Chart` 这类全局变量时序 —— 这些都是 `node --check` 和 `pytest` 都看不到的坑。V1.5.x 期间发生的两次重大回归都是这个原因:
- SPA 路由切页时 `analysis.js` 顶层撞到 `Chart is not defined`
- 知识百科 5 个跳转 bug(unmount 反向 render、hashchange 监听器泄漏、isMounted 错位、过滤后相关术语点击无效、80+ 词条同步 innerHTML 阻塞主线程)

**必须使用 Playwright 工具，禁止仅用 curl 检查 HTTP 状态码。** HTTP 200 不代表页面正确渲染——JS 模块加载失败、CSS 404、import() 异常、全局变量缺失等问题 `curl` 完全看不到。

**怎么做**:

```
# 起后端(必须),在另一终端
uvicorn app.main:app --port 8002

# 跑实例检查
python tests/verify_pages.py                        # 全 9 页(冷启动 + SPA 切换)
python tests/verify_pages.py --pages monitoring-overview,market-analysis  # 精准测
python tests/verify_pages.py --skip-spa             # 只测冷启动
python tests/verify_pages.py --baseline             # 把当前截图入库为基准
```

**或用 Playwright 直接检查单个页面**:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.goto('http://127.0.0.1:8002/gold-allocation-page', wait_until='networkidle')
    page.wait_for_timeout(3000)
    page.screenshot(path='reports/check.png', full_page=True)
    assert len(errors) == 0, f"Page errors: {errors}"
    browser.close()
```

**检查清单**:
1. HTTP 200（通过 Playwright 的 `response.status`）
2. `pageerror` 事件 = 0（JS 异常）
3. 页面渲染了预期内容（`page.content()` 包含关键 CSS 类名）
4. 截图存档确认视觉正确

脚本会做 4 件事:
1. **冷启动**:用独立 Chromium context 打开每个 page,等真内容出现 (`<real-content-selector>` 之一)
2. **SPA 切换**:同一会话内点完 9 个横栏 link,记录点击 → 真内容出现 的耗时
3. **错误收集**:`console.error` + `pageerror` + 任何 `>=400` HTTP 响应,任一非零都标 FAIL
4. **截图存档**:`tests/screenshots/<page>.png`,baseline 模式写到 `tests/screenshots/baseline/`

阈值:冷启动真内容出现 < 10s;SPA 切换真内容出现 < 3s(冷加载 100+KB JS 模块在 headless 容器内的合理上限;已缓存的 page module 实测 60-100ms)。

### 六.2 按改动类别分级的测试要求

| 改动类别 | 例子 | 静态检查 (ruff/pytest/node --check) | 实例检查 (verify_pages.py) |
|---|---|:---:|:---:|
| **小文本** | 中文标点、错别字、注释、doc string、CHANGELOG 措辞、README 文案 | ✓ | ✗ |
| **CSS 样式** | 颜色、间距、阴影、hover/focus 微调 | ✓ | ✗ |
| **后端业务逻辑** | 领域规则、计算公式、repository 改动 | ✓ | ✗ (单测覆盖) |
| **架构** | SPA 路由、模块加载、静态资源加载顺序、入口函数签名、controller 对象形态、模板结构 | ✓ | **✓ (必)** |
| **工作流** | 重试/轮询、防重入 token、状态机、事件流、SPA 切换、刷新按钮、abort controller | ✓ | **✓ (必)** |
| **推理模块** | `terminal_summary_engine`、`monitoring_dashboard`、`strategy_signal`、`alerts_bundle`、知识百科 catalog | ✓ | **✓ (必)** + 实地数据流过 |
| **跨页 fetch / 多 endpoint 并行** | `pages/strategy` 用 `Promise.allSettled` 拉 `/strategy/unified` + `/monitoring/dashboard` + `/btc-derivatives/dashboard` + `/monitoring/macro-overview` | ✓ | **✓ (必)** + 4/4 失败兜底 + 数据源状态小卡渲染 |

**作用域(scope)选择规则** —— 不跑全 9 页,只跑真正会受影响的:
- 改了 `main.js` / `core/*.js` / `templates/page.html` → 跑全 9 页(共享依赖)
- 改了某一个 `pages/<name>.js` → 只跑 `--pages <name>` + 它跳过去的目的地
- 改了 `terminal_summary_engine` / 推理 service → 跑 monitoring + alerts + strategy(消费方)
- 小文本 / CSS → 不需要跑

### 六.3 错误教训(典型反面教材)

| 教训 | 现象 | 根因 | 后续防范 |
|---|---|---|---|
| `analysis.js` 切换崩溃 | `ReferenceError: Chart is not defined` | 模板 `<script defer>` 加载 Chart.js,但 `import()` 不等待;另外 `node --check` 看不见 `window.Chart` | `loadScriptOnce()` 在 `boot()` 内 `await`,且 `verify_pages.py` 跑 analysis 必现 |
| 知识百科 5 bug | unmount 反向 render、hashchange 泄漏、isMounted 错位、过滤后点击无效、80+ 词条同步阻塞 | 知识百科是「架构」级页面但只跑了 `node --check` | 知识百科改动 = 架构,必须实例检查 |
| 横栏点击 lag 100-300ms | click handler 同步 walk boot() 阻塞主线程 | 没有骨架占位,`node --check` 完全无法发现 | 实测耗时,verify_pages.py 的 SPA 切换测试 |
| template `<script defer>` 阻塞 DCL | headless 验证时 market-analysis 30s 都拿不到 HTML | Chart.js 远程 CDN 慢时 `defer` 仍阻塞 DOMContentLoaded | 模板不引用外部 CDN,统一走 main.js 的 `loadScriptOnce` |
| 状态卡 emoji/警告色过载 | `📊` / `⚡` 跨平台渲染不一致,大面积琥珀色背景像错误提示 | 直接借用 emoji 和告警色,未和现有设计语言(冷白半透明、青绿色)对齐 | 视觉组件统一使用内嵌 SVG;颜色仅在 RANGE/TRANSITION 模式用低饱和色微调;静态断言禁止 emoji/文本箭头 |
| BTC 衍生品页并排小字溢出 | 右侧 `btc-hedge-result` 容器在无数据时输出竖排小字,游离在表单外 | 容器 `min-height: 220px` + flex-end 对齐,而内容短,形成竖排溢出 | 证据与保护规划改为上下两层;空态用虚线 dashed 卡片上下排版;证据子卡 `grid-auto-rows: 1fr` 等高 |
| 结构图右侧形态矩形不延伸 | BTC 1h 截图里棕色"震荡区间"矩形右边停在 07-26,左侧最新 K 线在 07-27,中间留出空隙 | `shouldExtendToLatest` 不含 `pattern_region` 角色,polygon 右角未被 `extendOverlayToLatestCandle` 拉至 latestX | `shouldExtendToLatest` 加入 `pattern_region` / `region` 角色;`extendOverlayToLatestCandle` 新增 polygon 右角延伸分支;`tests/test_structure_overlay_extension.py` 静态守卫 |
| 通道多边形左边缘截断 | HYPE 1h 截图里通道多边形左边从 07-23 19:00 开始,但实际从 07-21 12:00 就有 swing low / high 在通道边界上,中间留出空隙 | `detect_channels` 固定用 `highs[-4:] / lows[-4:]`,只覆盖最近 4 个 pivot,`left_idx` 永远是 4th-from-last | `detect_channels` 改为贪心扩展:在 4 pivot 拟合基础上向左逐一加入更老的 pivot 并重做线性回归,只要 `max(u_err, l_err) ≤ tol * 2.0` 就保留;`test_channel_polygon_left_edge_includes_older_pivots_in_tolerance` 静态断言 `left_idx ≤ 12` |
| 摆动骨架末端点滞后 | 蓝虚线最后 dot 在 07-26 22:00,新 K 线 07-27 08:00 之后没有 dot,trendline 外推只补一个空白点 | 之前只补 1 个外推点,缺少 live swing dot | `extendOverlayToLatestCandle` 在 swing 角色下额外 append 一锚定到最新 K 线 high/low 的 dot,选与上一个 dot 距离更近的一边 |
| 系统 chip 单一灰色 | 右侧 3 张系统卡"已确认"chip 全部灰色,看不出"已确认的方向" | 状态 chip 默认 `chip-neutral`,未读 system.direction | 派生 `chipToneForDirection()` 把方向映射为 bull/bear/neutral;只动 system 卡片分支,避免影响 alerts / swing dot 内部 tooltip 里的"已确认"文本 |
| 墙位迁移图与期限矩阵割裂 | 标准到期日期限矩阵（6 行）与关键行权价迁移图（180D 历史折线）割裂在不同视图,用户无法对照 | 图表只展示历史线,标准到期日的 PUT WALL / MAX PAIN / CALL WALL 没在图上呈现 | 新增 `expiryAnchors` Chart.js 插件,`buildMaturityExpiryAnchors()` 从 maturity_ladder 派生垂直虚线 + 3 个圆点;`key_levels_history` `span: 6 → 12` 独占整行 |
| 期限矩阵 wall cell 视觉权重平等 | `$60,000` 与 `未形成有效墙` 两类信息块占据一样字号 / 颜色,用户扫不到主结论 | 容器只有 `is-effective` / `is-insufficient` class,没有 CSS 区分 | 新增 `.btc-wall-cell` 基础 + `.is-effective`（16px / ink / 青绿 border-top） / `.is-insufficient`（13px / muted / dashed border / opacity 0.86）两个变体;`<b>` 字号差 ≥ 2px,静态守卫 |
| 现价表单 HTML5 校验误报 | 系统自动导入的 `65226.17` 触发"请输入有效值。两个最接近的有效值分别为 65226 和 65227"原生警告 | `<input type="number">` 默认 `step=1`,但 spot_price 是浮点,浏览器把任何小数都视为"非整数步" | 在 spot_price 输入加 `step="any"`;`tests/test_btc_hedge_form_input_step.py` 静态守卫 |
| **架构重组后 6 页报错未发现** | 用户报告 market-events、ashare-etf 等页面报错,但之前声称"全部正常" | **1)** 只用 curl 检查 HTTP 200,未用 Playwright 渲染; **2)** 用户报告 A 页只修 A 页,不检查 B/C/D 页; **3)** 修复后不跑全量 verify_pages | **绝对禁止 curl-only 验证。架构/路由改动后必须 `verify_pages.py` 全量(冷启动+SPA)。修复任何一页后必须重跑全量。** |

### 六.4 修复后验证规则（强制）

**修复一个页面的 bug 后,必须重跑全量 `verify_pages.py`,不是只跑那一页。** 原因:SPA 路由、共享依赖 (`main.js`/`core/*.js`)、静态资源路径的改动会影响所有页面。

```
# ❌ 错误:只验证刚修的那一页
python tests/verify_pages.py --pages ashare-etf --skip-spa

# ✅ 正确:全量验证
python tests/verify_pages.py
```

**任何涉及以下改动的任务,完成后必须全量 verify_pages:**
- `main.js` / `core/*.js` / `templates/page.html`
- `app/api/router.py` (路由注册)
- `app/core/paths.py` (静态资源路径)
- 文件重命名/目录结构调整
- 删除任何 `pages/*.js` 或 `endpoints/*.py`

**如果 verify_pages 有任何 FAIL,任务未完成。** 不允许以"可能是缓存"为理由跳过。

验证通过标志：
```
☐ ruff: All checks passed
☐ pytest: X passed, 0 failed
☐ compileall: all compiled
☐ node --check: all passed
```

### 错误处理原则

- 修复代码只是手段，**数据正确到达前端**才是目标
- 如果外部 API 不可达，记录原因并告知用户，而非静默吞掉错误
- 永远保留缓存降级路径，确保网络故障时不返回空白页

## 七、提交策略

- 每个功能域独立 commit，禁止混入运行时文件（.db, .log, cache）
- 禁止直接提交 API Key 和 secret
- Commit message 格式：`[domain] 简述`
  - `[macro]` — 宏观数据、指标、评分
  - `[frontend]` — 前端页面、JS、CSS
  - `[network]` — 代理、数据源、API 接入
  - `[config]` — 配置文件（catalog, yaml, json）
  - `[test]` — 测试用例
  - `[docs]` — 文档
  - `[infra]` — 构建脚本、CI、工作流

## 八、输出要求

每次完成任务时：
1. 说明修改了哪些文件
2. 说明为什么这样设计
3. 说明已知风险和下一步建议
4. 不要一次性重构全项目，保持变更小而清晰
