# 运维手册

## 环境准备

```powershell
# 1. 创建虚拟环境，放在源码目录外
py -3.14 -m venv ..\runtime_dev\.venv

# 2. 激活虚拟环境
..\runtime_dev\.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -e ".[dev]"
```

## 日常启动

```powershell
# 源码开发模式，默认端口 8002，带热重载
python scripts/tasks.py dev-local

# 便携版启动
.\TradingSystemLauncher.exe
# 或
.\start_portable.bat
```

## 健康检查

| 端点 | 用途 |
| --- | --- |
| `http://127.0.0.1:8002/health` | 服务存活检查 |
| `http://127.0.0.1:8002/health/live` | 进程存活 |
| `http://127.0.0.1:8002/health/ready` | 数据库与依赖就绪 |

```powershell
curl http://127.0.0.1:8002/health
```

## 质量门禁

```powershell
python scripts/tasks.py check
```

该命令会执行 ruff、pytest、compileall、`import app.main`，并对 `app/static/**/*.js` 运行 `node --check`。

## 关键路径

| 路径 | 说明 |
| --- | --- |
| `runtime_dev/source_runtime/data/trading_system.db` | 源码模式 SQLite 数据库 |
| `runtime_dev/source_runtime/cache/` | 本地缓存目录 |
| `runtime_dev/source_runtime/logs/` | 运行日志 |
| `runtime_dev/source_runtime/config/proxy_state.json` | 代理检测状态 |
| `app/monitoring/configs/` | 指标目录、刷新策略、数据源配置 |

## 端口策略

| 模式 | 端口 | 命令 |
| --- | --- | --- |
| 源码开发 | 8002 | `python scripts/tasks.py dev-local` |
| 通用/便携 | 8000 | `python scripts/tasks.py dev` 或 `start_portable.bat` |

## Worker 配置

`WORKER_PROFILE` 控制后台 worker 启动：

| 值 | 启用的 worker |
| --- | --- |
| `none` / `off` / `disabled` | 不启动后台 worker |
| `desktop_light` | `indicator_monitor`、`precompute`、`market_event_translation`、`market_events_feed` |
| `desktop_full` | `desktop_light` 全部 worker，加上 `event_bus`、`market_stream` |

## 常见故障

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 页面白屏 | JS 语法错误 | 查看浏览器 Console，运行 `python scripts/tasks.py check` |
| 数据为 0 或 null | worker 未启动或外部数据源不可达 | 检查 `WORKER_PROFILE`、日志和缓存状态 |
| 市场事件长期不更新 | `market_events_feed` 未运行 | 确认 profile 包含该 worker |
| 翻译不完整 | 翻译 worker 未运行或 provider 限流 | 检查翻译状态和 `translation_retry_after` |
| FRED 数据拉不到 | 网络或代理问题 | 配置代理，确认降级缓存可用 |
| A 股 ETF 无报价 | Eastmoney 访问受限 | 检查直连策略与缓存 |

## 数据库维护

```powershell
# 备份
copy runtime_dev\source_runtime\data\trading_system.db trading_system_backup.db

# SQLite 压缩
sqlite3 runtime_dev\source_runtime\data\trading_system.db "VACUUM;"
```

如需重建本地状态，先备份数据库，再删除 `.db` 文件并重启服务；`AUTO_CREATE_SCHEMA=true` 时会自动创建 schema。
