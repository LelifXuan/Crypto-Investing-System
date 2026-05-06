# 加密资产投资分析系统 V1.1 发布说明

## 中文说明

Crypto Investing System V1.1 是一个面向加密资产市场分析、技术指标监测、多周期结构判断和投资决策辅助的公开发布版本。

本版本重点强化了系统的可解释性、可复盘性和本地化使用体验，适合用于个人加密资产投研、市场观察、技术分析辅助和策略研究原型验证。

本项目不是自动保证盈利的交易系统，也不构成任何形式的金融建议或投资建议。系统输出应被理解为辅助分析材料，最终投资决策仍需由用户结合自身风险承受能力、仓位管理和独立研究完成。

---

## 版本信息

```text
Version: V1.1
Project: Crypto Investing System
Release Type: Public Release / Portable Release
Recommended Asset Name: Crypto-Investing-System-V1.1-Windows-Portable.zip
```

---

## 本版本定位

V1.1 主要面向以下使用场景：

- 加密资产市场观察；
- 多周期技术分析；
- 趋势、动量、波动率和成交量指标监测；
- 市场结构识别与行情复盘；
- 预警事件整理；
- 置信度评估与交易前辅助判断；
- 本地化 portable 版本运行与测试。

本版本更适合作为“投研与决策辅助终端”，不建议在没有充分回测、风控验证和真实环境测试的情况下直接作为全自动交易系统使用。

---

## 核心功能

### 1. 多周期市场分析

系统支持从短周期、中周期到高周期的市场状态观察，用于辅助判断价格趋势、结构位置和潜在风险。

可用于分析：

- 短期价格行为；
- 中期趋势方向；
- 高周期支撑与阻力；
- 趋势延续或反转条件；
- 不同周期之间的共振与冲突。

---

### 2. 技术指标监测

V1.1 支持多类技术指标的综合分析，不鼓励依赖单一指标直接做交易判断。

指标分析重点包括：

- 趋势类指标；
- 动量类指标；
- 波动率类指标；
- 成交量相关指标；
- 支撑与阻力参考；
- 风险状态辅助判断。

系统设计目标是通过多指标交叉验证提高分析可靠性，同时降低单一指标误判带来的风险。

---

### 3. 市场结构分析

市场结构模块用于帮助用户从价格行为角度理解行情变化，而不仅仅依赖滞后的指标信号。

重点关注：

- 波段高点与波段低点；
- 趋势结构变化；
- 支撑与阻力区域；
- 震荡区间；
- 突破与跌破；
- 潜在趋势延续或反转信号。

该模块适合与技术指标、成交量和多周期分析共同使用。

---

### 4. 预警中心

预警中心用于整理重要市场变化和信号事件，减少人工盯盘压力。

可能包含的预警类型包括：

- 价格波动预警；
- 指标阈值预警；
- 市场结构变化预警；
- 波动率扩张预警；
- 多周期冲突预警；
- 风险状态预警。

预警不等于交易指令。用户应结合趋势、结构、执行条件和风险状态进行综合判断。

---

### 5. 置信度评估框架

V1.1 包含面向投资分析的置信度评估框架，用于整合多类市场证据。

该框架重点评估：

- 指标方向是否一致；
- 当前信号是否受到高周期结构支持；
- 市场处于趋势、震荡还是高风险状态；
- 短周期与长周期是否冲突；
- 当前价格是否适合执行；
- 风险门禁是否允许继续操作。

置信度评分应被理解为决策辅助参考，而不是确定性的市场预测。

---

### 6. 知识百科模块

知识百科模块用于解释系统中涉及的技术术语、指标含义、市场结构概念和分析逻辑。

该模块的目标是提高系统透明度，使用户不仅能够看到结论，也能够理解结论背后的指标依据、结构依据和风险提示。

---

### 7. Portable 本地运行支持

本版本面向 GitHub Release 提供 portable 发布包，便于用户下载后在本地进行测试和使用。

建议用户在使用 portable 版本前阅读随包提供的说明文件，重点确认：

- 启动方式；
- 本地访问地址；
- Python 或运行时依赖要求；
- 配置文件位置；
- 日志文件位置；
- API Key 配置方式；
- 本地缓存与数据库位置。

请勿将真实 API Key、钱包私钥、助记词或交易账户敏感信息提交到公开仓库。

---

## V1.1 重点改进方向

相较于早期版本，V1.1 的重点改进方向包括：

- 更清晰地组织市场分析、结构分析、预警和知识百科模块；
- 强化多周期分析和指标冲突识别；
- 将置信度、执行条件和风险状态区分开；
- 提升知识百科对交易使用场景的解释能力；
- 改善 portable 发布包的 GitHub 分发体验；
- 强化安全提示，避免敏感配置误提交；
- 为后续缓存优化、性能优化和回测验证打基础。

---

## 推荐使用流程

建议用户按照以下流程使用本系统：

1. 选择目标加密资产；
2. 查看高周期趋势与市场结构；
3. 检查中周期动量、波动率和成交量状态；
4. 查看短周期信号和潜在执行条件；
5. 比较不同指标之间的一致性与冲突；
6. 检查预警中心中的重要事件；
7. 查看置信度评估结果；
8. 结合仓位、杠杆、止损和风险状态做最终判断。

---

## 风险与安全说明

使用本系统前，请注意：

- 加密资产市场具有高波动性；
- 技术指标在不同市场状态下可能失效；
- 历史表现不代表未来收益；
- 多周期信号和指标信号经常会出现冲突；
- 高置信度不等于低风险；
- 方向判断正确也可能因为入场位置、滑点、杠杆和仓位管理不当而亏损；
- API Key 和私有配置文件不应提交到 GitHub；
- 市场分析用途建议优先使用只读权限 API。

---

## 已知限制

V1.1 仍属于持续迭代版本，以下方向仍有优化空间：

- 知识百科词条覆盖面仍可继续扩展；
- 部分指标到交易动作之间的解释仍可进一步细化；
- 多周期冲突处理逻辑仍可进一步标准化；
- 指标计算与页面展示之间需要继续保持一致；
- 复杂图表叠加时的渲染性能仍可优化；
- 不同页面之间的数据请求和计算结果可以进一步复用；
- 回测、滑点、手续费、流动性约束和压力测试能力仍需增强；
- portable 版本仍需持续改善启动稳定性、依赖管理和用户文档。

---

## 后续计划

后续版本建议重点推进：

- 扩展知识百科词条覆盖范围；
- 为核心指标增加“交易使用方式”和“冲突处理规则”；
- 增加从信号到交易的完整决策流程说明；
- 优化 K 线、快照和指标计算缓存；
- 减少重复数据请求和重复计算；
- 增加更完整的错误处理和降级状态；
- 增强 portable 版本封装质量；
- 增加回测、滚动验证和风险评估模块；
- 增强风险控制和仓位管理逻辑；
- 提高投资建议输出的可解释性和审慎性。

---

## 下载说明

请在本 Release 页面下方的 Assets 区域下载发布包。

推荐文件名：

```text
Crypto-Investing-System-V1.1-Windows-Portable.zip
```

如果同时提供源码包，可使用：

```text
Crypto-Investing-System-V1.1-Source.zip
```

下载后建议先阅读 README、README_PORTABLE 或随包说明文件，再进行启动和配置。

---

## 升级说明

如果你从旧版本升级到 V1.1，请先备份本地配置和数据。

建议检查：

- API 配置；
- 本地环境变量；
- 本地缓存文件；
- 用户自定义交易对；
- 周期设置；
- 预警配置；
- 数据库和日志目录。

除非已经做好备份，否则不要直接覆盖本地私有配置文件。

---

## 免责声明

本项目仅用于研究、学习和决策辅助。

本项目不提供金融建议、投资建议、交易建议或任何形式的收益保证。

用户需自行承担投资决策、交易执行和风险管理责任。

---

# English Description

Crypto Investing System V1.1 is a public release focused on crypto market analysis, technical indicator monitoring, multi-timeframe structure analysis, alert organization, and investment decision support. This version improves explainability, reviewability, and local portable usage, making it suitable for personal crypto research, market observation, technical analysis assistance, and strategy research prototyping.

This project is not an automated profit-guaranteeing trading system and does not provide financial or investment advice. System outputs should be treated as analytical references only. Final investment decisions should always be made by users based on their own risk tolerance, position sizing, and independent research.

---

## Version Information

```text
Version: V1.1
Project: Crypto Investing System
Release Type: Public Release / Portable Release
Recommended Asset Name: Crypto-Investing-System-V1.1-Windows-Portable.zip
```

---

## Release Positioning

V1.1 is designed for the following use cases:

- crypto market observation;
- multi-timeframe technical analysis;
- monitoring trend, momentum, volatility, and volume indicators;
- market structure recognition and review;
- alert event organization;
- confidence evaluation and pre-trade decision support;
- local portable testing and usage.

This version is better understood as a research and decision-support terminal. It is not recommended to use it as a fully automated trading system without sufficient backtesting, risk validation, and real-world testing.

---

## Core Features

### 1. Multi-Timeframe Market Analysis

The system supports market observation from short-term, medium-term, and higher-timeframe perspectives. It helps users evaluate price trends, structural context, and potential risks.

It can be used to analyze:

- short-term price behavior;
- medium-term trend direction;
- higher-timeframe support and resistance;
- trend continuation or reversal conditions;
- alignment and conflict across timeframes.

---

### 2. Technical Indicator Monitoring

V1.1 supports comprehensive analysis across multiple types of technical indicators. It does not encourage making trading decisions based on a single isolated signal.

Indicator analysis focuses on:

- trend indicators;
- momentum indicators;
- volatility indicators;
- volume-related indicators;
- support and resistance references;
- risk-state evaluation support.

The system aims to improve analytical reliability through multi-indicator confirmation while reducing the risk of misjudgment from isolated indicators.

---

### 3. Market Structure Analysis

The market structure module helps users understand market changes from a price-action perspective rather than relying only on lagging indicator signals.

It focuses on:

- swing highs and swing lows;
- trend structure changes;
- support and resistance zones;
- consolidation ranges;
- breakouts and breakdowns;
- potential continuation or reversal signals.

This module is best used together with technical indicators, volume analysis, and multi-timeframe review.

---

### 4. Alert Center

The alert center organizes important market changes and signal events, helping reduce manual monitoring pressure.

Potential alert types include:

- price movement alerts;
- indicator threshold alerts;
- market structure change alerts;
- volatility expansion alerts;
- multi-timeframe conflict alerts;
- risk-state alerts.

Alerts are not trading instructions. Users should combine alerts with trend, structure, execution quality, and risk-state analysis.

---

### 5. Confidence Evaluation Framework

V1.1 includes a confidence evaluation framework for investment analysis. It combines multiple types of market evidence.

The framework evaluates:

- whether indicators are aligned;
- whether the current signal is supported by higher-timeframe structure;
- whether the market is trending, ranging, or entering a high-risk state;
- whether short-term and long-term signals conflict;
- whether the current price is suitable for execution;
- whether risk gates allow further action.

The confidence score should be interpreted as a decision-support reference, not as a deterministic market prediction.

---

### 6. Knowledge Encyclopedia

The knowledge encyclopedia explains technical terms, indicator meanings, market structure concepts, and analytical logic used by the system.

Its goal is to improve transparency so that users can understand not only final conclusions, but also the indicator evidence, structural evidence, and risk warnings behind them.

---

### 7. Portable Local Usage Support

This version is intended to provide a portable release package through GitHub Releases, making it easier for users to download, test, and run locally.

Before using the portable version, users should read the included documentation and confirm:

- startup method;
- local access address;
- Python or runtime dependency requirements;
- configuration file location;
- log file location;
- API key configuration method;
- local cache and database location.

Do not commit real API keys, wallet private keys, seed phrases, or sensitive trading account information to a public repository.

---

## Key Improvement Directions in V1.1

Compared with earlier versions, V1.1 focuses on:

- clearer organization of market analysis, structure analysis, alerts, and knowledge encyclopedia modules;
- stronger multi-timeframe analysis and signal conflict recognition;
- clearer separation between confidence, execution conditions, and risk state;
- improved explanation quality in the knowledge encyclopedia;
- better GitHub distribution experience for portable packages;
- stronger security reminders to avoid accidental exposure of sensitive configuration;
- preparation for future cache optimization, performance optimization, and backtesting validation.

---

## Recommended Workflow

A recommended workflow is:

1. Select the target crypto asset;
2. Review higher-timeframe trend and market structure;
3. Check medium-timeframe momentum, volatility, and volume conditions;
4. Review short-term signals and potential execution conditions;
5. Compare agreement and conflict between indicators;
6. Check important events in the alert center;
7. Review the confidence evaluation result;
8. Make the final decision based on position size, leverage, stop loss, and risk state.

---

## Risk and Safety Notes

Before using this system, please note:

- crypto markets are highly volatile;
- technical indicators may fail under different market regimes;
- historical performance does not guarantee future returns;
- multi-timeframe and indicator conflicts are common;
- high confidence does not mean low risk;
- a correct directional view can still lose money due to poor entry, slippage, leverage, or position sizing;
- API keys and private configuration files should never be committed to GitHub;
- read-only exchange API permissions are recommended for market analysis.

---

## Known Limitations

V1.1 is still under active iteration. The following areas can be further improved:

- knowledge encyclopedia term coverage can be expanded;
- explanations from indicators to trading actions can be further refined;
- multi-timeframe conflict handling can be more standardized;
- indicator calculation and page display consistency should continue to be maintained;
- rendering performance for complex chart overlays can be improved;
- data requests and computed results can be better reused across pages;
- backtesting, slippage, fees, liquidity constraints, and stress testing need further enhancement;
- portable packaging still needs improvements in startup stability, dependency management, and user documentation.

---

## Future Plans

Future versions may focus on:

- expanding knowledge encyclopedia coverage;
- adding trading playbooks and conflict rules for core indicators;
- adding a complete signal-to-trade decision workflow;
- optimizing K-line, snapshot, and indicator calculation cache;
- reducing repeated data requests and repeated computation;
- adding more complete error handling and fallback states;
- improving portable packaging quality;
- adding backtesting, walk-forward validation, and risk evaluation modules;
- strengthening risk control and position sizing logic;
- improving explainability and caution in investment recommendation outputs.

---

## Download

Download the release package from the Assets section below.

Recommended file name:

```text
Crypto-Investing-System-V1.1-Windows-Portable.zip
```

If a source package is also provided, the following name can be used:

```text
Crypto-Investing-System-V1.1-Source.zip
```

After downloading, please read README, README_PORTABLE, or the included documentation before startup and configuration.

---

## Upgrade Notes

If you are upgrading from an earlier version to V1.1, back up your local configuration and data first.

Recommended checks:

- API configuration;
- local environment variables;
- local cache files;
- user-defined symbols;
- timeframe settings;
- alert configuration;
- database and log directories.

Do not overwrite private local configuration files unless a backup has been created.

---

## Disclaimer

This project is provided for research, education, and decision-support purposes only.

It does not provide financial advice, investment advice, trading advice, or any guarantee of returns.

Users are responsible for their own investment decisions, trade execution, and risk management.
