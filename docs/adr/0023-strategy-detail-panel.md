# ADR 0023：保留完整 Strategy Detail Panel

状态：采用；验收结果见 `docs/ui2-page-migration-acceptance.md` H4。

## 决策

V2.3 采用方案 A：保留现有完整 Detail Panel，不迁移成 Workbench Inspector。
策略详情包含决策、执行计划、证据与约束，是完整研究任务，而非单个指标的局部解释。
本阶段仅注册刷新扫描、聚焦矩阵、聚焦排名、关闭详情四个 page-scoped 命令；
刷新与按钮共用函数，聚焦使用稳定 section ID，卸载销毁 scope 与按钮监听器。

## 当前语义与行为

- 详情身份由 `instrument × trade_timeframe` 确定，并保存在 Strategy 页 `opportunity` URL 参数中。页面恢复时重新核对已发布扫描单元的时效；不可恢复的参数清除。
- 已发布且已计算的格子均可打开详情，包括“无机会”。详情列出该周期的多空评分、上下级周期证据、交易门槛结果与未通过原因；未通过者不展示可执行价位，不进入机会排序。缺数据或过期更新中的格子保持禁用。
- 扫描单元携带 `source_snapshot_key`；详情读取的统一策略快照若已换代，先关闭旧面板并重新读取矩阵，不能把不同代的方向和价位拼在一起。
- 周线、日线、4H 详情分别使用日线、4H、1H 的执行计划；详情的方向、价位和许可必须与所点矩阵单元格的已发布周期决策一致。
- Detail Panel 使用 `role=dialog`、`aria-modal=true` 和可访问标题；窄屏保留同一完整面板，不叠加第二个 drawer。
- 共享浮层优先级：Palette 5000 > Detail/modal/navigation 3000 > responsive Inspector 2000 > desktop Inspector 1500。
- 一次 Escape 仅关闭最上层；Palette 覆盖详情时，Tab 约束于 Palette，关闭后回到详情；滚动锁按所有者释放。
- 详情关闭恢复有效触发点；快速切换候选会关闭旧详情并取消其请求。页面命令不通过按钮文案查找或 window 桥接。
- 不新增最高机会命令，不把排名直接解释为执行授权。

## 后置选项与限制

方案 B（详情内局部证据 Inspector）和方案 C（独立详情路由）仅作为未来选项。
当前提供可恢复的已发布周期判断深链接，不恢复历史交易许可；现有 `inspect` 参数不应用于 Strategy。
未来如引入 B/C，需重新评估浮层层级、权限上下文、LKG、历史快照身份与移动端焦点，不能复用当前矩阵位置充当身份。
