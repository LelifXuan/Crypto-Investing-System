# 02. 为什么该页面不显示图表

## 结论
基于当前上传仓库，**最高置信度的问题不是“图表绘制细节错误”，而是“这个页面本身没有被正式接入仓库主流程”**。

## 高置信度证据

### 1) 没有 Structure 页面路由
`app/web/router.py` 里当前只有：
- `/dashboard`
- `/positions-page`
- `/reviews-page`
- `/indicators-page`
- `/market-data-page`
- `/market-events-page`
- `/monitoring-page`
- `/alerts-page`
- `/macro-calendar-page`
- `/imports-page`

**没有 `/structure-page`。**

### 2) 没有 Structure 页面模板
`app/templates/page.html` 里没有：
- `structure-template`
- 结构页的 toolbar
- 结构页 chart canvas
- 结构页信息卡片容器

### 3) 前端 boot 流程没有 Structure 分支
`app/static/app.js` 的 `bootPage()` 里没有：
- `page === "structure"`
- `mountStructureTemplate()`
- `loadStructureSnapshot()`
- `renderStructureChart()`

### 4) 后端 API 没有 Structure 接口
`app/api/router.py` 当前没有 include structure router。
`app/api/v1/endpoints/` 目录下也没有 `structure.py`。

### 5) 数据层没有 Structure 模块
当前仓库中没有：
- `app/services/structure_*.py`
- `app/schemas/structure.py`
- `app/repositories/structure_*.py`
- structure 相关数据库表

SQLite 当前表中也没有 structure snapshots / structure events / profile levels 等表。

## 因此最可能的真实原因

### 根因 1：截图对应的页面代码不在这次上传的仓库里
这是最可能的情况。也就是说：
- 你本地跑的是比这份 archive 更“新”的页面
- 但那部分改动没有一起打包进来
- 所以在当前仓库里无法找到真正的结构页实现

### 根因 2：页面只是静态壳子，没接 boot / API / renderer
如果你本地已经有这个页面，最常见的失败链路是：
- HTML 已经渲染出容器
- 标题、周期、结论 badge 已经能显示
- 但没有执行真正的 chart boot
- 或 chart boot 后拿到空数据
- 或 library/plugin 没加载
- 或异常被吞掉，只剩空白容器

### 根因 3：图表库选择不匹配
当前仓库只明确引了：
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

如果结构页想画：
- K线 / candlestick
- ZigZag 拐点
- Fractal 点
- HH/HL 标签
- 经典图形趋势线
- VP/MP 横向价位分布

那么只靠当前这一层 Chart.js 不够，通常还需要：
- 金融图插件
- 自定义 overlay renderer
- 或直接改用更适合 OHLC + overlay 的图表库

否则常见现象就是：
- 容器有了
- 但 series 根本没有被成功实例化

## 中等置信度的直接触发点
如果你本地已有 structure 页面，重点检查这几项：

1. `document.body.dataset.page` 是否真的是 `structure`
2. `bootPage()` / page registry 是否真的调用了 structure 的 boot 函数
3. chart 容器 id 和 JS 查询 id 是否完全一致
4. API 是否返回：
   - candles.length > 0
   - overlays 非空或至少是空数组
   - verdict 对象存在
5. 初始化时 chart 容器是否已有宽高
6. Chart library/plugin 是否成功加载
7. promise rejection 是否被 `.catch(() => {})` 吞掉

## 对 Codex 的执行结论
Codex 不应直接把问题归因于“样式问题”或“单一 canvas bug”。

正确判断应是：
1. **先补完整 Structure 页面接线链路**
2. **再补最小可用 snapshot API**
3. **再补图表 renderer 与 overlay**
4. **最后排查具体绘制细节**
