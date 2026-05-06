# 03. Structure 页面修复方案（Codex 实施规范）

## 目标
修复“形态叠加图”页面空白问题，并把实现纳入现有交易终端的正式主流程。

## 一、必须新增/修改的模块

### 1. Web 路由
文件：`app/web/router.py`

新增：
- `GET /structure-page`
- `page_id="structure"`
- `title="形态结构"`

### 2. 页面导航与模板
文件：`app/templates/page.html`

修改：
- 主导航增加“形态结构”入口
- 新增 `structure-template`

`structure-template` 至少包含：
- instrument tabs 或 instrument selector
- timeframe selector（1h / 4h / 1d / 1w / 30d）
- structure type toggles（Swing / Classic / Profile）
- chart toolbar（刷新、重置、重放）
- chart host（必须有固定最小高度）
- verdict badge
- summary cards
- loading / empty / error 区块

### 3. 前端页面模块
建议新增文件：
- `app/static/pages/structure.js`
- `app/static/core/structure-renderer.js`

若暂时不能拆文件，则至少在 `app/static/app.js` 中新增独立模块区块，并留出后续可抽离边界。

需要新增函数：
- `mountStructureTemplate()`
- `bootStructurePage()`
- `loadStructureSnapshot()`
- `renderStructurePage()`
- `renderStructureChart()`
- `renderStructureSummary()`
- `setStructureLoadingState()`
- `setStructureErrorState()`
- `setStructureEmptyState()`
- `destroyStructureChart()`

### 4. API
新增文件：
- `app/api/v1/endpoints/structure.py`
- `app/schemas/structure.py`
- `app/services/structure_service.py`
- `app/repositories/structure_repository.py`

API 至少提供：
- `GET /api/v1/structure/snapshot?instrument_id=...&timeframe=...`
- `POST /api/v1/structure/recompute`

### 5. 数据库
新增表建议：
- `structure_snapshots`
- `structure_events`
- `structure_overlay_geometries`
- `structure_profile_levels`

### 6. 样式
文件：`app/static/styles.css`

新增：
- structure page layout
- chart host min-height
- overlay legend
- verdict badge states
- empty / error / loading state styles

## 二、推荐 API 输出 schema

```json
{
  "instrument_id": "btc-usdt-perp",
  "timeframe": "4h",
  "as_of": "2026-04-14T06:00:00Z",
  "verdict": {
    "bias": "bullish",
    "label_zh": "利多",
    "confidence": 0.72,
    "summary": "摆动结构保持 HH-HL，Classic 未确认反转，Profile 显示价值区抬升。"
  },
  "candles": [
    {
      "ts_open": "2026-04-01T00:00:00Z",
      "open": 65000,
      "high": 66000,
      "low": 64000,
      "close": 65500,
      "volume": 1234.5
    }
  ],
  "overlays": {
    "swing": [],
    "classic": [],
    "profile": []
  },
  "summary_cards": [
    {
      "key": "swing",
      "title": "摆动结构",
      "value": "HH-HL",
      "tone": "bullish",
      "detail": "最近两个确认摆动高点抬高，低点也抬高。"
    }
  ],
  "debug": {
    "source": "snapshot_cache",
    "latency_ms": 48,
    "candles_count": 320,
    "overlay_counts": {
      "swing": 18,
      "classic": 2,
      "profile": 6
    }
  }
}
```

## 三、前端渲染要求

### 最小成功标准
即使没有真实识别结果，也必须做到：
- 能先画出 K 线或至少 close line
- 能在右侧/上方显示 verdict
- overlays 为空时显示“暂无已确认结构”
- API 错误时显示 error state，而不是空白

### 建议的防空白机制
1. **先渲染基础价格序列**
2. overlays 和 cards 后补
3. 任何异常都切到错误态卡片
4. 在 chart host 中显示 debug corner：
   - page booted
   - api loaded
   - candles count
   - renderer ready

## 四、最容易漏掉的具体 bug 点

### 1. page_id 对不上
HTML body 上如果不是 `data-page="structure"`，则 boot 不会执行。

### 2. template 没 mount
如果 `bootStructurePage()` 没先 mount template，后续 `querySelector` 会拿不到图表容器。

### 3. chart host 宽高为 0
需要：
- 固定 `min-height`
- 页面可见时初始化
- 首次 mount 后 `requestAnimationFrame` 再 render
- `ResizeObserver` 变化时 `chart.resize()`

### 4. API 为空但没有 empty state
`candles.length === 0` 时，不能静默 return。

### 5. library/plugin 没加载
如果采用 Chart.js 以外的库或 financial plugin，必须显式做 library readiness 检查。

### 6. 错误被吞掉
当前仓库已有多处 `.catch(() => {})` 风格。Structure 页禁止这样做，至少要：
- console.error
- 页面 error 卡片
- 状态文本显示失败原因

## 五、建议的分阶段交付

### Phase 1
- route + template + boot + mock snapshot
- 页面能稳定出图

### Phase 2
- 接真实 snapshot API
- 接真实 summary / verdict

### Phase 3
- 接 Swing / Classic / Profile overlays
- 加刷新与缓存

### Phase 4
- 加重放、tooltip、debug panel、性能优化
