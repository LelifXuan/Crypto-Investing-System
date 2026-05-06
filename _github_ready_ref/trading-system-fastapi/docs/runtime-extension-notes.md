# Runtime Extension Notes

这版扩展相对原始 Codex 文档骨架，新增了以下可执行能力：

1. FastAPI app 入口与 lifespan
2. PostgreSQL async engine / session factory
3. Alembic async migration 环境
4. 六大模块的路由、schema、repository、service 分层
5. Docker / Compose 启动链路
6. 单元测试骨架

## 当前实现边界

### 已经跑通的思路
- Fill -> PositionView 重建
- PositionView + MarkPrice -> PnLSnapshot
- Candle -> IndicatorValue
- PnLSnapshot/Fill -> ReviewSummary
- MarketEvent 入库及按 instrument 关联

### 仍建议下一步补强
- 幂等键中间件
- 统一异常模型
- RBAC / JWT
- 事件总线驱动重算
- 时序库分层
- 更细的会计口径与多币种折算
