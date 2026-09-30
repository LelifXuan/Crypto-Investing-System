# CIS System Integrity Baseline

- **Baseline 标识**: `CIS-UI2-V2.3-Page-Migration`
- **基线日期**: 2026-09-30
- **模式**: Integrity Remediation（仅 P0/P1）
- **主目标**: 正确性、隔离性、真实性、金融语义完整性
- **禁止目标**: 无关重构 / 美化 / 架构重写

## 1. 基线代码状态

V2.3 定版批次已按功能域提交入库，工作区干净。基线 commit（自旧到新）：

| Commit | 域 | 内容 |
|---|---|---|
| `5655028` | [docs] | V2.3 CHANGELOG 章节 + 验证门禁记录 + README/技术债/验收文档 |
| `d89019e` | [config] | 版本口径统一 2.3.0（app/pyproject/.env.example/start.bat） |
| `6759df8` | [strategy] | 按交易级别重建策略（周期决策/机会扫描/参考价/跨页一致性）+ 监控只读会话 + 预热裁剪 |
| `edb8400` | [frontend] | 策略页 15 单元矩阵投影 + 周期机会/周期聚焦渲染 |
| `d072795` | [test] | 周期决策/扫描发布器/15 抽屉/非法计划价位守卫 + 截图与验证报告（含 scripts 与 CFTC 数据行尾归一） |

## 2. 基线验证状态（摘自 CHANGELOG V2.3 章节）

- 2026-09-29 周期详情与扫描同源门禁：全量 `pytest` **2229 passed、4 skipped、0 failed**；维护范围 Ruff、`compileall` 通过；Playwright **11/11 冷启动、10/10 SPA 切换**；真实扫描压力测试 **2 PASS / 0 FAIL**。
- 应用版本 `2.3.0`；`/openapi.json` 版本一致。

## 3. 基线已知盲区（本轮整改动机）

现有测试主要验证 component correctness（schema、渲染、resolver 行为、页面契约），未充分验证：

1. **信号归属**——BTC 专属信号是否影响了非 BTC 策略方向（P0-QNT-001）；
2. **数值字段的金融含义**——绝对正值 level 被当作流入增量（P1-QNT-002）；
3. **评分语义**——启发式证据分是否被用户理解为成功概率（P1-SEM-001）；
4. **全局状态真实性**——Shell 静态写死「系统在线/数据连接正常」（P1-STATE-001）；
5. ~~分发边界~~——**撤回（所有者决定 2026-09-30）**：密钥系所有者为本分发单独创建，嵌入内部包系授权设计；仅保留打包门禁作为默认卫生设施。

本轮把测试标准从 component correctness 提升到 **system invariant correctness**（INV-001..005，见 ACCEPTANCE 文档）。

## 4. 整改范围声明

只处理 `CIS_P0_P1_FIX_REGISTER.md` 中登记的 5 个 finding。§2 排除清单（框架迁移、Portfolio Engine、OMS、概率校准模型、全站 CSS 重写等）一律不做。P2 项仅登记 DEFERRED，不阻塞、不顺手修。
