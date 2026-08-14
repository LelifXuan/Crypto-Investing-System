# 设计 Token 表（Editorial Research Terminal）

> 事实源：`app/static/editorial.css :root`。该文件在 legacy stylesheet 后加载，迁移期负责最终语义。

## 1. 色彩（核心语义）

| Token | 值 | 语义 |
|---|---|---|
| `--bg` | `#f2efea` | 应用底色 |
| `--bg-strong` | `#e8e3dd` | 侧栏底色 |
| `--surface` | `#f7f5f1` | 主画布 |
| `--surface-elevated` | `#fcfbf8` | 一级表面 |
| `--surface-muted` | `#f0edf3` | 弱表面 |
| `--text-primary` / `--ink` | `#211d2b` | 主文字 |
| `--text-secondary` | `#5f5968` | 次文字 |
| `--accent` | `#66548e` | 品牌紫 |
| `--accent-strong` | `#4d3b73` | 深紫、选中与主操作 |
| `--accent-soft` | `#ece8f3` | 紫色弱背景 |
| `--info` | `#3e6f9f` | 信息蓝 |
| `--bullish` | `#34745f` | 看涨 |
| `--bearish` | `#a34f5f` | 看跌 |
| `--bullish-chip-ink` / `--bullish-chip-surface` | `#285e4d` / `#e5eeea` | 看多胶囊文字 / 底色 |
| `--bullish-chip-surface-soft` / `--bullish-chip-border` | `#eef3f1` / `#c6d9d1` | 温和看多胶囊底色 / 边框 |
| `--bearish-chip-ink` / `--bearish-chip-surface` | `#843e4c` / `#f2e6e9` | 看空胶囊文字 / 底色 |
| `--bearish-chip-surface-soft` / `--bearish-chip-border` | `#f6eff1` / `#e2cbd0` | 温和看空胶囊底色 / 边框 |
| `--neutral-chip-ink` / `--neutral-chip-surface` | `#59535f` / `#ece9e4` | 中性胶囊文字 / 底色 |
| `--neutral-chip-border` | `#d9d3ca` | 中性胶囊边框 |
| `--warning` | `#9b6a25` | 警告 |
| `--danger` | `#9d3f48` | 故障/高风险 |
| `--border` | `#d9d3ca` | 通用分隔线 |
| `--border-strong` | `#c8c0b6` | 强边界 |
| `--direction-up` | `#16a34a` | K线涨（仅图表 wick） |
| `--direction-down` | `#dc2626` | K线跌（仅图表 wick） |

**body 背景是纯色 `--bg`**，禁止恢复装饰性径向光晕和纸张网格。

## 2. 全画布尺寸

| Token | 值 | 用途 |
|---|---|---|
| `--sidebar-width` | `216px` | 桌面侧栏 |
| `--sidebar-collapsed-width` | `64px` | 折叠侧栏 |
| `--canvas-gutter` | `clamp(20px,1.5vw,36px)` | 主画布边距 |
| `--topbar-height` | `64px` | 顶部上下文栏 |
| `--reading-measure` | `800px` | 长正文最大行宽 |

## 3. 圆角 / 阴影 / 间距

| Token | 值 | 用途 |
|---|---|---|
| `--radius` | `14px` | 重点面板 |
| `--radius-sm` | `10px` | 数据区 |
| `--radius-card` | `10px` | 普通内容区 |
| `--radius-pill` | `999px` | 胶囊（可选：Mercury 式按钮） |
| `--shadow-soft` | `0 18px 40px rgba(31,42,58,0.07)` | 软阴影 |
| `--shadow-card` | `0 22px 56px rgba(31,42,58,0.1)` | 卡片阴影 |
| `--shadow-hover` | `0 26px 70px rgba(31,42,58,0.14)` | 悬停阴影 |
| `--shadow-button` | `0 6px 14px rgba(91,138,131,0.10)` | 按钮 |
| `--shadow-button-hover` | `0 10px 22px rgba(91,138,131,0.18)` | 按钮悬停 |
| `--reading-measure` | `800px` | 正文宽度；不限制工作台 |
| `--content-gap` | `24px` | 内容间距 |
| `--section-gap` | `28px` | 区块间距 |
| `--card-padding` | `28px` | 卡片内边距 |
| `--chart-height` | `clamp(430px, 43vh, 560px)` | 图表高度 |
| `--space-inline` | `6px` | 图标与文字、紧密内联元素 |
| `--space-action` | `8px` | 同级按钮与动作控件 |
| `--space-control` | `12px` | 工具栏字段与控制组 |
| `--space-card` | `16px` | 同级卡片与工作区面板 |
| `--space-section` | `24px` | 页面一级章节 |

## 4. 字体

| Token | 值 |
|---|---|
| `--font-sans` | `"IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif` |
| `--font-mono` | `"IBM Plex Mono", "SFMono-Regular", Consolas, monospace` |

**版式要点（Mercury 借鉴，2026-08-11 已部分落地）**：
- `h1`: `clamp(34px,3vw,46px)` / lh 1.08 / `letter-spacing: -0.04em`
- `h2`: `clamp(24px,1.5vw,30px)` / lh 1.12 / `-0.03em`
- 表格 `td`: `font-variant-numeric: tabular-nums`（✅ 已落地）
- `.metric strong`: `clamp(30px,2vw,38px)` / weight 600 / `-0.05em` / tabular-nums（✅ 已落地）
- `.metric-box strong`: 18px / `-0.03em` / tabular-nums（✅ 已落地）
- 表头 `th`: 12px / 700 / `0.08em` / uppercase（现有惯例，可选项：改 13px/400）

## 5. 动效（Emil Kowalski 曲线）

| Token | 值 | 用途 |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | 入场/按压/悬停 |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` | 形变/混色 |
| `--ease-drawer` | `cubic-bezier(0.32, 0.72, 0, 1)` | iOS 式抽屉/面板/弹窗 |
| `--dur-press` | `120ms` | 按压 |
| `--dur-hover` | `180ms` | 悬停 |
| `--dur-elevate` | `220ms` | 抬升 |
| `--dur-drawer` | `240ms` | 抽屉 |
| `--motion-fast` | `120ms var(--ease-out)` | 快捷动效 |
| `--motion-hover` | `180ms var(--ease-out)` | 悬停动效 |

阶梯约束：`dur-press < dur-hover < dur-elevate < dur-drawer` 必须保持。

## 6. 语义色矩阵（audit §11，硬约束）

| 语义 | 允许颜色 | 禁止共用 | 文字/图标补充 |
|---|---|---|---|
| Bullish | 方向色 | Live / Success / Selected | 必须有"看涨/多"文字 |
| Bearish | 方向色 | Danger / Data Error | 必须有"看跌/空"文字 |
| Warning | 风险色 | Bearish | 必须有警告图标或文字 |
| Danger | 故障或高风险 | 普通 Bearish | 不得仅靠颜色 |
| Live | 数据质量色 | Bullish | 必须显示 Live 文字 |
| Stale | 数据质量色 | Warning 同族但不同图标 | 必须显示时间 |
| Neutral | 中性色 | Accent / Bullish | 必须显示中性文字 |
| Selected | 交互状态色 | Bullish | 用边框/背景/Focus 表示 |

注意：品牌、选中、看涨、看跌、信息、实时、警告、故障必须使用独立语义 token，禁止同色复用。
