# 发布流程

## 前置条件

1. `python scripts/tasks.py check` 全部通过。
2. 工作区改动已按功能域分组，避免混入运行时文件或构建产物。
3. `.env.example` 与 `portable.env.example` 不包含 secret，并覆盖必要配置说明。

## 发布步骤

```powershell
# 1. 质量门禁
python scripts/tasks.py check

# 2. 构建源码发布包
python scripts/tasks.py release-zip

# 3. 构建便携包
python scripts/tasks.py build-portable

# 4. 便携包预检
python scripts/tasks.py portable-preflight
```

## 产物

| 文件 | 说明 |
| --- | --- |
| `dist/trading-system-fastapi-github.zip` | GitHub 源码发布包 |
| `dist/trading-system-fastapi-github.zip.sha256` | 源码包校验文件 |
| `dist/portable_bundle.zip` | Windows 便携包 |
| `dist/portable_bundle.zip.sha256` | 便携包校验文件 |
| `dist/release_manifest.json` | 发布清单 |

## 便携包内容

便携包应包含：

- 嵌入式 Python 运行时：`runtime_env/`
- 应用源码和配置
- `TradingSystemLauncher.exe`
- `start_portable.bat`
- `portable.env.example`
- `README_PORTABLE.md`
- `portable_runtime.lock.json`
- `requirements-portable.txt`
- `release_manifest.json`

## 不应进入发布包的内容

- `runtime_dev/`
- `archive_old/`
- `TradingSystemPortable/` 本地镜像
- `.env`、secret、key、pem
- SQLite 数据库、日志、缓存、pytest/ruff 缓存
- `dist/` 内旧产物

## 提交策略

- 每个功能域独立提交，例如 `[macro]`、`[frontend]`、`[network]`、`[release]`。
- 不提交 `.db`、`.log`、cache、runtime 用户数据。
- 不提交 API key 或 secret。
- 发布前确认 `TradingSystemLauncher.exe` 存在；若无法构建 launcher，必须在发布说明中标注 `start_portable.bat` 为官方 fallback。

## V1.5 发布前验收清单（监控总览改造）

V1.5 在 V1.4.1 Portable 基础上新增监控总览页 `decision_brief`、
多周期冲突矩阵、决策快照持久化与 4 项 P2 风险修复。发布前需要确认：

- [ ] `python scripts/tasks.py check` 21/21 通过
- [ ] `python -m pytest tests/test_terminal_summary_engine.py tests/test_monitoring_dashboard_summary_sources.py tests/test_monitoring_decision_review.py tests/test_monitoring_frontend_static.py -q` 全绿
- [ ] `python -m ruff check .` All checks passed
- [ ] `python scripts/cross_check_and_retry.py` 9/9 PASS
- [ ] `python scripts/audit_user_facing_text.py` 0 failures
- [ ] `python scripts/audit_mojibake.py` 无新增 warn/block（既有 6 个 sanitizer 已知）
- [ ] `node --check app/static/**/*.js` 0 error
- [ ] 监控总览页 UI：终端摘要渲染为三行（市场情况 / 交易指引 / 风险点 / 失效条件）
- [ ] 当 alerts / strategy cache 缺失，`source_alignment.consistency = "degraded"` 且无方向伪造
- [ ] 当 4h/1d/1w 方向冲突，`trading_guidance` 文案降级为"等待确认"
- [ ] `ComputedDatasetCache` 表存在 `dataset_type=monitoring_decision_brief` 的历史快照
- [ ] `GET /monitoring/decision-brief/history` 可返回最近 20 条
- [ ] 每个 row 的 `evidence_strength >= 0.5`，否则 tone=warning 且 summary 前缀"证据强度"
- [ ] dist/ 产物（release-zip / build-portable / portable-preflight）通过且含 V1.5 内容
- [ ] `git tag v1.5` 已打
- [ ] 工作树无 CRLF/LF 混合（`.gitattributes` 已生效）
