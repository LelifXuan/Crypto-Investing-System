# 05. 联调与验收清单

## A. 页面接线
- [ ] `/structure-page` 能正常返回页面
- [ ] 主导航能进入结构页
- [ ] `body[data-page="structure"]` 正确设置
- [ ] 结构页模板成功 mount 到 `#page-root`

## B. API
- [ ] `GET /api/v1/structure/snapshot` 返回 200
- [ ] 返回 payload 包含 `candles`
- [ ] 返回 payload 包含 `verdict`
- [ ] overlays 为空时也返回空数组，而不是缺字段
- [ ] API 错误时前端能显示错误态

## C. 图表
- [ ] 首次进入页面时能看到基础价格图
- [ ] 切换 1h / 4h / 1d / 1w / 1M 后图表更新
- [ ] overlays 有数据时能叠加显示
- [ ] overlays 无数据时有明确提示
- [ ] 图表容器 resize 后仍能正常显示

## D. 非空白要求
- [ ] 禁止“标题有了，图表区域纯空白”
- [ ] loading 时显示 skeleton / loading text
- [ ] empty 时显示 empty state
- [ ] error 时显示 error state
- [ ] 任一 promise 异常要 console.error 并显示到页面状态区

## E. 工作流与可维护性
- [ ] 新页面逻辑不要再复制进多个重复函数版本
- [ ] `bootPage()` 或 page registry 中只有一个 structure boot 入口
- [ ] 不允许再次出现同名 structure 函数多次定义
- [ ] 至少保留一组 mock snapshot，用于脱离识别引擎时调试 UI

## F. 建议的调试输出
前端 debug panel 或 console 至少输出：
- `structure:boot:start`
- `structure:template:mounted`
- `structure:api:request`
- `structure:api:success candles=<n> overlays=<...>`
- `structure:renderer:start`
- `structure:renderer:ready`
- `structure:renderer:error`
- `structure:resize`
