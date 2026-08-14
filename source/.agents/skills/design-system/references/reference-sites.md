# 参考站 Design Token 对比（2026-08-11 浏览器实测）

> 提取方法：`control-browser`（Playwright）读取 computed style。
> 结论：**方向是浅色 Monet，参考站只借鉴版式层，不借鉴深色底/主色。**

## 1. Mercury（mercury.com + demo.mercury.com/dashboard）— 用户认可的最佳参考

| 维度 | Mercury 实测值 | 借鉴结论 |
|---|---|---|
| 主题 | 深色 `#171721`(html) / 侧边栏 `#10101A` | ❌ 不借鉴（方向冲突） |
| 主色 | 靛蓝 `#5266EB` | ❌ 不借鉴（保持青绿 `#5b8a83`） |
| 文字 | 主 `#EDEDF3` / 次 `#9D9DA8` | ❌ 不借鉴（保持深墨 `#1f2a3a`） |
| 正文字体 | arcadia / UI 用非标字重 360-420 | ❌ 换字体成本高 |
| H1 | 45px / 480 / lh 1.1 | ✅ 负字距思路 |
| 强调数字 | **28px / 380**（很轻） | ✅ 大数字轻字重 |
| 表格表头 | **13px / 400 / ls 0.1px** | ✅ 可选（当前是 12px/700/大写） |
| 表格单元格 | 16px / lh 1.0 / 竖排收紧 | ✅ 行高压缩可选 |
| 按钮圆角 | pill（32-40px） | ✅ 可选（当前 12px） |
| 输入框圆角 | pill（32px 左） | ✅ 可选 |
| 数字对齐 | tabular-nums | ✅ **已落地** |
| 卡片圆角 | 近直角 | ✅ 数据卡可用小圆角 |

**落地记录**：2026-08-11 Batch 1 已落地 `td` tabular-nums、`.metric strong` weight 600 + tabular-nums、
`.metric-box strong` tabular-nums。截图：`tests/screenshots/batch1-before/after(-etf).png`。

## 2. shadcn/ui（ui.shadcn.com）

| 维度 | 实测值 | 借鉴结论 |
|---|---|---|
| 字体 | Geist | ❌ 不换字体 |
| H1 | 48px / 600 / **ls -2.4px** | ✅ 大标题强负字距可选 |
| 正文 | 16px / 400 / lh 1.5 | ✅ 已是基线 |
| 组件圆角 | 8px / 10px | ✅ 数据组件小圆角可选 |
| 颜色 | oklch 深色变量 | ❌ 不借鉴 |

## 3. iA.net（ia.net/topics）

| 维度 | 实测值 | 借鉴结论 |
|---|---|---|
| 主题 | 近黑 `#070707` | ❌ 不借鉴 |
| 正文字体 | iASansNight 22px / lh 1.65 | ✅ 大正文行距可选 |
| 标题 | 58px / 700 / **ls -0.87px** | ✅ 负字距大标题 |
| 内容宽度 | max-width 768px（正文）/ 1024px（标题） | ✅ 阅读宽度约束可选 |

## 4. Emil Kowalski（emilkowalski.ski — 站点 DNS 不可达，用公开文档值）

| 维度 | 值 | 借鉴结论 |
|---|---|---|
| 抽屉/面板 | `cubic-bezier(0.32, 0.72, 0, 1)` | ✅ 已采纳为 `--ease-drawer` |
| 标准 ease-out | `cubic-bezier(0.22, 1, 0.36, 1)` | ✅ 与 `--ease-out`(0.23,1,0.32,1) 近似 |
| 弹性入场 | overshoot 变体 | ❌ 未落地 |

## 5. 下一步候选（未做，需用户/vision 模型拍板）

1. 表头压缩：12px/700/大写 → 13px/400/正常大小写 + 0.1px（影响所有表格惯例）
2. 按钮 pill 圆角：12px → `--radius-pill`（大动作，需单独评估）
3. `.metric strong` 字重再降：600 → 500/400（Mercury 380-480 更极端）
4. h1 负字距加深：-0.04em → -0.05/-0.06em
5. 数据卡片小圆角 token（8-12px）替代 24px 全家桶
