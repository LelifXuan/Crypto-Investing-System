# 01. 代码审计与工作流优化

## A. 已确认的代码结构问题

### 1) 前端主文件过大且重复定义严重
当前仓库的 `app/static/app.js` 里存在大量重复函数定义，说明文件被多次拼接或多轮生成后未清理。

已扫描到的重复定义：
- `loadMonitoringOverview`：7 次
- `loadMacroCalendar`：7 次
- `ensureMonitoringLayout`：6 次
- `renderIndicatorCharts`：5 次
- `renderIndicatorDashboard`：5 次
- `bindGlobalEvents`：5 次
- `renderLiveMarketPanel`：5 次
- `hydrateLocalModeStatus`：4 次
- `loadIndicators`：4 次
- `calculateIndicators`：4 次
- `renderObservationGroups`：4 次
- `loadAlertCenter`：4 次
- `scheduleIndicatorAutoRefresh`：4 次
- `mountMarketAnalysisTemplate`：4 次

这会带来几个后果：
- 真实生效的是“最后一个同名函数”，可维护性极差
- 很难确认某个页面当前到底使用哪一版逻辑
- 新页面很容易接错到旧函数或半废弃函数
- 任何新增图表页都更容易出现“能渲染外壳，但不出图”

### 2) `bootPage()` 仍然是巨型 if/else 分发
当前页面启动逻辑集中在 `app/static/app.js` 末尾的 `bootPage()` 中。

问题：
- 新页面接入要改多处
- 没有统一的 mount/unmount 生命周期
- 没有页面级错误边界
- 没有 page module registry

### 3) 页面与数据源是“隐式耦合”
以现有指标页为例，图表依赖：
- template 中的 canvas id
- `bootPage()` 分支
- `loadIndicators()`
- `renderIndicatorCharts()`
- API `/api/v1/indicators/*`

如果 Structure 页也沿用这一模式，但缺少任意一环，就会出现：
- 页面壳子存在
- 标题存在
- 图表区域存在
- 但最终没有任何 series 被绘制

## B. 建议工作流

### 推荐的开发顺序
1. **先接页面壳子与 page_id**
2. **再接最小可用 API（哪怕先返回 mock snapshot）**
3. **再接图表渲染器**
4. **最后接复杂识别逻辑**

### 推荐的调试顺序
1. 页面是否真的进入正确 boot 分支
2. API 是否返回非空 candles / overlays / verdict
3. Chart library / plugin 是否加载成功
4. 容器尺寸是否有效
5. 空数据/异常是否被错误吞掉

## C. 推荐的前端重构方向

### 最小重构
把 `app/static/app.js` 拆成：
- `app/static/core/api.js`
- `app/static/core/dom.js`
- `app/static/core/charts.js`
- `app/static/pages/market-analysis.js`
- `app/static/pages/market-events.js`
- `app/static/pages/monitoring.js`
- `app/static/pages/structure.js`
- `app/static/bootstrap.js`

### 页面注册表
改成：
```js
const pageRegistry = {
  dashboard: bootDashboardPage,
  positions: bootPositionsPage,
  reviews: bootReviewsPage,
  'market-analysis': bootMarketAnalysisPage,
  'market-events': bootMarketEventsPage,
  'monitoring-overview': bootMonitoringPage,
  'alert-center': bootAlertCenterPage,
  'macro-calendar': bootMacroCalendarPage,
  imports: bootImportsPage,
  structure: bootStructurePage,
};
```

这样 Structure 页不会再依赖一个巨大的 if/else 被手工拼进去。

## D. 对 Codex 的明确要求
- **不要继续向当前 `app/static/app.js` 追加整块重复代码**
- 优先抽出 `structure page module`
- 对新页面必须加：loading / empty / error 三态
- 对所有图表必须加：初始化日志、API 返回长度日志、resize 触发日志
