# UI 2.0 页面迁移验收记录

> 历史记录：以下版本号、测试结果和产物均对应 2026-08-31 内部验收包；当前源码版本见根目录 `README.md` 与 `CHANGELOG.md`。

应用版本 1.8.1；UI 发布 V2.3；设计基线 3.4。未通过阶段不得标记冻结。

## H0 — PASS / FROZEN（2026-08-31）

- JS `node --check`、改动 Python `py_compile` 通过。
- H0、Registry、包路径、设计手册、Palette、Operator 浏览器合同：32 passed。
- 全量 `python tests/verify_pages.py`：11/11 冷启动、10/10 SPA；无页面异常、console error、失败响应。
- 新增文件与构建脚本 Ruff：0；全量项目 Ruff 留待最终门禁独立报告。
- 真实 HTTP 验证 HTML no-cache、资产 revalidation、ETag/Last-Modified 304；无路由拦截的浏览器缓存 A→B 升级通过。
- 内置 Python 3.11 启动独立 8002 服务；开发测试使用系统 Python 3.14（便携运行环境不包含 pytest）。
- 证据目录：`%TEMP%/cis-ui23-d2c7fa06920547eab956f5c4bf2f53df/h0/`。
- 旧版本首次升级须 Ctrl+Shift+R 一次；之后自动协商更新。未改 provider，direct/proxy 不适用。

## H1 Analysis — PASS / FROZEN（2026-08-31）

- Analysis 全模块、H0、交付边界与 Registry：57 passed；JS 检查、Python 编译与改动测试 Ruff 通过。
- 最后同版全量实例：11/11 冷启动、10/10 SPA，无异常、console error 或失败响应。
- 20 次快速操作：真实精简实例 PASS（缺少目标快照时明确终止降级）；确定性真实字段 fixture PASS（图表与选择链验证）。
- 已验证键盘/preview/pin、最新 DTO、同值无动效、研究意图切换、URL 冷缓存/失败/LKG/卸载、实际图表点击和 resize、对象消失。
- 主视口与计划全部响应式视口已保存 fullPage；人工检查桌面 pin/linked selection 与移动 sheet。证据为同目录 `h1/workbench/`、`h1-freeze/verify/`。
- 冷缓存失败后残留骨架已修复；压力守卫区分明确终止的无数据页面与真正图表丢失，并有反例测试，未放宽 ready-data 检查。
- 旧 mark 缺失时回退收盘价的展示已取消；实际收盘价保留在独立字段。

## H2 Structure 身份合同 — PASS / FROZEN（2026-08-31）

- `test_structure_research_identity.py` Node ESM 合同通过；语法、编译、Ruff 通过。
- 身份来自形态原始类型与带时区起始时间；候选重排、滚动窗口、投影延长、状态/角色晋级不改变身份。
- 重复锚点冲突拒绝独立选择；缺失/非法时间拒绝；同一瞬间的不同时区表示归一 UTC。真实 SQLite 快照的无后缀 ISO 日期时间按现有 candle UTC 合同补 Z，不按浏览器本地时区解释；纯日期拒绝。
- 不使用 backend candidate ID、geometry ID、数组位置或价格，不修改后端 DTO。

## H3 Structure — PASS / FROZEN（2026-08-31）

- 身份、页面行为、请求与交付边界 26 passed；既有 Structure 合同 124 passed、1 legacy skip。
- 共享 Inspector 回归与 Structure 浏览器行为合计 31 passed；修复桌面原点已聚焦时错误跳到刷新按钮的边界。
- 最后全量实例 11/11 冷启动、10/10 SPA；fixture 20 次快速筛选 PASS。语法、编译与改动测试 Ruff 通过。
- 覆盖系统/形态/Profile、SVG 键盘入口与透明命中区、preview 不重建 SVG、pin、刷新 DTO、冲突、筛选清除、URL、LKG 和冷恢复中切页。
- 主视口与全部响应式视口 fullPage 截图在 `h3/workbench/`；真实 ETH 结构实例也验证 POC 可选且无 console error。SQLite 无后缀 UTC 锚点已补真实形态回归。
- 删除旧双栏覆盖、渐变 toolbar、失效原生 select 和重复 card padding 规则；共享 surface 无新增调色板。

## H4 Strategy ADR 与命令 — PASS / FROZEN（2026-08-31）

- ADR 0023 采用完整 Detail Panel，记录模态/移动端/浮层与深链接限制；不引入 Inspector。
- 四个页面命令与 Palette 浮层回归 9 passed；主视口、1100、390 的 focus/refresh/detail/20 次开关/scope 注销通过。
- 全量实例 11/11 冷启动、10/10 SPA，无浏览器异常或失败响应；JS、Python 编译和新增测试 Ruff 通过。

## 最终同版软件验收 — PASS（2026-08-31）

| 交付域 | 状态 |
| --- | --- |
| P1：Monitoring、BTC、Events、Macro | ACCEPTED / FROZEN，最终同版回归通过 |
| P2 Operator Core | Command Palette、pin、resize、URL 恢复与浮层协调通过 |
| H0 发布加固 | PASS / FROZEN |
| H1 Analysis | PASS / FROZEN |
| H2 身份合同、H3 Structure | PASS / FROZEN |
| H4 Strategy | ADR 0023 与四命令通过；保留原 Detail Panel |
| ETF、Gold、Knowledge | 未迁移；Knowledge 保持 reference layout |

### 本轮实际修复与测试收口

| 文件 | Before | After |
| --- | --- | --- |
| `source/app/static/pages/structureWorkbench.js` | click 整数坐标与 PointerEvent 小数坐标直接比较，静止鼠标被误判为移动 | 统一 CSS 像素坐标；真实移动仍可 preview，committed ID 不改变 |
| `source/app/static/editorial.css` | 旧 `article.card:hover` 让整个 SVG 上浮，细线命中区随之移动 | 在既有 Structure surface 规则取消 transform；未新增样式层或调色板 |
| `source/tests/test_structure_workbench.py` | 点击透明命中区边缘；未覆盖不同事件坐标精度 | 点击中心；增加 DPR 1/2 小数坐标回归，resize 两端仍保持 POC，拖拽中切页清理 |
| `source/tests/stress_test.py`、`test_analysis_workbench.py` | 仅等待外壳 transition，LKG 后台刷新可能尚未结束；诊断文字错误称固定 5 秒 | 同时等待真实 aria-busy；超时忙碌仍 FAIL，增加延迟完成与永久忙碌反例 |
| `source/tests/test_strategy_operator_commands.py`、`stress_test.py` | 部分压力测试依赖实时数据，禁用刷新按钮造成等待超时 | 复用真实字段 fixture 覆盖六页和 Strategy，仍保留独立真实实例/LKG 门禁 |
| `source/app/api/v1/endpoints/market_prices.py`、`test_ephemeral_mark_response.py` | 未落库报价缺少整数 mark_id，响应序列化可返回 500 | 沿用既有临时报价 ID 0；持久化 ID 不变，无新数据库事实或 provider 请求 |

结构点击问题通过事件轨迹确认：Chromium click 的整数坐标与 pointerover 的小数坐标来自同一静止位置。修复后 17 项 Structure 行为测试及连续 12 次真实点击复现通过。测试未通过重试忽略断言、强制点击或放宽图表保留条件掩盖问题。

### 同版命令与结果

- 改动及未跟踪 JS：26 个 `node --check` 全部通过。
- 改动及未跟踪 Python：44 个 `py_compile` 全部通过；改动范围 Ruff **0**。
- `python -m pytest tests/ -q -rs`：**1986 passed、6 skipped、5 warnings**，688.66 秒；浏览器没有因后端未启动而 skip。
- `python tests/verify_pages.py`：**11/11 冷启动、10/10 SPA**，0 slow；正常操作 pageerror、console error、HTTP ≥400 为 0。
- `python tests/stress_test.py --fixtures --rapid-clicks 20`：**8 PASS、0 WARN、0 FAIL**（六页、Strategy、pending scan 切页）。Palette 连续 20 次开关、四页快速命令刷新/选择/卸载、Analysis 意图恢复、Structure 拖拽切页均在全量行为测试内通过。
- `python tests/responsive_check.py --pages monitoring-overview,btc-derivatives,market-events,macro-calendar,market-analysis,market-structure --viewports desktop-2k,laptop-1280,tablet,mobile-s`：**24/24 PASS，0 overflow**。
- 确定性浏览器矩阵另覆盖 2560×1440、1500×900、1440×900、1280×720、1180×800、1100×800、900×900、800×900、768×1024、768×900、390×844，以及 2560×1600 高屏复核。
- fullPage 证据覆盖关闭/打开、pin/preview、resize 两端、drawer、bottom sheet、Palette、linked highlight、URL 与已就绪图表。截图独立输出，未更新基准。
- Browser 实际 ETH 1h 页面复核 POC、键盘选择、最宽 Inspector、来源状态与 console；项目 Playwright 验证完整数据、冷缓存/LKG、Escape/焦点恢复、焦点约束/滚动锁、reduced-motion、图表 resize 与卸载。

证据根目录：`%TEMP%/cis-ui23-d2c7fa06920547eab956f5c4bf2f53df/`。最终日志为 `delivery-pytest.log`、`delivery-verify.log`、`delivery-responsive.log`、`release-stress-final.log`、`delivery-ruff.json`；图片在 `final/workbench/`、`final/verify/`、`final/responsive/`。

### 已知遗留与环境限制

- 全量 Ruff：**235 项项目遗留 + 4893 项内置依赖源码问题**。项目分类：E501 119、I001 46、F401 31、F841 9、E701 7、E402 6、F821 6、F541 4、B007 3、B905 2、B011 1、E741 1。与本轮改动范围 0 分开记录。
- 6 skip：`test_chip_structure.py` 缺少 `TimeframeSnapshot` 导出（1）；旧 knowledge guide-card 测试尚未迁为 FAB（2）；pandas-ta 缺失（1）；TA-Lib 缺失（2）。
- 5 warnings：Pydantic 测试访问实例 `model_fields` 的弃用警告（3）；JWT 测试短密钥警告（2），不是生产密钥披露或变更。
- 内置 Python 3.11.15 的 `pip check` 通过；测试工具使用系统 Python 3.14，可选指标依赖未补装。
- PID 50112 的本轮实例日志无数据库锁、ResponseValidationError 或 ASGI 异常；3 次 Windows Proactor 连接关闭回调的 WinError 10054 与快速取消/断开场景一致，未伴随浏览器失败响应。精简库不含完整 ETF 历史，记录到 Eastmoney RemoteProtocolError/ETF history empty 降级，未伪装为行情完整。
- 验证使用约 23.4 MiB 精简库与有效已发布快照；未复制完整历史数据库。worker 与自动预热关闭。provider 请求未改，external direct/proxy 门禁不适用，不代表外部服务可用性认证。

### 便携交付与敏感清理

目标包：`dist/CIS-UI2-V2.3-Page-Migration-PRIVATE-20260831.zip`，包含内置 Python、依赖、启动脚本、代码及原样 `.env`；**未加密、含密钥、仅限内部授权使用**。包内 manifest 提供逐文件 SHA-256，保留 `app/cache` 业务源码，排除数据库、日志、运行缓存、临时截图与 `nul`。

独立解压验证结果记录在同名 `.verification.json`，绑定最终 ZIP SHA-256；包内不自写该结果，避免循环哈希。该外部记录区分包内容/依赖隔离、启动脚本、空库八页浏览器验证、端口回收及人工清理状态。

历史清理再次被执行策略拒绝，未改用其他工具绕过，以下对象仍需人工删除：

- `%TEMP%/cis-ui2-portable-20260831-0018`（含密钥的历史解压副本）。
- `%TEMP%/cis-ui2-final-1dcf372e6eed408c84f7ad4e6d4c733f/runtime/data/verification.db` 及存在时的 `-wal`、`-shm`。

本轮解压副本与验证库的最终清理结果见外部 `.verification.json`。旧交付包、用户截图基准、未提交改动及 `nul` 保留；未自动提交或推送。

本记录不是完整 P2 Complete 声明。

## 后续发布卫生补验（2026-08-31）

六页和 Operator Core 边界不变。补修 FAB hidden 语义与测试基础设施后，同版完整 pytest 为
2013 passed、4 skipped、0 warnings；全量页面 11/11 + 10/10，压力 8/8 通过。
该结果是原冻结版本的后续补验，不改写以上历史命令结果。
细节、业务债务与归档位置见 [发布卫生记录](ui23-release-hygiene.md)，
新便携包及独立验证使用 `CIS-UI2-V2.3-Hygiene-PRIVATE-20260831` 标识；旧包保留。
