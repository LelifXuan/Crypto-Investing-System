# Gold Allocation Page V5 — 对齐技术指标页(分析页)视觉语言

**日期**: 2026-07-31
**状态**: 设计完成,等待用户复核
**范围**: 仅前端 — 视觉对齐 + 修结构性小毛病
**参考标准**: 技术指标页 `market-analysis` (`app/static/pages/analysis.js` + `app/static/styles.css:4240-4388`)

## 0. 背景与目标

黄金配置页目前(`gold_v4.js`,2026-07-22)虽然采用了全局 `.card` 玻璃系统,但仍有数项视觉债务,与分析页对照后明显落伍:

- Hero 是单列 `.hero-card`,与 `.analysis-hero-grid` 的 1.7fr / 0.9fr 双列不一致
- 5 张图表高度不一(320 / 200 / 200 / 180 / 200),参差不齐;主图又独占一行满宽,中段两张卡拉伸后下方留白
- `.gold-workbench` 左 Spot-DCA / 右 Contract Reference 使用 1:1 等宽但 `align-items` 默认,卡高等高未保证
- 多处 `chip-neutral` 默认值(`gold_v4.js:100, 111, 116`)、governance 兜底 `chip-warning`(`gold_v4.js:181-182`),与方向无关,使用者无法判断"系统是否就绪"
- `.gold-tech-tile`(现价 / MA / 回撤 / OI)所有瓦片字体一致,有效数值与"数据积累中"占位视觉权重相同,易扫到主结论受损
- Jinja 模板双 hero(`page.html:44-52` 的 `.gold-initial-shell` + `gold_v4.js:35-46` 的 `.hero-card`),首屏渲染时重叠
- `gold_v4.js` 多处散落的 `style="..."` 内联属性(`gold_v4.js:51, 92, 97, 107-108, 122-128, 137, 143, 156-157`),样式不集中

本次 V5 设计的目的是在不改动任何后端 schema / endpoint / 服务逻辑的前提下,完整对标分析页的玻璃 + eyebrow + chip tone 系统,顺手解决结构性债务。

## 1. 设计原则

- **玻璃面复用**:每张 `.gold-*` 卡都使用分析页 `.card` + `.chart-wrap` + `.mini-card` 三种现成组件,**不新建任何装饰性前缀类**
- **Chip 七档制**:照搬 `analysis.js:394-425` 的 `signalTone`/`signalLabel` + `core/dom.js:306-314` 的 `impactChip()`,覆盖 bull/bear/neutral/warning/event 六档(去掉 emoji)
- **等高栅格**:图表卡用 `grid-auto-rows: 1fr`、workbench 用 `align-items: stretch`、governance 用 `repeat(4, 1fr)` 三种栅格锁死高度
- **类名收敛**:删除 `.gold-v3-*`、`.gold-tech-tile`、`.gold-code-badge`、`.gold-formula-var`;统一使用 `.gold-` + 分析页同构词
- **零内联样式**:JS 不再产出 `style="..."` 属性,所有视觉通过 class 选择器
- **禁止 emoji**:DOM 输出的字符串禁止任何 emoji 码位
- **宽度继承**:不写自有 `max-width`,复用全局 `--shell-width`(`styles.css:43`)

## 2. 页面骨架(5 段,与分析页对齐)

```
┌────────────────────────────────────────────────────────────────────┐
│ ① HERO  eyebrow GOLD ALLOCATION · h1 + 副标 + 刷新按钮              │
├────────────────────────────────────────────────────────────────────┤
│ ② CHART GRID (1 + 2×2,等高)                                        │
│   ┌───────────────────── price (full-width, is-wide) ────────────┐ │
│   ├──────┬──────┬──────┬──────┐                                   │
│   │ RSI  │ BOLL │ VOL  │ DD   │   equal-height sub-cards          │
│   └──────┴──────┴──────┴──────┘                                   │
├──────────────────────────┬─────────────────────────────────────────┤
│ ③ SPOT DCA               │ ④ CONTRACT REFERENCE                    │
│   4 块上中下(top-down)    │   3 块上中下(top-down)                   │
├──────────────────────────┴─────────────────────────────────────────┤
│ ⑤ GOVERNANCE  4 列 mini-card (宏观 · XAUT · 衍生品 · 时间)           │
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 ① Hero

外层 `<section class="gold-hero">`,内嵌 `<article class="card analysis-hero-card">`:

- 内部用 `card-head-inline` 一行:左侧 `eyebrow "GOLD ALLOCATION"` + `h1.gold-page-h1 "黄金配置 Workbench"` + `p.gold-page-sub`,右侧 `<button class="mock-button" id="gold-refresh">刷新 XAUT</button>`
- 副标文案:从 `market_scenarios.active_scenario` 派生成中文,模板:`"宏观判断: ${scenarioLabel(active_scenario)}"`(`STRATEGIC_UNDERWEIGHT` → `低于目标,触发基础定投`,`EXECUTE` 状态追加 `今日基础定投可执行` 等)
- 删除 `page.html:44-52` 的 `.gold-initial-shell`,首屏不渲染双 hero(`page.html` 该注释保留:`<!-- gold-allocation dedicated shell removed in v5 -->`)
- 数据来源:`payload.market_scenarios.active_scenario`、`payload.snapshot.observed_at`、`payload.refresh_state`

### 2.2 ② Chart Grid

```css
.gold-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 22px;
}
.gold-chart-card.is-wide { grid-column: span 2; }
```

每张卡结构:

```html
<article class="card gold-chart-card [is-wide]" id="gold-chart-price">
  <div class="card-head-inline">
    <eyebrow>PRICE &amp; INDICATORS</eyebrow>
    <chip>XAUT 1h</chip>
  </div>
  <div class="chart-wrap"><canvas id="gold-canvas-price"></canvas></div>
</article>
```

5 张卡的稳定 ID(供 chart.js 与将来动效订阅):

| 卡片 | ID | is-wide |
|---|---|---|
| 价格 + 均线 | `gold-chart-price` | ✓ |
| RSI(14) | `gold-chart-rsi` |  |
| Bollinger %B | `gold-chart-bollinger` |  |
| 成交量 | `gold-chart-volume` |  |
| 回撤 | `gold-chart-drawdown` |  |

每张卡的左右 padding=0(图表紧贴卡边),eyebrow 与 chip 走 `.card-head-inline` 横排。Canvas 高:

- price: 320px(`is-wide` 自己撑高,JS 不写死高度)
- 其余 4 张: 等高,目标 240-260px,通过 `grid-auto-rows: 1fr` 自动适配

### 2.3 ③ Spot-DCA(top-down 重排)

`<article class="card gold-workbench-card gold-spot-dca">`,内部改为 4 个从上到下子块:

| 序 | 子块 | 类名 | 内容 |
|---|---|---|---|
| 1 | 权重 | `.gold-weight-row` | `当前 / 目标` 双行标签 + 单条 `weight-bar + weight-fill` + chip `biasChipClass(spotBias)` |
| 2 | 公式 | `.gold-formula-box` | BASR + FIXED 两行,公式项 13px label / 18px value(原 10px 太小,提到与 `.signal-value` 同档) |
| 3 | 加仓门禁 | `.gold-gate-row`(×2 纵向) | `① 60日回撤` + `② 利率/通胀`,chip:passing=bullish-soft / 临界=warning / 未过=bearish-soft |
| 4 | 建议金额 | `.gold-recommend-row` | `gold-recommend-amount` 32px + chip 建议/暂缓/减仓(用 chip-event 表示"暂缓") |

**关键修复**:门禁两行由原先的两列 `gap:8px` flex-row 改为上下两条 `.gold-gate-row`,修复"右侧溢出竖排小字"风险(参 `AGENTS.md:225`)。

### 2.4 ④ Contract Reference(top-down 重排)

`<article class="card gold-workbench-card gold-contract-ref">`:

| 序 | 子块 | 类名 |
|---|---|---|
| 1 | XAUT 现价 banner | `.gold-price-banner` |
| 2 | 技术指标 2 列 mini-grid | `.gold-mini-grid` 4 个 `.mini-card` |
| 3 | 衍生品 2 列 mini-grid | `.gold-mini-grid` 4 个 `.mini-card` |

`.mini-card` 继承分析页样式(`styles.css:2354-2373`),带 `.is-effective / .is-insufficient` 两个变体:

- 有效数值:16px ink / 青绿 border-top / opacity 1
- 占位/缺失:13px muted / dashed border / opacity 0.86

参考 BTC 衍生品 wall-cell 修复(`AGENTS.md:230`)。

### 2.5 ⑤ Governance(4 列 mini-card,完全替换 1×N 灰条)

```html
<section class="gold-governance">
  <p class="eyebrow">数据治理 · SNAPSHOT</p>
  <div class="gold-governance-grid">
    <article class="card gold-mini-card">宏观 · 在线 · <chip-bullish-soft>已就绪</chip-bullish-soft></article>
    <article class="card gold-mini-card">XAUT · 60s 前 · <chip-bullish-soft>新鲜</chip-bullish-soft></article>
    <article class="card gold-mini-card">衍生品 · 暂缺 · <chip-warning>轮询中</chip-warning></article>
    <article class="card gold-mini-card">时间 · 19:55 UTC · <chip-neutral>快照</chip-neutral></article>
  </div>
</section>
```

```css
.gold-governance-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
```

原 `renderGovernance()`(`gold_v4.js:169-186`)整段删除,inline status block 关闭。

## 3. 视觉 Token 与 Chip 调色板

### 3.1 玻璃表面

完全复用分析页 `styles.css:4244-4251`:

```css
background: linear-gradient(180deg, rgba(255,253,249,0.94), rgba(245,240,232,0.78)),
            radial-gradient(circle at top right, rgba(255,255,255,0.26), transparent 30%);
border: 1px solid rgba(196, 188, 168, 0.42);
border-radius: 22px;
box-shadow: inset 0 1px 0 rgba(255,255,255,0.72), 0 12px 32px rgba(70, 60, 40, 0.04);
backdrop-filter: blur(10px);
```

### 3.2 Chip 七档

| domain state | class | label |
|---|---|---|
| 在线 / 60s 内就绪 | `chip-bullish-soft` | 绿 |
| 强确认 / 双源通过 | `chip-bullish` | 强绿 |
| 中性 / 默认 / 待定 | `chip-neutral` | 灰 |
| 警告 / 暂缺 / 临界 | `chip-warning` | 琥珀 |
| 错误 / 服务中断 | `chip-bearish` | 强棕 |
| 缺失 / 数据不足 | `chip-bearish-soft` | 浅棕 |
| 事件 / 临期 / 暂缓 | `chip-event` | 浅蓝紫 |

实现方式:
- `impactChip(kind, tooltip, customLabel)` 已从 `core/dom.js:306` export,可直接复用。
- `signalTone(text)` / `signalLabel(text)` 在 `analysis.js:394-401` 是**模块内私有函数,未 export**。V5 选择**就地把这两段函数复制到 gold_v5.js 内部**(约 30 行 JS),或抽出到 `core/dom.js` 作为新 export (`goldToneFromStatus(statusCode)` + `goldLabelFromStatus(statusCode)`)。在 gold_v5.js 内复制更安全 — 只读、不动共享 core,避免影响分析页(参考 AGENTS.md §六.3 教训)。
- 针对 status code(`EXECUTE` / `READY_FIXED_ADD` / `BLOCKED_*` / `WAIT_DRAWDOWN` / `SETUP_FORMING` / `DATA_DEGRADED`)做一个 `statusTone()` map,与 analysis.js 的文本 tone 解耦。

### 3.3 字号与字重

| role | selector | size / weight |
|---|---|---|
| Page h1 | `.gold-page-h1` | 34px / 600 |
| Section eyebrow | `<p class="eyebrow">` | 12px / 700 letter-spacing .2em |
| Card title | `.gold-card-title` | 18px / 600 |
| Card value | `.gold-card-value` | 22px / 600 |
| Formula value | `.gold-formula-item b` | 18px / 600 |
| Mini-card value | `.gold-mini-card strong` | 16-20px / 600 |
| Body copy | `.gold-card-copy` | 13px / 400 muted |

## 4. 数据流与错误态

### 4.1 数据来源(不改后端,精确到 schema)

`/api/v1/gold/workbench` 返回的 `GoldWorkbenchRead` (`app/schemas/gold_workbench.py:53-67`) 顶层字段:

| 段 | 字段 | 说明 |
|---|---|---|
| ① Hero 副标 | `snapshot.observed_at` + `market_scenarios.active_scenario` | active_scenario 用于一句"宏观 X 评估" |
| ② 5 张图 | `technical_summary.{rsi_14, boll_pct_b, ema20_distance, atr_14}` + candles 通过 `chart_series_or_chart_token.token` 二次拉 `/gold/workbench/{snapshot_id}/charts` | 与现有 V4 相同 |
| ③ spot | `strategic_allocation` (allocation_state/gap_amount/target_min/target_max) + `base_dca` + `dip_add` | 决策 payload(`build_gold_decisions()` at `gold_workbench.py:142`) |
| ④ contract | `technical_summary.{price, ema20_distance}` + `derivatives.{oi_change_4w, funding_rate, cot_net_spec_percentile}` | 现有派生,前端按需取 |
| ⑤ governance | `source_manifest[]` (每项含 `source_key`, `freshness_state`, `error_code`, `age_seconds`, `observed_at`) | 三条记录:`gold_policy` / `gold_spot_quote` / `gold_derivatives`,在 `gold.py:403-460` 构建 |

**所有响应字段不变**,只改前端消费方式与渲染样式。`payload.sources[]` / `payload.macro_bias` 在 schema 不存在,旧 V4 也仅是猜测字段。**V5 必须在 gold_v5.js 中改用 `source_manifest[]` 与 `market_scenarios.active_scenario`**。

### 4.2 冷加载态

- `payload == null` 时,Hero 副标显示 `"宏观信号生成中 — 等待 Workbench 回应"` + chip `chip-event`
- 5 张图卡显示虚线 dashed 边框 + `数据生成中` 占位
- governance 4 张 mini-card 显示 dashed 边框 + 同样占位

### 4.3 失败态

- 4xx/5xx 时,gov 卡片受影响源显示 `chip-bearish` 标签"已断开"
- 其它未受影响卡继续渲染(优先用 LKG)

## 5. 文件变更

| op | path | 摘要 |
|---|---|---|
| 新建 | `app/static/pages/gold_v5.js` | 替换 gold_v4,导出 `{ renderGoldV5, unmount, ready }` |
| 修改 | `app/static/main.js` | 路由 `gold-allocation` → `./pages/gold_v5.js`,dispatcher `renderGoldV5` |
| 修改 | `app/static/styles.css` | 追加 gold-v5 块约 130 行(收在文件末尾) |
| 修改 | `app/templates/page.html` | 删除 `.gold-initial-shell`(line 44-52),保留注释占位 |
| 新建 | `tests/test_gold_v5_frontend_static.py` | 静态守卫(无 emoji、无内联 style、无 `<select`、5 chart ID、4 gov mini-card) |
| 删除 | `app/static/pages/gold_v4.js` | gold_v5 上线后删 |
| 删除 | `app/static/styles.css` 旧 gold 类 | `.gold-v3-*` / `.gold-tech-tile` / `.gold-code-badge` / `.gold-formula-var` / `.gold-signal-card` |

## 6. 样式块大致骨架(给 styles.css 末尾追加)

```css
/* === gold-allocation v5 — visual alignment with analysis page === */
.gold-hero .card-head-inline { gap: 16px; align-items: flex-end; }
.gold-page-h1 { font-size: 34px; font-weight: 600; letter-spacing: -0.04em; color: var(--ink); }
.gold-page-sub { font-size: 14px; color: var(--text-secondary); margin-top: 4px; }

.gold-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 22px;
}
.gold-chart-card { padding: 0; }
.gold-chart-card .chart-wrap {
  padding: 18px 18px 14px;
  border-top: 1px solid rgba(196, 188, 168, 0.32);
}
.gold-chart-card .card-head-inline { padding: 18px 18px 12px; }
.gold-chart-card.is-wide { grid-column: span 2; }

.gold-workbench-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  align-items: stretch;
}
.gold-workbench-card { padding: 24px; display: flex; flex-direction: column; gap: 18px; }
.gold-weight-row { display: flex; align-items: center; gap: 14px; }
.gold-weight-bar { flex: 1; height: 8px; border-radius: 999px; background: rgba(91, 138, 131, 0.18); overflow: hidden; }
.gold-weight-fill { height: 100%; background: var(--accent); transition: width .3s ease; }
.gold-formula-box { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; border-radius: 14px; background: rgba(255,253,249,0.5); border: 1px solid rgba(196, 188, 168, 0.32); }
.gold-formula-item { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.gold-formula-item b { font-size: 18px; font-weight: 600; color: var(--ink); }
.gold-gate-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-top: 1px solid rgba(196, 188, 168, 0.22); }
.gold-gate-row .gold-gate-num { font-weight: 700; color: var(--accent); margin-right: 10px; }
.gold-recommend-row { display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid rgba(196, 188, 168, 0.22); }
.gold-recommend-amount { font-size: 32px; font-weight: 700; color: var(--ink); }

.gold-price-banner { display: flex; align-items: baseline; justify-content: space-between; padding: 14px 18px; border-radius: 14px; background: rgba(91, 138, 131, 0.08); border: 1px solid rgba(91, 138, 131, 0.18); }
.gold-price-value { font-size: 28px; font-weight: 700; }
.gold-mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.gold-mini-card { padding: 12px 14px; border-radius: 12px; background: rgba(255,253,249,0.6); border: 1px solid rgba(196, 188, 168, 0.32); display: flex; flex-direction: column; gap: 4px; }
.gold-mini-card.is-effective strong { font-size: 16px; font-weight: 700; color: var(--ink); border-top: 2px solid var(--accent); padding-top: 4px; }
.gold-mini-card.is-insufficient { opacity: 0.86; border-style: dashed; }
.gold-mini-card.is-insufficient strong { font-size: 13px; color: var(--text-secondary); font-weight: 500; }

.gold-governance { margin-top: 22px; }
.gold-governance-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 12px;
}

/* Cold-load / failure skeleton — same dashed pattern */
.gold-chart-card.is-empty,
.gold-mini-card.is-empty,
.gold-workbench-card.is-empty {
  border-style: dashed;
  background: rgba(245, 240, 232, 0.45);
  color: var(--text-secondary);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}
```

## 7. 静态守卫(`tests/test_gold_v5_frontend_static.py`)

```python
def test_no_emoji_in_gold_v5_js():
    """Static guard: no emoji codepoints in gold_v5.js"""
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    emoji_codepoints = [(0x1F300 + i) for i in range(0x100)] + [... ]
    # simplified: forbid any char > 0x2700 in template literals
    for line in src.splitlines():
        assert not any(0x2700 <= ord(c) <= 0x27BF or 0x1F300 <= ord(c) <= 0x1FAFF
                       for c in line), f"emoji in {line!r}"

def test_no_inline_style_in_gold_v5_js():
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    assert 'style="' not in src, "inline style attribute forbidden"

def test_no_select_literal_in_gold_v5_js():
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    assert "<select" not in src, "no native <select> allowed"

def test_chart_card_ids_present():
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    for card_id in ("gold-chart-price", "gold-chart-rsi", "gold-chart-bollinger",
                    "gold-chart-volume", "gold-chart-drawdown"):
        assert card_id in src, f"missing chart card id {card_id}"

def test_governance_grid_present():
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    assert "gold-governance-grid" in src
    assert "gold-mini-card" in src

def test_no_chip_warning_fallback():
    src = (STATIC_DIR / "pages" / "gold_v5.js").read_text(encoding="utf-8")
    # Old v4 fallback: `chip-warning` was hard-coded for governance; v5 must
    # route through tone mapping.
    assert 'class="status-chip ${healthy ? "chip-bullish-soft" : "chip-warning"}' not in src
```

## 8. 验证门禁(强制,按 `AGENTS.md §六`)

1. `node --check app/static/pages/gold_v5.js`
2. `python -c "import py_compile; py_compile.compile('app/main.py', doraise=True)"` (后端无改动仅 smoke)
3. `python -m pytest tests/test_gold_v5_frontend_static.py -q`
4. `python tests/verify_pages.py --pages gold-allocation --baseline` (写入新基线)
5. `python tests/verify_pages.py` (**全量 9 页** — 因为 main.js / 路由变了)
6. `ruff check app/`
7. 确认 `tests/screenshots/baseline/gold-allocation.png` 与新表盘一致,然后全量 vite serve 测试通过

**任何一项不通过,任务不视为完成**(参 `AGENTS.md §六.4`)。

## 9. 已知风险与后续建议

### 9.1 风险

- **图表高度切换**:从 5 个独立高度改为 1+2×2 后,若现价卡内容(均线 + VWAP)比 4 张子卡都长,可能会拉伸其他卡使整体纵向变长。**缓解**:`is-wide` 价格卡 `grid-column: span 2` 不影响行高,主图可独立高 320px,4 张子卡共享第二行 min-content 高度。
- **`signalTone`/`signalLabel` 未 export**:已在 §3.2 明确 gold_v5.js 内部复制或抽到 `core/dom.js`。**避免**改分析页共享模块。
- **CSS 块追加位置**:若 styles.css 末尾类名与 gold-v4 残留类冲突,需先 grep 删除再 append。
- **Governance 字段已实锤为 `source_manifest[]`**:含 `source_key/freshness_state/error_code/age_seconds/observed_at`,V5 必须直接读此字段,不重塑新数据结构。

### 9.2 不在范围(有意识的)

- 后端 schema / endpoint / service 不动
- 不新增 ATR / IV / 持仓变化率等新图表
- 不动 dropdown / knowledge / strategy 等其他页面
- 不引入新 glass token,完全复用现有 `--surface-glass` 与 `--blur-soft`

### 9.3 后续(可在 V6+ 推)

- 给 chart 卡加 `.card-head-inline` 内嵌 chip,展示该指标当前读取的最新值
- 增加"宏观 → Spot-DCA 因果链"连接线箭头 SVG(只针对 active users)
- 把 governance mini-card 升级为可点击 dropdown,展开看 snapshot 历史

## 10. 与 V4 的关键差异

| 方面 | V4 | V5 |
|---|---|---|
| Hero | 单 `.hero-card` + 单独 button | `analysis-hero-card` 单一卡 + `card-head-inline` |
| Jinja 双 hero | `gold-initial-shell` + `.hero-card` | 只剩 `.hero-card` |
| Chart heights | 5 个不一 320/200/200/180/200 | 1+2×2 grid-auto-rows: 1fr,等高 |
| Workbench 高度 | flex 默认 stretch 不保证 | `align-items: stretch` 强制 |
| Spot-DCA 门禁 | 横向 2 行(易溢出) | 上下 2 行 `.gold-gate-row` |
| Contract-ref tile | `.gold-tech-tile` 等权 | `.mini-card` + `.is-effective / .is-insufficient` |
| Governance | 单条 1×N 灰条 | 4 列 `.gold-mini-card` 玻璃卡 |
| Chip tone | 多处 hard-coded `chip-neutral` / `chip-warning` | 全部走 `impactChip(tone)` 7 档 |
| Emoji | 之前已零容忍 | 静态守卫 `test_no_emoji_in_gold_v5_js` |
| 内联样式 | 11 处 `style="..."` | 0;静态守卫 `test_no_inline_style` |
| 类名 | `.gold-v3-*` 残留 | 全部 `.gold-*`,删除 v3 前缀 |

## 11. 实施顺序(给 writing-plans)

1. CSS 块追加(整块) — 验证 styles.css 通过
2. gold_v5.js 落地(整文件) — 验证 node --check 与静态守卫
3. page.html 删除 `.gold-initial-shell` — 验证 Jinja 渲染
4. main.js 路由切换 + 静态守卫 6/6 通过
5. `verify_pages.py --pages gold-allocation --baseline`
6. `verify_pages.py` 全量 9 页
7. 删除 gold_v4.js 与旧 css 类 — git 一次提交
8. 文档页 commit、tag `gold-page-v5-design`

