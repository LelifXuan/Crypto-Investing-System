# Crypto Investing System V1.6 Portable

Windows win-x64 Portable 包自带 Python 运行时，目标机器无需安装 Python。
You do not need to install Python on the target Windows machine.

## 启动

1. 将压缩包解压到可写目录。
2. 双击 `TradingSystemLauncher.exe`，或运行 `start_portable.bat`。
3. 默认访问 `http://127.0.0.1:8000/`。

运行时配置、数据库、衍生品归档和日志全部位于 `runtime/`。升级脚本默认保留 `runtime/config`、`runtime/data` 和用户文件，重建 cache/tmp。

## V1.6 数据与刷新

- BTC 衍生品使用 Deribit、OKX、Bybit、Binance Futures、Bitget、Hyperliquid 公开源。
- 页面读取缓存；刷新在后台任务中执行。
- 无真实数据和 15 分钟内真实缓存时显示 `data_insufficient`，不使用 fixture。
- 高频衍生品历史写入 gzip JSONL 分区，默认归档上限 5 GiB。

## 排障

运行 `start_portable.bat` 并检查：

```text
runtime/logs/portable_console.log
```

完整 V1.6 说明、升级、回滚、数据保留和 Playwright 发布验收流程见源码发布页中的 `README V1.6 Portable.md`。

发布包必须包含 `runtime_env/python/python.exe`、`portable_runtime.lock.json`、`requirements-portable.txt` 和 `release_manifest.json`。
