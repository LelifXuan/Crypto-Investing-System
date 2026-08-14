# 动画设计能力模块

> 动画设计规范 + 可复用配方。诊断基线 2026-08-11（见 §1）。
> 原则：**动画是信息的编排，不是装饰**——入场建立层级、退出是系统响应、数据更新表达变化。

## 1. 诊断基线（2026-08-11 实测，实施修复前先读）

| 场景 | 现状 | 根因 | 修复位置 |
|---|---|---|---|
| SPA 页面切换 | **无动画（硬切）** | `styles.css:7474` 定义了 `.page-transition`（fadeIn 220ms + 6px）但 `main.js` 的 boot/scheduleBoot/navigateToPage **从未挂这个 class** | `main.js` navigateToPage/boot 挂 `.page-transition` |
| 图表刷新 | 跳变 | `charts.js:807` `new Chart()` 无 animation 配置；`lineDataset()` 每次返回新对象，`update()` 整体替换无法差值 | 加 `animation.duration/easing` 或数值过渡插件 |
| 上下滚动 | 页内 smooth 已有 | `scroll-behavior: smooth` 在 145 行；但 SPA 切页**滚动位置不复位** | `navigateToPage` 加 scroll-to-top |
| 卡片/抽屉 | 部分有 | `.strategyDetailsIn`(240ms) / dropdown 已有 | 保持 |

## 2. 动画设计原则

1. **节奏阶梯**：`--dur-press 120ms < --dur-hover 180ms < --dur-elevate 220ms < --dur-drawer 240ms`。
   - 按压/微交互 → 120ms；悬停 → 180ms；元素入场 → 220ms；抽屉/面板 → 240ms。
   - 退出动画比入场**快且干脆**（系统响应要"snap"）：如 `.page-transition-out` 80ms 是对的，别改成慢速。
2. **曲线语义**（Emil Kowalski，已入库 `--ease-*`）：
   - `--ease-out`：入场/按压/悬停（标准减速）
   - `--ease-drawer`：iOS 式抽屉/面板（强减速开场）
   - `--ease-in-out`：屏幕内形变/混色
   - 禁止 `ease-in` 用在 UI 入场（"ease-in on UI is a block"——是既有注释教训）。
3. **入场动效规则**：
   - 位移量小（4-8px），不夸张；配合 opacity，`transform: translateY(4-8px)` + fade。
   - 同屏多个卡片用 **stagger**（`animation-delay: calc(var(--i) * 30-40ms)`），上限 8 个，避免排队感。
   - 尊重 `prefers-reduced-motion`（见 §4 强制降级）。
4. **数据更新规则**：
   - 数字变化 → 滚动/位移动画（或 tabular-nums 无抖动）；整体替换无法差值时，宁可短 fade 也不硬跳。
   - Chart.js 数据更新：优先 `chart.data.datasets[i].data` 原地替换（保留差值动画），避免重建 dataset 对象。
5. **性能**：动画只动 `opacity` / `transform`（GPU 合成层）；禁止动画 `width/height/top/left`。动效门禁：`python tests/motion_verify.py`（WARN 基线：`--dur-elevate`/`--ease-in-out` 未引用 + 27 处硬编码时长——见 verification.md 基线表）。

## 3. 可复用动画配方

### 3.1 页面切换（SPA）
- CSS 已有 `.page-transition`（enter）与 `.page-transition-out`（exit 80ms）。
- 正确接线：切换前给当前页容器加 `.page-transition-out`，等待动画结束（~80ms）再卸载；新页挂载后给容器加 `.page-transition`。
- **当前未接线**（诊断①）——main.js 需要：`navigateToPage` 时对旧容器加 out class，`boot` 完成 mount 后对新容器加 `.page-transition`。

### 3.2 数字滚动
```css
@keyframes countUp { from { opacity: 0.4; transform: translateY(3px); } to { opacity: 1; transform: none; } }
```
- 数字更新时给数字元素重触发该 keyframe（`el.animate()` 或 re-add class），与 tabular-nums 搭配。

### 3.3 卡片 stagger 入场
```css
[data-stagger] > * { animation: fadeUp 220ms var(--ease-out) backwards; }
[data-stagger] > *:nth-child(n) { animation-delay: calc((n - 1) * 35ms); }
```
- 容器标 `data-stagger`，子项按序延迟；`backwards` 防止首帧闪烁。上限 8 项。

### 3.4 图表数据更新（Chart.js）
- 创建时：`options.animation = { duration: 600, easing: 'easeOutQuart' }`。
- 更新时：原地替换 `dataset.data`，避免重建 dataset 对象导致整体跳变：
  ```js
  chart.data.datasets[i].data = newData;
  chart.update();
  ```

### 3.5 滚动与切页复位
- `navigateToPage` 内加 `window.scrollTo({ top: 0, behavior: 'smooth' })`（配合已存在的 `scroll-behavior: smooth`）。

### 3.6 全站统一骨架闪烁动画 (2026-08-14)

`@keyframes skeletonShimmer`（1.6s ease-in-out、opacity 0.45↔0.85）从"仅图表骨架"
扩展到全站所有 loading 占位元素，统一"等待"感视觉语言。

**承载 selector**：
- `.chart-skeleton-candle` / `.chart-skeleton-axis span`（via `.loading-pulse` class，由 `chartSkeleton()` 在 `core/dom.js:360` 输出）
- `.shimmer-bar::after`（`loadingState()` 在 `core/dom.js:350` 输出，loading 进度条）
- `.nav-skeleton-row`（SPA 切页骨架条，由 `renderNavSkeleton()` 在 `core/dom.js:79` 输出）
- `.event-stream-skeleton-copy i`（市场事件流的"假文字行"）

**复用 `.loading-pulse` class**：原本是死类（只出现在 reduced-motion block，CSS 无定义、JS 无调用），
现在作为通用骨架闪烁 class。语义吻合（"加载中脉冲"= 骨架闪烁），不必新增 token。
`chartSkeleton()` 现在显式给每根 candle 与 axis span 挂 `class="loading-pulse"`，
CSS 不再用 selector-级 `animation` 而是 class-级。

**降级**：沿用全局 `prefers-reduced-motion` 块（`animation-duration: 0.01ms`）—— 静态骨架
以 opacity 0.45 显示。与 `event-stream-skeleton-dot` 的 `animation: none !important` 不一致，
但后者是因为有 `animation-delay` 阶梯，只压时长会留错位。

**清掉的死 keyframe**：`shimmerSlide`（`styles.css` 旧的 1.4s 扫光）、`nav-skeleton-shimmer`
（SPA 切页的 background-position 扫光）。两者替换为 `skeletonShimmer` 后无人使用。

**测试门禁**：`tests/test_skeleton_shimmer_consistency.py`（11 项断言）钉住四个 carrier selector、
chartSkeleton DOM 输出、两个 dead keyframe 已清、reduced-motion 沿用压时长。

## 4. 无障碍（强制）

- `@media (prefers-reduced-motion: reduce)` 下**禁用/降级所有动画**：opacity 过渡保留（信息层），位移/缩放/滚动动画移除。
- 现状：`styles.css:11965` 已有 `animation: none !important` 的降级分支，**新动画必须纳入该降级**。
- tooltip 键盘焦点触发仍缺失（audit §6.4 P1-A11Y）——动画不能依赖 hover 传达唯一信息。

## 5. 验证

- 动画改动 = CSS + 可能的 main.js（工作流）→ 跑 `motion_verify.py` + `verify_pages.py`（main.js 改动全量 9 页）。
- 实测：浏览器截图 + `pageerror`=0；非多模态模型用 DOM/computed style 验证，观感交用户/vision。
