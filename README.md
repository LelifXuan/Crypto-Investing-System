# Crypto Investing System V1.4 Portable

本项目是一个本地优先的加密市场研究、宏观监控、形态结构识别与策略辅助系统。

V1.4 Portable 版面向 Windows win-x64 用户，目标是下载、解压后即可运行，不要求用户提前安装 Python 或手动配置依赖。

## 重要声明

本系统只用于市场研究、数据监控、策略复盘和决策辅助，不构成任何投资建议，也不是自动交易执行系统。加密资产波动极高，任何模型、指标、形态识别、宏观评分或 AI 策略输出都可能失效。请结合自身风险承受能力独立判断。

## V1.4 核心更新

V1.4 在 V1.3 true-portable 基础上，重点增强数据可用性和宏观页解释闭环：

1. 新增本机代理自动发现：系统会自动识别 `APP_PROXY_URL`、系统环境变量、Windows 系统代理、WinHTTP 代理和常见本地代理端口。
2. 新增 per-source 代理策略：未检测到代理时，仅 BLS 和 CoinMarketCap 的 live 数据源降级；Gate.io、FRED、BEA、Treasury、A 股 ETF 等数据源继续直连尝试。
3. 新增宏观种子缓存：开发机预先抓取的低频宏观数据可随 Portable 包发布，用户不开 VPN 时仍可看到缓存数据。
4. 新增缓存状态解释：宏观指标会显示 `source / status / latest_date / cache_origin / cache_age_days / is_scored`。
5. 新增缓存评分准入：缓存仍在新鲜度窗口内时可参与评分；缓存过期时只展示，不参与评分。
6. 强化安全策略：API Key、代理密码和完整鉴权 URL 不得进入源码、日志、缓存、前端响应或 healthcheck 返回体。
7. 初步引入A股标的：HALO ETF组合和自由现金流ETF

## 目录结构

```text
runtime_env/                       不可变运行环境，包含嵌入式 Python 和依赖
runtime/                           用户本地运行状态
runtime/config/portable.env         用户本地配置
runtime/config/proxy.detected.json  自动代理检测结果，不含密码
runtime/cache/                      用户运行期缓存
runtime/logs/                       本地日志
app/assets/seed_cache/              随包发布的只读宏观种子缓存
```

升级应用时，通常只需要保留 `runtime/`，替换其它程序文件。

## 启动方式

推荐：

```text
双击 TradingSystemLauncher.exe
```

调试模式：

```text
双击 start_portable.bat
```

启动成功后浏览器会打开本地页面，默认地址通常为：

```text
http://127.0.0.1:8000/strategy-page
```

如果端口被占用，请修改：

```text
runtime/config/portable.env
```

中的：

```env
APP_PORT=8000
```

## 代理自动发现

V1.4 默认启用代理自动发现：

```env
APP_PROXY_MODE=auto
PROXY_AUTO_DETECT_ENABLED=true
```

系统会按以下顺序检测：

1. `APP_PROXY_URL`；
2. `HTTPS_PROXY / HTTP_PROXY / ALL_PROXY`；
3. 上次检测结果 `runtime/config/proxy.detected.json`；
4. Windows 系统代理；
5. WinHTTP 代理；
6. 常见本地代理端口，如 `127.0.0.1:7890`、`127.0.0.1:7897`、`127.0.0.1:10809`。

如果没有开启 VPN 或代理，系统不会整体失败。默认只有以下 live 数据源会受影响：

```text
BLS
CoinMarketCap
```

若存在内置缓存或运行期缓存，宏观页会继续使用缓存数据。

## 宏观缓存机制

宏观数据通常是日度、周度、月度或季度更新，数据量小、时效窗口长。因此 V1.4 支持把开发机刷新过的宏观缓存放入 Portable 包：

```text
app/assets/seed_cache/macro_cache_seed.sqlite
app/assets/seed_cache/macro_cache_seed_manifest.json
```

首次启动时，系统会把 seed cache 合并到：

```text
runtime/cache/macro_api/cache.sqlite
```

读取顺序：

```text
运行期缓存 → 内置种子缓存 → live 数据源 → 缺失/降级状态
```

无 VPN 时，如果 BLS 或 CoinMarketCap live 抓取失败，页面会显示：

```text
系统判定：BLS 当前不可达，系统使用 Portable 内置缓存继续展示 CPI / 就业数据。
```

而不是返回空结果或把缺失数据按 0 分评分。

## 主要页面

- 监控总览：查看关键市场指标、数据状态、缺失输入和风险提示；
- 技术分析：查看 K 线、核心指标、衍生指标与基础趋势判断；
- 形态结构：识别 swing 摆动结构、经典图形、箱体、三角形、楔形、颈线和关键价位；
- 告警中心：聚合结构、指标、背离、风险和事件类告警；
- AI 策略：生成多空策略倾向、入场条件、止损止盈、置信度和缺失输入说明；
- 宏观与事件：展示宏观指标池、数据源状态、缓存状态、宏观事件和事件翻译状态；
- A 股 ETF：查看现金流 ETF 与 HALO ETF 价格；
- 知识百科：整理指标、形态、风控、ETF 和交易术语说明。

## 配置 API Key

真实 API Key 只能写入用户本地配置或系统环境变量，不得写入源码仓库。

目前已经配置好基础的API KEY。

用户本地配置文件：

```text
runtime/config/portable.env
```

可配置：

```env
FRED_API_KEY=
BLS_API_KEY=
BEA_API_KEY=
COINMARKETCAP_API_KEY=
GATEIO_API_KEY=
GATEIO_API_SECRET=
```

没有 API Key 时，系统应显示 `auth_missing` 并尝试缓存回退，不应崩溃。

## 故障排查

优先查看：

```text
runtime/logs/portable_console.log
runtime/logs/portable_startup_diagnostics.log
runtime/config/proxy.detected.json
```

常见情况：

| 现象 | 说明 | 处理 |
|---|---|---|
| BLS / CMC live 不可用 | 未检测到本机代理或网络不可达 | 开启 VPN，或继续使用缓存 |
| 宏观页显示缓存 | live 源不可用但缓存可用 | 正常降级 |
| 缓存过期且无 live | 数据只展示，不参与评分 | 开启代理后刷新 |
| Gate.io 正常但 BLS 失败 | 符合 per-source 代理策略 | 不影响 Crypto 行情 |

## 版本定位

V1.4 的重点是：

```text
数据源可解释
代理可自动发现
缓存可离线使用
缺失不误评分
Portable 包可在不同用户电脑上稳定运行
```
