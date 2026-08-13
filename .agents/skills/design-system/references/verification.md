# 视觉验证门禁（强制流程）

> 遵循 AGENTS.md §六。**绝对禁止未经验证即汇报完成。**

## 1. 门禁清单与作用域

| 门禁 | 命令 | 何时必跑 |
|---|---|---|
| CSS 审计 | `python tests/css_audit.py` | 改动 styles.css（**增量门禁**：只对新增死类 FAIL；首次跑先 `--rebase` 记录存量基线，清理完一批死码后再 `--rebase` 下调） |
| 动效审计 | `python tests/motion_verify.py` | 改动动效 token/transition |
| 前端静态测试 | `python -m pytest tests/test_ashare_etf_frontend_static.py tests/test_spa_router_navigation.py -q` | 任何前端改动 |
| 实例检查（全量） | `python tests/verify_pages.py` | 改 main.js / core/*.js / 模板 / 架构 / 修复任何页面后 |
| 实例检查（定向） | `python tests/verify_pages.py --pages <page>` | 只改单个 pages/*.js |
| 无障碍 | `python tests/a11y_scan.py` | 改颜色/对比度/ARIA/键盘交互 |
| 视觉回归 | `python tests/a11y_visual_diff.py` | 改布局/样式后（需 baseline） |
| 响应式 | `python tests/responsive_check.py` | 改布局/宽度/断点 |
| 性能 | `python tests/perf_gate.py` | 改渲染路径/加载/大列表 |
| 原生 select 守卫 | `python -m pytest tests/test_no_native_select_remaining.py` | 任何模板/JS 改动 |

> 注：a11y/visual_diff/responsive/perf 当前仅 1 页试点（2026-08-11），全 9 页一键入口未接。

## 2. 已知门禁基线（2026-08-11 实测，避免误判为新回归）

| 门禁 | 当前状态 | 说明 |
|---|---|---|
| `css_audit.py` | **增量 PASS（2026-08-11 改造）**：dead 472 存量债务 / 0 新增；token 覆盖 68.9%、硬编码色 340 为 WARN | 检测器已排查为**准确**（DOM 抽样验证非误报）。472 个死类是历次重构遗留的旧类名（JS 已改名但 CSS 未删）。已改为**增量门禁**：基线存 `tests/css_audit_baseline.json`，只对新增死类 FAIL；灵敏度测试验证过（注入假死类 → FAIL，恢复 → PASS）。**新增死类必须清理，存量债务分批清理后 `--rebase` 下调基线** |
| `motion_verify.py` | WARN：9/9 token 100% 覆盖、5 处硬编码时长（无限循环动画） | 2026-08-11 已修复 token 覆盖 |
| 前端静态测试 | 26 passed | 绿 |
| 运行截图 | `tests/screenshots/batch1-*.png` | Batch 1 版式对比 |

**规则**：改动前后各跑一次相关门禁，diff 只应为本次改动引入；既有 FAIL/WARN 单独说明，不冒充本次回归。

## 3. 浏览器实测截图（视觉改动必做）

### 3.1 视口规范（2026-08-11 强制）

**开发者显示器物理分辨率 2560×1440（16:9）。** 所有截图必须统一到此视口：

```python
# Playwright 脚本内
ctx = browser.new_context(viewport={"width": 2560, "height": 1440})
```

```js
// control-browser 内
await tab.setViewportSize({ width: 2560, height: 1440 });
```

```bash
# CLI 入口
python tests/verify_pages.py --viewport 2560x1440  # 已是默认值
python tests/responsive_check.py --viewports desktop-2k  # 响应式测试含 2K 档
```

> **为什么**：截图效果必须与开发者肉眼看到的一致。1366×900 下布局宽松，
> 2560×1440 下卡片间距、图表大小、文本行宽才会暴露真实问题。

### 3.2 截图流程（全页 + 交互展开，2026-08-11 强制）

**禁止只截视口顶部！** 必须 `fullPage: true` 截取整个页面内容。

#### 全页截图步骤

1. 设置视口 `setViewportSize({ width: 2560, height: 1440 })`
2. 等待 API settle（`waitForTimeout(4000-5000)`）
3. **滚动到页面底部**触发 `content-visibility: auto` 的懒渲染元素
4. `screenshot({ fullPage: true })` 存档

#### 交互展开检查（容易遗漏的区域）

部分页面有 **抽拉面板 / 折叠区域 / 抽屉**，截图前必须展开：

| 页面 | 展开目标 | 操作方式 |
|------|----------|----------|
| AI 策略 | `page-guide-fab` → `page-guide-panel` | 点击 `.page-guide-fab` |
| BTC 衍生品 | 期限矩阵 / 墙位详情 | 滚动到图表区域 |
| 黄金配置 | Workbench / 合约参考 / DCA 面板 | 滚动到页面下半部 |
| 形态结构 | 通道详情 / 摆动点 tooltip | 滚动 + hover |

#### 重点检查区域

- **图表 canvas**：K线、资金费率、持仓量、收益曲线 — 必须完整渲染
- **数据表格**：期限矩阵、墙位矩阵、事件列表 — 行列完整
- **策略面板**：DCA 金额、风控门禁、执行建议 — 文字清晰
- **底部区域**：页脚、版权、最后一张卡片 — 不被截断

**非多模态模型的限制**（重要）：当前模型读不了截图（`Media omitted`）。分工：
- 模型负责：DOM 几何、computed style、重叠/溢出、`pageerror`、stylesheet 规则断言、页面结构。
- 用户/vision 模型负责：最终观感（配色好不好看、层级是否清晰）。

建议的多模态工作流：
1. before 截图 → 存档 `tests/screenshots/<feature>-before.png`
2. 改动 → 跑门禁 → after 截图 → 存档 `tests/screenshots/<feature>-after.png`
3. 把两张图交给 vision 模型对比，或用户自行查看拍板
4. 定稿后按 AGENTS.md §七独立 commit（`[frontend] 简述`）

## 4. 压力测试（2026-08-11 新增，交互密集页面必做）

**普通实例检查无法发现卡顿问题！** 因为 `verify_pages.py` 每次加载后等 3-5 秒，
完全没模拟真实用户的快速操作。以下页面必须做压力测试：

### 4.1 压力测试命令

```bash
# 形态结构页 — 快速切换标的/时间周期
python tests/stress_test.py --page market-structure --rapid-clicks 15

# 技术指标页 — 快速切换标的按钮 + 刷新
python tests/stress_test.py --page market-analysis --rapid-clicks 15

# AI 策略页 — 快速展开/折叠抽屉 + 连续生成
python tests/stress_test.py --page ai-strategy --rapid-clicks 10

# 全量压力测试
python tests/stress_test.py
```

### 4.2 已知压力测试问题（2026-08-11 实测确认）

| 页面 | 操作 | 现象 | 根因 |
|------|------|------|------|
| **形态结构** | 快速切换标的/时间周期（< 400ms 间隔） | **图表区域完全空白**，`loading: 0` 但 `canvas: 0` | 快速切换中断了图表渲染管线，`content-visibility` 或 `AbortController` 未正确处理中断后的恢复 |
| **技术指标** | 快速点击标的按钮（15 次，100ms 间隔） | **loading 不消失**（`loading: 3` 持续 5s+） | 并发请求竞争，旧请求的 loading 状态未被取消 |
| **AI 策略** | 冷启动打开页面 | 显示"无策略"，需手动展开每个抽屉并点击"生成" | 冷缓存无预计算数据，workbench 需要用户主动触发每个分析模块 |
| **AI 策略** | 点击机会矩阵格子 | 打开 `#strategy-detail-panel` 抽拉面板，但数据常不完整 | 抽拉面板调用 4 个并行 API（unified/monitoring/derivatives/macro），任一失败则显示"价位缺失/几何关系无效"、"盈亏比 0:1" |
| **AI 策略** | 快速点击多个矩阵格子 | 每个格子都显示"无明确方向"，需逐个点击打开 | 矩阵 15 个格子 × 3 个时间周期，冷启动时全部为 WAIT/NO_TRADE 状态 |

### 4.3 压力测试检查清单

```
☐ 形态结构：快速切换 5+ 标的 × 5+ 时间周期，图表始终渲染
☐ 技术指标：快速切换 5+ 标的，loading 在 3s 内归零
☐ AI 策略矩阵：逐个点击 15 个矩阵格子，每个应打开 #strategy-detail-panel 抽拉面板
☐ AI 策略数据：抽拉面板内的数据不应出现"价位缺失"、"盈亏比 0:1"、"几何关系无效"
☐ AI 策略抽拉：打开抽拉面板 → 关闭 → 打开下一个，连续操作无卡顿
☐ BTC 衍生品：快速滚动 + 切换周期，无空白闪烁
☐ 黄金配置：快速切换 Workbench 模块，数据不丢失
```

### 4.4 AI 策略页抽拉面板问题详解（2026-08-11 实测）

**页面结构**：
- 机会矩阵：5 品种 × 3 时间周期 = 15 个 `.scan-cell-btn` 按钮
- 抽拉面板：`<aside id="strategy-detail-panel">` 滑入式抽屉
- 渲染管线：点击格子 → `onSelectOpportunity()` → `openDetailPanel()` → 4 并行 API 调用

**问题链**：
1. **冷启动全部"无明确方向"**：矩阵所有 15 个格子显示"无明确方向"，因为统一策略缓存尚未生成
2. **需逐个手动点击**：用户必须点击每个格子才能打开抽拉面板查看是否有策略
3. **数据不完整**：即使打开面板，4 个并行 API（unified/monitoring/derivatives/macro）可能部分失败
   - 失败时显示："入场、止损或止盈价位缺失或几何关系无效，计划已阻止执行"
   - 盈亏比显示："0:1"（无效值）
4. **需手动重建**：用户必须点击"立即重建本单元"按钮强制重新生成

**代码位置**：
- `app/static/pages/strategy/index.js:146` — `onSelectOpportunity()` 入口
- `app/static/pages/strategy/renderDetailPanel.js:80` — `openDetailPanel()` 创建抽屉
- `app/static/pages/strategy/renderScanMatrix.js:12` — `renderScanMatrix()` 渲染矩阵
- `app/static/pages/strategy/renderScanMatrix.js:85` — `bindScanMatrix()` 绑定点击事件

### 4.4 压力测试方法（control-browser CUA）

IAB 的 Playwright locator 在快速连续点击时会出现 `broker response id mismatch`，
必须用 CUA 坐标点击来模拟真实快速操作：

```js
// 获取按钮坐标
const coords = await tab.playwright.evaluate(() => {
  var btn = document.querySelector('button.dropdown');
  var rect = btn.getBoundingClientRect();
  return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
});

// 快速连续点击（< 200ms 间隔）
for (let i = 0; i < 10; i++) {
  await tab.cua.click({ x: coords.x, y: coords.y });
  await tab.playwright.waitForTimeout(150); // 模拟人类快速点击
}
```

## 5. 验证通过标志（AGENTS.md 原文）

```
☐ ruff: All checks passed
☐ pytest: X passed, 0 failed
☐ compileall: all compiled
☐ node --check: all passed
☐ verify_pages 全量通过（架构/工作流改动时）
```

**如果 verify_pages 有任何 FAIL，任务未完成。** 不允许以"可能是缓存"为理由跳过。
