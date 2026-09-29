# V2.3 发布卫生与测试债务收口

> 历史记录：以下版本号、测试结果和 ZIP 校验值均属于 2026-08-31 内部验收包；当前源码版本见根目录 `README.md` 与 `CHANGELOG.md`。

应用 1.8.1 / UI V2.3 / 设计基线 3.4。开始日期 2026-08-31。
本轮不扩大六页 Workbench 范围，不改业务计算、数据库、DTO 或 provider。

## 修改与原因

| Before | After |
| --- | --- |
| 六个静态测试只在脚本入口使用 pytest，却未导入，正常收集掩盖错误 | 补导入，增加六文件 × 成功/失败退出码共 12 项真实 `__main__` 调用回归；不递归运行测试 |
| Knowledge 的两项旧卡片测试整组 skip | 改为 Monitoring/BTC/Strategy × 桌面/1100/390 的 9 项 FAB 行为链，保留真实内容与焦点断言 |
| 指南 `[hidden]` 被旧 CSS 强制 display:block，仅 opacity:0 | 既有 styles.css 规则改为 display:none；隐藏内容离开布局及可访问树，不新增组件或动画层 |
| 缺少后端时部分浏览器用例静默 skip | `pytest --acceptance` 在收集前检查后端；运行中因后端缺失 skip 则改为 FAIL；可选库 skip 不受影响 |
| 测试读取 settings 实例 model_fields，JWT 测试继承短密钥 | 改为类型访问；JWT 采用足够长度的专用测试密钥，monkeypatch 自动恢复，不改 .env |
| 手册测试只搜索前 1500 字，发布记录增长后找不到约束优先级 | 按 §0 标题边界定位，保留旧路径禁止条件，不通过扩大字符窗口掩盖结构问题 |
| 旧验收证据仅在系统临时目录 | 精选截图、零错误页面摘要、交付验证 JSON 按显式 allowlist 归档并生成 SHA-256；不复制原始日志、HAR、密钥或响应正文 |

前端测试技能用于真实浏览器交互验证；界面细节技能用于检查隐藏/退场状态。本轮优先保证
`hidden` 语义，不为退场动画保留已关闭面板的可访问内容。

## 验收环境与记录位置

- 本轮证据：仓库 `reports/ui23-hygiene-20260831/`，不依赖 `%TEMP%`，不纳入提交/便携包。
- 历史精选证据：该目录 `previous-release/`；allowlist 哈希在 `archived-evidence-hashes.json`。
- 自建后端：127.0.0.1:8002，内置 Python 3.11.15；测试使用系统 Python 3.14。
- 测试父子进程统一 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。只设后者会让旧审计
  测试的 subprocess 文本管道按 GBK 解码 UTF-8，引发 reader thread 异常；最终门禁统一环境，
  未通过吞掉解码错误或过滤 warning 掩盖失败。旧 subprocess 编码隐式依赖另列测试可移植性债务。
- WORKER_PROFILE=none；LOCAL_BOOTSTRAP_WARMUP_ENABLED=false；约 23.39 MiB 精简库，
  仅品种目录和 157 个已有页面快照，不复制完整历史库。
- 旧 ETF 真实缓存回归检查相对 runtime 路径，却通过 app_paths 从隔离目录读取。本轮只向
  测试隔离目录复制六份所需历史 JSON，合计 1,251,044 字节，逐文件核对哈希。未改测试
  断言、未联网、未复制历史数据库；路径分叉登记为后续测试可移植性债务。

## 同版软件门禁 — PASS（2026-08-31）

- 最终完整 pytest：**2013 passed、4 skipped、0 warnings**，819.92 秒。
- 全量页面：**11/11 冷启动、10/10 SPA**，0 slow；pageerror、console error、HTTP >=400 为 0。
- 压力：**8 PASS、0 WARN、0 FAIL**，含六页、Strategy 和 pending scan 切页；后者耗时 243.3ms。
- 新增/修复定向测试：33 passed；最终 FAB 矩阵另跑 9 passed，手册合同 8 passed。
- FAB 覆盖 2560×1440、1100×800、390×844；全量既有 Workbench 测试继续覆盖原响应式矩阵。
  导航遮罩关闭后的可读指南截图以 `*-ready-open.png` 留存；闭合面板的可访问 region 数为 0。
- 后端缺失 CLI 反例：显式返回 pytest exit 4，阻止收集；不以浏览器 skip 冒充验收。
- 84 个已验证 JS/Python/CSS 文件哈希一致；295 项原有截图与交付产物未改动。
- 内置 Python `pip check`：No broken requirements found。

4 个 skip：筹码结构旧模块 1；pandas-ta 缺失 1；TA-Lib 缺失 2。无缺少后端导致的浏览器 skip。
原 5 条 Pydantic / JWT 测试 warning 已消除，不使用 warning filter。

首轮失败日志保留为 `full-pytest-attempt1.log`：4 failed、2009 passed、4 skipped、2 warnings。
原因分别为 ETF 隔离输入、手册固定字符窗口、两处 UTF-8/GBK 管道解码。全部修复/对齐后
从静态检查开始重跑，未跳过失败用例。最终日志为 `full-pytest.log`、`verify.log`、`stress.log`。

验收命令：

```text
python -m pytest tests/ --acceptance -q -rs
python tests/verify_pages.py
python tests/stress_test.py --fixtures --rapid-clicks 20
```

VERIFY_SCREENSHOT_DIR 与 WORKBENCH_SCREENSHOT_DIR 均指向独立证据目录，截图 fullPage，
不覆盖既有基准。Backend preflight 是运行条件检查，不代替 Playwright 页面门禁。

## 剩余债务边界

- 筹码结构模块仍 skip；详见 [消费链专项审计](chip-structure-availability-audit.md)。
  缺失输入不应变成 extreme 风险；旧权限冲突与伪 freshness 已确认，但未修改业务。
- pandas-ta / TA-Lib 保持可选；不安装以追求零 skip，不改内置 Python。
- 全量 Ruff 分别记录项目与 runtime_python 第三方源码；不忽略全局错误、不改依赖源码。
- 本轮静态门禁：56 个改动/未跟踪 Python 编译、26 个 JS `node --check` 通过；本轮修复
  文件 Ruff 为 0。全量项目遗留由 235 降至 221，内置第三方源码仍为 4893。
  项目分类：E501 115、I001 46、F401 31、F841 7、E402 6、E701 5、F541 4、B007 3、
  B905 2、B011 1、E741 1；六个 F821 已清零。详细位置见 `full-ruff.json`，不是第三方代码修改清单。
- 旧 `test_user_facing_text_audit.py` 创建 fixture 后未将其传给扫描器，而是扫描当前源码；
  其正反用例不能独立证明 fixture 的检测能力。此问题不在本轮指定修复文件内，列入下一批
  测试重构，不能把该用例通过解释为全部用户文案合规。测试父子进程 UTF-8 对齐仅解决编码。
- 精简实例长时间停留可能出现后台预计算等待超时：worker 明确关闭且 LKG 保留。
  正常验收仍要求无 console error/HTTP失败；这不代表实时供给已经验证。

## 敏感产物与人工清理

原 V2.3 包 SHA-256 已核对：
`0eb83daf214568a7ea00328028ea4ef7990692843cc77311e69dc70c32991489`。
原包、原校验文件与截图保持不变。本轮 CSS 修复涉及运行代码，因此最终门禁通过后另建
Hygiene 标识便携包，禁止覆盖原包；仍未加密、包含原样 .env，仅限内部授权使用。

本轮开始时四个历史清理目标仍存在：

1. `%TEMP%/cis-ui2-portable-20260831-0018`（含密钥）。
2. `%TEMP%/cis-ui2-final-1dcf372e6eed408c84f7ad4e6d4c733f/runtime/data/verification.db`。
3. `%TEMP%/cis-ui23-package-20260831`（含密钥）。
4. `%TEMP%/cis-ui23-d2c7fa06920547eab956f5c4bf2f53df/runtime/data/verification.db`。

数据库 -wal/-shm 若存在也需人工删除。本轮只读确认，不更换工具绕过此前策略拒绝。
新交付文件：`dist/CIS-UI2-V2.3-Hygiene-PRIVATE-20260831.zip` 及 `.zip.sha256`。
独立解压启动、逐文件校验、八页检查、FAB 回归、端口回收与清理结果写入同名
`.verification.json`，绑定最终 ZIP 哈希；包内不自写外部验证结论，避免循环哈希。
历史人工清理未完成时，不标记整个清理任务完成。
