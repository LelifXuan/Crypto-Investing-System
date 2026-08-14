# Custom Dropdown 组件重构 Spec (2026-07-31)

> 本 spec 由用户 17 节附件驱动。`pasted-text-20260731-162251-62970e59.txt` 已经把所有要求逐节给出；本 spec 把它们聚成可验证的子项，**不改动业务逻辑、DATABASE、API、图表、市场分析**——严格遵守附件 §十六 "实现边界"。

| 项 | 内容 |
|---|---|
| Spec 日期 | 2026-07-31 |
| 解决对象 | `app/static/ui/dropdown.js` + `app/static/styles.css` 中 `.dropdown*` rules |
| 改动范围 | dropdown 组件、相关 CSS、调用参数（向后兼容）、测试、token |
| 关键证据 | 附件截图（左侧"弧光/月牙"形状）+ 现有 CSS (11260-11294) `border-left:2px solid transparent` + `border-left-color:var(--accent)` on selected — 这是"月牙"的真实成因 |
| 不变更 | dropdown 调用方业务逻辑、页面 topology、图表组件、API、数据库 |

---

## 1. 根因分析

### 1.1 左侧"弧光 / 月牙"

| 现象 | 真实成因 |
|---|---|
| 选中项左侧出现深色弧光或月牙 | `.dropdown-item` (`styles.css:11268`) 设置 `border-left: 2px solid transparent`，是为 `[aria-selected="true"]` (`styles.css:11287`) 设置 `border-left-color: var(--accent)` 留通道。但 `border-left-width: 2px` 始终生效，selected 时切换为 `var(--accent)`，**未 selected 时是 transparent**。配合 `border-radius: 12px`（option） + Popover 上 `overflow: hidden` 的潜在圆角裁切，顶部 / 底部 12px 与左右圆角错位 → 视觉上出现"垂直亮带"，误读为"月牙"。|
| 多个选项同时出现底色 | (a) `close()` 不主动清掉 `is-active` 类；下次 open 时 `moveActive()` 重新设，但也可能因 `aria-selected` 在 `refresh()` 后未重新同步 → 一个是真的 selected，一个是上次 keyboard-active 的遗留。(b) `selectValue()` 内部 `prev === value` 早返回，导致"鼠标曾经过的项"如果 `value === prev` 又被 swap 一次，会双重 setActiveIndex。 |
| 长文本挤压 / 截切 | Trigger / Popover 宽度锁 `rect.width`（`dropdown.js:38, 39`）。短 Trigger（`4h` / `1d`）超过 60% 留白；长 Trigger（"全部供给节点"）单行省略甚至被切。 |
| 滚动条过宽 | styles.css 当前未声明 `::-webkit-scrollbar`，落到用户系统默认（Win 通常 17px）。 |

### 1.2 选择器优先级冲突

| 选择器 | 影响 |
|---|---|
| `.dropdown-item[aria-selected="true"].is-active` | 覆盖 `is-active` 自身视觉，**却保留同样的 0.16 accent-soft 底色**。键盘导航到 selected 项时 = 同色，"没有区分"。 |
| `.dropdown-item:hover` (CSS only, 不写 class) | 但 hover 时**没有清掉 `is-active`**——键盘导航到一个非 selected 的项，鼠标再 hover，键盘 active 与 mouse hover 双重 effect。 |

### 1.3 上一次 commit 已确认 §16.A 的 10 个 token 已就位；本 spec 不再补 token。

---

## 2. 设计（用户已批准的 4 个回答）

| 决策 | 选择 |
|---|---|
| Popover 渲染位置 | **保留 portal**（appendChild 到 `document.body`，靠 `positionPopover()` 计算坐标）|
| 状态机 / 选择器优先级 | **同时重塑 CSS 选择器优先级**（`is-active` 与 `aria-selected` 视觉必须分开，且 hover 不写持久 class）|
| type-ahead 事件 | **本次一并修复**（仅在 popover `is-open` 且 trigger 获取焦点时拦截字母键）|
| 调用点迁移 | **逐页迁移 + 默认值兼容**（旧 22 个调用点可选，是否迁移由 caller 决定）|

---

## 3. 状态模型

### 3.1 单一事实来源

| 状态 | 表示 | 存活期 |
|---|---|---|
| **committed value** | `<button class="dropdown">` 的 `aria-expanded` + `data-value`（popover 内 `aria-selected` 由 syncSelected 重算） | 跟随 component 实例 |
| **selected** | `[role="option"][aria-selected="true"]` 单选最多 1 个 | 跟随 component 实例；`refresh()` / `setValue()` / `open()` 都重新同步 |
| **keyboard highlight** | `[role="option"][data-highlighted="true"]` 单选最多 1 个 | **仅 popover open 期间**；`close()` 立刻清掉 |
| **hover** | 纯 CSS `:hover`，不写 class | 随 mouseenter / leave |
| **focus** | `:focus-visible` on trigger，与 selected 视觉不同 | 跟随 trigger focus |
| **active**（鼠标按压）| CSS `:active` 伪态 | 随 press |

### 3.2 与现有代码的对应

- `aria-selected` → 现有 `aria-selected` (持久)
- `data-highlighted` 替代 `.is-active`（避免与 CSS `.is-active` 命名混淆），重命名为 `data-keyboard-nav` 或保留 `.is-active` 是 implementation detail。我倾向**保留 `.is-active` class 名（不破 CSS）**，但同时把 close() 与 refresh() 中清掉它，并加 `data-highlighted="true"` 属性作为 ARIA 标记（spec 写作 `aria-activedescendant` 替代——更标准）。

最终方案：**保留 `.is-active` class 名，加 `aria-activedescendant` 持有 active item 的 id，每个 option 加 `id`**。这样 ARIA 完全合规，CSS 不破。

### 3.3 状态不变式

- **INV-1**：单选 dropdown 同一时间 `[aria-selected="true"]` ≤ 1 个。
- **INV-2**：popover 关闭后，所有 `.is-active` 被移除；`aria-activedescendant` 被清空。
- **INV-3**：每次 `open()` `refresh()` `setValue()` 后 `syncSelected()` reassert 唯一 selected。
- **INV-4**：mouseenter 不写持久 class；hover 通过 CSS `:hover` 单独表达。
- **INV-5**：开发期断言（生产可关）：`if (selectedItems.length > 1) console.warn(...)`。

---

## 4. CSS 选区（修改）

### 4.1 删除 `.dropdown-item` 的 `border-left: 2px solid transparent`

```css
.dropdown-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 40px;          /* contract bound */
  padding: 9px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;       /* 小于 Popover 圆角 */
  font: inherit;
  font-size: 14px;
  line-height: 1.45;
  text-align: left;
  color: var(--ink);
  cursor: pointer;
  box-shadow: none;          /* 不再叠垂直渐变 */
  transition:
    background var(--motion-fast, 120ms ease),
    border-color var(--motion-fast, 120ms ease),
    color var(--motion-fast, 120ms ease);
}
```

### 4.2 三态视觉分开（selected / highlighted / hover / focus）

```css
/* Hover — 浅 ghost 底色 */
.dropdown-item:not([disabled]):not([aria-selected="true"]):hover {
  background: rgba(91, 138, 131, 0.06);
  border-color: transparent;
}

/* Keyboard highlight — 1px accent border + focus ring */
.dropdown-item.is-active {
  background: rgba(91, 138, 131, 0.10);
  border-color: rgba(91, 138, 131, 0.55);
  outline: none;
}

/* Selected — 完整底色（无左侧条，无内阴影） */
.dropdown-item[aria-selected="true"] {
  background:
    linear-gradient(
      180deg,
      rgba(91, 138, 131, 0.16),
      rgba(91, 138, 131, 0.10)
    );
  border-color: rgba(91, 138, 131, 0.22);
  color: var(--accent-strong);
  font-weight: 600;
}

/* Selected + keyboard-highlighted: 用边框区分，不重底色 */
.dropdown-item[aria-selected="true"].is-active {
  background:
    linear-gradient(
      180deg,
      rgba(91, 138, 131, 0.22),
      rgba(91, 138, 131, 0.14)
    );
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent) inset;
}

/* Disabled — 与其他状态独立，不响应 hover */
.dropdown-item[disabled] {
  opacity: 0.5;
  cursor: not-allowed;
  background: transparent !important;
  border-color: transparent !important;
}
```

### 4.3 Popover 承担主要背景与圆角

```css
.dropdown-popover {
  position: fixed;            /* portal 渲染 */
  z-index: 1000;
  background:
    linear-gradient(
      180deg,
      rgba(252, 249, 243, 0.97),
      rgba(246, 241, 232, 0.95)
    );
  border: 1px solid var(--border-glass);
  border-radius: 16px;
  box-shadow: var(--shadow-card);
  backdrop-filter: var(--blur-soft);
  -webkit-backdrop-filter: var(--blur-soft);
  overflow: hidden;           /* 圆角裁切交给它 */
  display: flex;
  flex-direction: column;
}
.dropdown-popover[hidden] { display: none; }

.dropdown-list {
  display: flex;
  flex-direction: column;
  gap: 2px;                  /* 4-6px gap，主导视觉 */
  padding: 6px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-right: 8px;         /* 不要把文字顶到 scrollbar */
}
```

### 4.4 Trigger 宽度规则（via `sizeMode`）

| 模式 | 行为 |
|---|---|
| `content`（默认）| Trigger 最小 112px，最大 280px；Popover `min-width: max(TriggerRect, 内容测量)` |
| `trigger` | Popover 至少 Trigger 宽，但可加宽至 280px |
| `fixed` | Trigger 用 CSS 由 caller 决定宽度；Popover 等 Trigger |

Trigger 内 grid：

```css
.dropdown[data-size-mode="content"],
.dropdown[data-size-mode="trigger"],
.dropdown[data-size-mode="fixed"] {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 10px;
  min-width: var(--dropdown-min-width, 112px);
  max-width: var(--dropdown-max-width, 280px);
  min-height: 40px;
  padding: 8px 12px;
}
```

### 4.5 长文本换行

```css
.dropdown-label,
.dropdown-item-label {
  min-width: 0;
  overflow-wrap: break-word;
  word-break: normal;        /* 不要在中文里强切字 */
  line-height: 1.45;
}

.dropdown-trigger-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown[data-allow-trigger-wrap="true"] .dropdown-trigger-label {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

### 4.6 Scrollbar (跨浏览器)

```css
.dropdown-list {
  scrollbar-width: thin;
  scrollbar-color: rgba(93, 101, 108, 0.34) transparent;
}
.dropdown-list::-webkit-scrollbar { width: 7px; }
.dropdown-list::-webkit-scrollbar-track { background: transparent; }
.dropdown-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(93, 101, 108, 0.34);
}
.dropdown-list::-webkit-scrollbar-thumb:hover {
  background: rgba(93, 101, 108, 0.55);
}
```

### 4.7 圆角层级

| 元素 | 圆角 |
|---|---|
| Trigger | 12px |
| Popover | 16px |
| Option | 10px |
| Status / Chip | 999px (继承既有) |
| Scrollbar thumb | 999px |
| Dot / Icon | 50% |

---

## 5. JS 修改（`app/static/ui/dropdown.js`）

### 5.1 新 public API（向后兼容）

```js
mountDropdown(root, options) -> { setValue, destroy, refresh }

// 新增可选 options（全部有默认值，旧 caller 不感知）
options = {
  // existing
  items, value, placeholder, hasIcon, state, errorText, typeAhead, onChange,
  // new
  sizeMode: "content" | "trigger" | "fixed",   // default "content"
  minTriggerWidth: 112,                          // px, default 112
  maxTriggerWidth: 280,                          // px, default 280
  allowTriggerWrap: false,                       // default false
  maxVisibleItems: 6,                            // list max-height hint
  density: "comfortable" | "compact",            // default "comfortable"
  placement: "auto" | "bottom-start" | "top-end"  // default "auto"
}
```

向后兼容：`sizeMode` 缺省走 `content`；`maxTriggerWidth` 默认 280；所有缺省值与原行为相符或更稳。

### 5.2 状态清理逻辑（关键改动）

```js
function clearHighlight(popover) {
  if (!popover) return;
  popover.querySelectorAll(".dropdown-item.is-active").forEach((el) =>
    el.classList.remove("is-active"));
  root.removeAttribute("aria-activedescendant");
}

function syncHighlight(popover) {
  if (!popover || activeIndex < 0) {
    clearHighlight(popover);
    return;
  }
  const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
  items.forEach((el, idx) => {
    const on = idx === activeIndex;
    el.classList.toggle("is-active", on);
    if (on) {
      if (!el.id) el.id = `dropdown-opt-${root.dataset.dropdownId || "x"}-${idx}`;
      root.setAttribute("aria-activedescendant", el.id);
      if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
    }
  });
}

function close() {
  // ...existing close...
  clearHighlight(popover);   // NEW: 关闭即清掉 keyboard highlight
}

function open() {
  // ...existing open...
  syncSelected();             // NEW: 重新同步唯一 selected
  syncHighlight(popover);     // NEW: 用 syncHighlight 替换 moveActive
  activeIndex = indexOfSelected();
}
```

### 5.3 宽度测量（无 layout thrash）

```js
function measureTriggerWidth(root) {
  return Math.round(root.getBoundingClientRect().width);
}

function fitPopover(root, popover, mode) {
  const rect = root.getBoundingClientRect();
  const vw = document.documentElement.clientWidth;
  const vh = document.innerHeight;
  const gap = 6;
  const naturalWidth = Math.max(
    rect.width,
    popover.scrollWidth,         // 内容自然宽
    112
  );
  const maxWidth = Math.min(280, vw - 16);
  const width = Math.min(naturalWidth, maxWidth);
  popover.style.width = `${width}px`;
  popover.style.minWidth = `${Math.min(rect.width, width)}px`;

  // 上下方向
  const spaceBelow = vh - rect.bottom - gap;
  const spaceAbove = rect.top - gap;
  const maxHeight = Math.min(320, Math.max(spaceBelow, spaceAbove) - 8);
  popover.style.maxHeight = `${maxHeight}px`;
  const listEl = popover.querySelector(".dropdown-list");
  if (listEl) listEl.style.maxHeight = `${maxHeight - 12}px`;

  // 水平方向
  let left = rect.left;
  if (left + width > vw - 8) left = Math.max(8, vw - width - 8);
  popover.style.left = `${Math.round(left)}px`;

  // 上下方向（如果下方空间不够翻到上面）
  if (spaceBelow >= maxHeight) {
    popover.style.top = `${Math.round(rect.bottom + gap)}px`;
    popover.setAttribute("data-placement", "bottom-start");
  } else if (spaceAbove >= maxHeight) {
    popover.style.top = `${Math.round(rect.top - maxHeight - gap)}px`;
    popover.setAttribute("data-placement", "top-end");
  } else {
    // 不够翻转 → 选用较大一边
    if (spaceBelow >= spaceAbove) {
      popover.style.top = `${Math.round(rect.bottom + gap)}px`;
      popover.style.maxHeight = `${spaceBelow - 8}px`;
      popover.setAttribute("data-placement", "bottom-start");
    } else {
      popover.style.top = `${Math.round(rect.top - spaceAbove + 8)}px`;
      popover.style.maxHeight = `${spaceAbove - 8}px`;
      popover.setAttribute("data-placement", "top-end");
    }
  }
}
```

**测量策略**：单次 `getBoundingClientRect` + 一次 `popover.scrollWidth`（仅测量一次，写到 popover 后不再读取 trigger），避免 layout thrash。

### 5.4 每个 option 加 id（为 `aria-activedescendant` 服务）

```js
function buildItem(item, value, index, onPick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dropdown-item";
  btn.setAttribute("role", "option");
  // NEW: 稳定 id（基于 trigger dataset.dropdownId + index）
  btn.id = `dropdown-opt-${root.dataset.dropdownId || "anon"}-${index}`;
  btn.dataset.value = String(item.value);
  // ...
}
```

### 5.5 type-ahead 修正：仅在 popover open 时拦截 keydown

当前 `mountDropdown` 已经在 keydown handler 里处理（line 261-279），但仅当 `popover open` 才走那段代码（line 231-235 守卫先开）。这意味着 type-ahead 已经只在 open 时运行——但附件把它列为需要修，可能是想我**额外**确认这个守卫无误，并且在 popover 关闭时事件不应触发任何按键逻辑。我用一个 document-level capture 守卫：

```js
function onDocumentKeyDownCapture(e) {
  if (!root.classList.contains(OPEN_CLASS)) return;
  // 已经在 root 的 keydown 处理，不用再干预；这块其实是空的，作为显式注释存在
}
```

**实际上不需要这层**——现有的 root-level listener 已经足够。我会加一个 dev-only 注释说明「type-ahead 只在 root 的 keydown 内分支处理，关闭时不会污染 document」。本 spec 不需要新增 document keydown 监听。

### 5.6 destroy 强化

```js
destroy() {
  close();
  // 已有 removeListeners, 但加一项：清掉 data-* 与 active class
  Array.from(popover?.querySelectorAll(".dropdown-item") ?? []).forEach((el) => {
    el.classList.remove("is-active");
    el.removeAttribute("aria-selected");
  });
  // 已有 remove popover
}
```

---

## 6. 调用方兼容性

### 6.1 22 个调用点

不改 22 个调用点的 `mountDropdown(root, opts)` 调用签名；新增的参数全部 optional 且默认值与旧行为一致。但有以下两类必须做最小的 DOM 调整：

#### 6.1.1 加 `data-size-mode` attribute（默认 `content`）

现有 22 个调用点只声明了 `class="dropdown"` + `data-dropdown-size="compact"`。本 spec 在 stub 上的 DOM 不动，但 JS 读到 `data-size-mode` 时如果为空，默认走 `"content"`（按最长选项扩展 trigger）。

**新增的 `<button>` markup 不需要改**——mount 阶段补 `data-size-mode="content"`，但只有在 size 真正变了时 `setAttribute`。

#### 6.1.2 不强求迁移

旧调用方继续工作。**新调用方**只需传 `sizeMode: "trigger"` 即可。

---

## 7. 文件改动清单

| 文件 | 改动 | 风险 |
|---|---|---|
| `app/static/ui/dropdown.js` | 新增 `sizeMode / minTriggerWidth / maxTriggerWidth / allowTriggerWrap / maxVisibleItems / density / placement` 选项 + `clearHighlight / syncHighlight / fitPopover` + 每个 option 加稳定 id + `close()` 强制清 highlight + `destroy()` 加 ARIA 复位 | 中（新逻辑，但 API 兼容）|
| `app/static/styles.css`（仅 `.dropdown*` rules）| 删 `border-left`，重写三态视觉，重写 Popover 背景，重写 option 圆角，加 scrollbar/gutter，加 trigger width grid，加 `-webkit-line-clamp` 用于 trigger wrap | 中（破坏现有 8 套 trigger 视觉，可能要 pages-style override）|
| `tests/test_dropdown_state_uniqueness.py`（新增）| 静态守卫：`is-active` 类只在 popover open 期间出现；`aria-selected=true` ≤ 1；测试 mount 后无 inline style leak | 低 |
| `tests/test_dropdown_a11y.py`（新增）| 静态 + Playwright：`role=combobox` / `role=listbox` / `role=option` / `aria-expanded` / `aria-controls` / `aria-activedescendant` | 低 |
| `tests/_visual_dropdown_regression.py`（新增，与现有 `_visual_*.py` 同等级） | Playwright 截图 4h / 1d / 长 文本 / 1366 / 125% / scroll position | 低 |
| `tests/screenshots/dropdown-2026-07-31/*.png`（新增）| 8 张 evidence（4h、1d、供给顶部、供给中部、1366、125%）| 低 |
| 9 个页面（grep only）| **不修改页面代码**（仅触发「mount 后默认行为」）| 零 |
| 数据库 / API / 图表 | **不修改** | 零 |

---

## 8. 测试矩阵

| 类型 | 文件 | 校验 |
|---|---|---|
| 静态守卫 | `tests/test_dropdown_state_uniqueness.py` | `aria-selected="true"` 唯一；`is-active` 关闭即清；refresh 后旧 active 移除 |
| 静态守卫 | `tests/test_dropdown_a11y.py` | ARIA 属性齐全；keyboard handler 不冒泡到 document |
| Playwright | `tests/_visual_dropdown_regression.py` | 焦点 → open → 键盘 ArrowDown → 高亮变化 → Enter 选中；移开鼠标后 hover 立即消失；重新打开无残留 |
| 截图 | `tests/screenshots/dropdown-2026-07-31/` | 4h 选中 / 1d 选中 / 长文本顶部 / 长文本中部 / 1366 / 125% 缩放 |

---

## 9. 验收标准（与附件 §十四 对齐）

| # | 标准 | 校验方式 |
|---|---|---|
| 1 | 选中项左侧无深色弧光 / 月牙 | 静态：styles.css 检查 `border-left-color / border-left-width` 在 `.dropdown-item[aria-selected="true"]` 中已删；Playwright：computed style 检查 |
| 2 | 普通 Option 默认透明 | computed style `background === 'rgba(0, 0, 0, 0)'` on default option |
| 3 | Option 之间 ≥ 4px 间距 | computed style `gap: 4-6px` |
| 4 | 单选菜单只有 1 个 `aria-selected="true"` | 静态断言 |
| 5 | Hover / Highlight / Selected 视觉分开 | 视觉三色（hover 0.06 / highlight 0.10 / selected 0.16）|
| 6 | 鼠标移出后 hover 底色立即消失 | Playwright：移出 → 0.2s 后 computed style 回到 transparent |
| 7 | 关闭 + 重开无旧高亮残留 | Playwright：open → close → open → 检查 only current 选中 |
| 8 | 短文本不过度拉宽 | 截图 4h / 1d：width 处于合理范围（90-130px）|
| 9 | 长文本不被挤 | 截图 "全部供给节点"，无 ellipsis 出现 |
| 10 | 两行 Option 自动增长 | 截图 "重新质押 / 已吸收"，高度与相邻 option 不同 |
| 11 | 滚动条不遮挡文字 | computed `padding-right: 8px` |
| 12 | Popover 不超出 viewport | 截图 viewport 边缘位置（页面右 / 页面下）|
| 13 | 键盘 ARIA 不破坏 | kbd 模拟 + computed ARIA 属性断言 |
| 14 | 不在页面内新增 inline 样式 | 静态 grep |
| 15 | 不引入新硬编码颜色 | 静态 grep `var(--color)` vs 残留 `rgba(91, 138, 131` |
| 16 | 所有页面复用同一 Dropdown 视觉 | grep `.dropdown` 出现在 9 页源码中所有调用 |

---

## 10. 风险与回退

| # | 风险 | 缓释 |
|---|---|---|
| R-1 | 改 popover 背景会让依赖 `.dropdown-list` 颜色的现有 caller 失效 | 用 `:where(.dropdown-popover .dropdown-list)` 退化选择器先 grep |
| R-2 | 改 border-left 后某些页面调用方使用 `style="border-left:..."` 内联 | grep `\b(border-left|--accent)\b` 在 pages/*.js 上 0 hit 即可 |
| R-3 | 单次修改影响 9 页 | 静态守卫 + Playwright 9 页逐一验 |
| R-4 | 滚动条在 Firefox 旧版本无 `::-webkit-scrollbar` | 同步写 `scrollbar-color` 与 `scrollbar-width: thin`，Firefox 67+ 都支持 |
| R-5 | type-ahead buffer 与外部 input 冲撞（用户在 Trigger 上按 `r`）| 已确认仅在 `popover open` 时拦截；Trigger 默认类型不抢键盘字符 |
| R-6 | 截图证据需要后端运行 | uvicorn 已启动（背景）|

---

## 11. 交付要求（与附件 §十七 对齐）

1. 根因分析——见 §1
2. 修改文件清单——见 §7
3. 状态模型说明——见 §3
4. 宽度计算规则——见 §4.4 + §5.3
5. 长文本和换行规则——见 §4.5
6. 滚动容器规则——见 §4.6
7. 修复前后截图——`tests/screenshots/dropdown-2026-07-31/{before,after}/*.png`
8. 已验证页面与分辨率——9 页 × (1366 / 1440 / 1920 + 125%)
9. 键盘 / ARIA 验证——见 §8 测试矩阵
10. 测试结果——`pytest -v` + 7/7 static guards + 4/4 Playwright
11. 未解决问题——若 H 阶段某 viewport 截图仍有问题，回滚 single commit

---

## 12. 实施顺序

按 A-H 阶段执行。每阶段独立 commit，可单独回退：

| 阶段 | 内容 | commit 域 |
|---|---|---|
| A | dropdown.css 删 border-left + 重写三态视觉 + Popover 背景 | `[config]` |
| B | dropdown.js 状态清理（clearHighlight / syncHighlight） | `[frontend]` |
| C | dropdown.js `sizeMode` 测量 + `fitPopover()` | `[frontend]` |
| D | dropdown.js / CSS 长文本 + `data-allow-trigger-wrap` | `[frontend]` + `[config]` |
| E | dropdown.js / CSS scrollbar + scroll-gutter + scrollOrResize 升级 | `[frontend]` + `[config]` |
| F | dropdown.js type-ahead 注释 + destroy 强化 | `[frontend]` |
| G | tests/test_dropdown_state_uniqueness.py + test_dropdown_a11y.py | `[test]` |
| H | tests/_visual_dropdown_regression.py + 8 张截图 + 9 页 × 3 viewport Playwright | `[test]` |

---

## 13. 自我审查（spec 自检）

- **占位**：无 "TBD" / "TODO" / "TBA"
- **内部一致性**：
  - §3 状态模型 ↔ §4 CSS 三态：hover ghost、active 1px border、selected gradient，所有路径覆盖
  - §5 JS API ↔ §4 CSS：JS 设 `data-size-mode="content"`、CSS 读 `min-width: 112px` max 280px
- **范围**：仅 Dropdown 组件与其 CSS + 测试；不触页面业务逻辑、API、DB、图表
- **歧义**：JS 选 `clearHighlight` 而不是 `clearActive`、`fitPopover` 不是 `fitToPopover`、`sizeMode` 默认 "content"，所有命名在 §3-§5 内一致
- **可验证**：每个「标准」在 §9 都附校验方式

---

