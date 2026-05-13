Crypto Investing System V1.3 

本项目是一个本地优先的加密市场研究、监控与策略辅助系统。

V1.3 Portable 版面向 Windows win-x64 用户，目标是下载、解压后即可运行，不要求用户提前安装 Python 或手动配置依赖。


重要声明
	
	本系统只用于市场研究、数据监控、策略复盘和决策辅助，不构成任何投资建议，也不是自动交易执行系统。
	加密资产波动极高，任何模型、指标、形态识别或 AI 策略输出都可能失效。请结合自身风险承受能力独立判断。


V1.3 的核心目标是实现真正的 Portable 分发：
	
	①内嵌 Windows win-x64 Python 运行环境；
	②内嵌运行所需的 Python 依赖；
	③使用 runtime_env/ 单独存放不可变运行环境，便于检查和升级；
	④使用 runtime/ 单独存放用户运行数据、缓存、日志和本地配置；
	⑤启动脚本默认调用包内 Python，不再依赖系统 PATH 中的 Python；
	⑥增加 Portable 预检逻辑，启动前检查 Python、依赖、端口、数据库和运行目录；
	⑦AI 策略页改为缓存优先与后台刷新，减少日线、周线、月线等长周期策略的重复计算；
	⑧形态结构图进一步拆分 swing 骨架、经典形态边界线、箱体区域、颈线与失效线，降低画线重合对阅读的干扰；
	⑨监控总览页增强缺失输入提示，使 OI、CVD / Delta、depth、spread / slippage 等关键数据的可用状态更清晰。

请在 GitHub Releases 中下载 V1.3 的 Windows Portable 压缩包
使用以下任一入口启动：
	
	①推荐：双击 TradingSystemLauncher.exe；
	②调试模式：双击 start_portable.bat，保留控制台窗口以查看日志。

启动成功后，浏览器会打开本地页面，默认地址通常为：
	
	http://127.0.0.1:8000/strategy-page
	如果端口被占用，请修改 runtime/config/portable.env 中的 APP_PORT 后重启。
	runtime_env/ 是不可变运行环境；runtime/ 是用户本地运行状态。升级应用时，通常只需要保留 runtime/，替换其它程序文件。

Portable 预检

	启动时系统会自动执行预检。预检会检查：
	是否使用包内 runtime_env/python/python.exe；
	Python 主版本是否与 portable_runtime.lock.json 一致；
	fastapi、uvicorn、sqlalchemy、pydantic、jinja2、httpx、aiosqlite 等依赖是否可导入；
	runtime/data/、runtime/logs/、runtime/cache/、runtime/tmp/ 是否可写；
	本地数据库是否可创建或打开；
	端口是否被占用；
	应用是否可以正常导入并完成基础启动。

如启动失败，请优先查看：
	
	runtime/logs/portable_console.log
	runtime/logs/portable_startup_diagnostics.log

当前系统主要包含以下页面：
	
	监控总览：查看关键市场指标、数据状态、缺失输入和风险提示；
	技术分析：查看 K 线、核心指标、衍生指标与基础趋势判断；
	形态结构：识别 swing 摆动结构、经典图形、箱体、三角形、楔形、颈线和关键价位；
	告警中心：聚合结构、指标、背离、风险和事件类告警；
	AI 策略：生成多空策略倾向、入场条件、止损止盈、置信度和缺失输入说明；
	宏观与事件：展示宏观日历、市场事件和事件翻译状态；
	知识百科：整理指标、形态、风控和交易术语说明。

页面读取策略时应优先展示最近一次可用缓存；手动点击“刷新信号”只负责把新任务加入后台队列，不应阻塞页面等待完整计算。

如果页面提示“后台正在准备最新数据”，通常表示缓存尚未生成或已过期。此时可以继续查看上一份策略快照，等待后台刷新完成后再重新读取。
