# 修复 Python datetime UTC 问题

## 问题分析

Python 3.10 没有 `datetime.UTC`，导致以下错误：
```
ImportError: cannot import name 'UTC' from 'datetime'
```

项目中 **38 个文件** 使用了 `datetime.now(UTC)` 或 `from datetime import UTC`。

## 修复方案

### 方案：批量替换

将以下模式替换：

| 旧代码 | 新代码 |
|--------|--------|
| `from datetime import UTC, datetime` | `from datetime import timezone, datetime` |
| `datetime.now(UTC)` | `datetime.now(timezone.utc)` |
| `datetime.utcnow()` | `datetime.now(timezone.utc)` |

## 实施步骤

### 步骤 1：修复关键文件（策略页依赖）

| 文件 | 优先级 |
|------|--------|
| `app/services/strategy/snapshot_builder.py` | P0 (已修复) |
| `app/api/v1/endpoints/strategy.py` | P0 (已修复) |
| `app/services/strategy/market_strategy_signal_engine_v15.py` | P0 (已修复) |
| `app/services/strategy/orchestrator.py` | P1 |
| `app/services/strategy/iteration_engine.py` | P1 |
| `app/services/strategy/review_engine.py` | P1 |

### 步骤 2：修复其他服务文件

| 目录 | 文件数 |
|------|--------|
| `app/services/` | ~15 个 |
| `app/repositories/` | ~2 个 |
| `app/api/` | ~1 个 |
| `app/integrations/` | ~2 个 |
| `app/core/` | ~1 个 |
| `app/workers/` | ~2 个 |

### 步骤 3：验证

运行测试确认修复成功：

```bash
cd trading-system-codex
python -c "from app.services.strategy.market_strategy_signal_engine_v15 import MarketStrategySignalEngine; print('OK')"
python -c "from app.api.v1.endpoints.strategy import router; print('OK')"
```

## 影响范围

- 所有使用 datetime 的服务
- API 端点响应时间不受影响
- 数据库操作不受影响

## 验证步骤

1. 启动服务：`uvicorn app.main:app`
2. 访问策略页：`http://localhost:8000/strategy`
3. 检查浏览器控制台无报错