export const knowledgeCatalogVersion = "v7-v1-1";

export const knowledgePageFilters = [
  { key: "market-analysis", label: "技术指标" },
  { key: "market-structure", label: "形态结构" },
  { key: "alert-center", label: "告警中心" },
  { key: "monitoring-overview", label: "监控总览" },
  { key: "macro-calendar", label: "宏观日历" },
  { key: "market-events", label: "市场事件" },
  { key: "knowledge-base", label: "知识百科" },
  { key: "risk", label: "风险管理" },
];

export const knowledgeLevelFilters = [
  { key: "all", label: "全部等级" },
  { key: "basic", label: "基础" },
  { key: "intermediate", label: "进阶" },
  { key: "advanced", label: "高级" },
];

function term(id, label, options = {}) {
  return {
    id,
    term: label,
    aliases: options.aliases || [],
    category: options.category || "technical",
    family: options.family || "general",
    level: options.level || "intermediate",
    display_mode: options.display_mode || "full",
    importance: options.importance || "useful",
    summary: options.summary || options.definition || "",
    definition: options.definition || options.summary || "",
    why_it_matters: options.why_it_matters || "",
    formula: options.formula || "",
    how_to_use: options.how_to_use || "",
    useful_when: options.useful_when || "",
    thresholds: options.thresholds || [],
    risk_note: options.risk_note || "",
    example: options.example || "",
    page_refs: options.page_refs || ["knowledge-base"],
    related_terms: options.related_terms || [],
    tags: options.tags || [],
  };
}

const technicalItems = [
  term("ohlcv", "K线 / Candle / OHLCV", {
    aliases: ["open", "high", "low", "close", "volume"],
    family: "price",
    level: "basic",
    summary: "一根 K 线压缩了某个周期内的开、高、低、收和成交量。",
    definition: "K 线不是行情本身，而是时间切片。收盘价代表该周期最终被市场接受的位置，影线代表曾经到达但没有稳定接受的位置，成交量说明该周期有多少换手参与。",
    how_to_use: "先确认周期，再看连续 K 线是否抬高或压低，突破是否由收盘确认，长影线是否被快速收回。形态结构页里的突破、假突破、扫流动性都不能只用单根影线判断。",
    risk_note: "单根长影线经常只是扫止损或薄盘口冲击，不能直接等同于趋势反转。",
    page_refs: ["market-analysis", "market-structure", "alert-center"],
    related_terms: ["Timeframe / 周期", "Breakout / 突破"],
    tags: ["price", "core"],
  }),
  term("timeframe", "Timeframe / 周期", {
    aliases: ["1h", "4h", "1d", "1w", "1W", "1M", "30d"],
    family: "timeframe",
    level: "basic",
    summary: "周期决定一根 K 线覆盖的时间，也决定信号用途。",
    definition: "低周期更接近执行噪声，高周期更接近方向背景。1h 常用于入场触发，4h 常用于结构确认，1d/1w 更适合判断主趋势和风险背景。",
    how_to_use: "高周期决定能不能做，低周期决定怎么做。若 1d 偏空而 1h 偏多，低周期反弹不应自动升级为合约多头。",
    page_refs: ["market-analysis", "market-structure", "alert-center"],
    tags: ["timeframe"],
  }),
  term("sma", "SMA 简单移动平均线", {
    aliases: ["SMA20", "MA"],
    family: "trend",
    summary: "SMA 是固定窗口内价格的算术平均，常作为慢速趋势基准。",
    definition: "SMA 对窗口内每个价格给同等权重，因此比 EMA 更慢、更平滑。它适合观察中期成本区和均值回归，不适合捕捉快速启动。",
    formula: "SMA(N) = 最近 N 根收盘价之和 / N。",
    how_to_use: "在横盘市场里，价格围绕 SMA 往返更常见；在趋势市场里，SMA 的斜率和价格是否持续站在均线上方更重要。",
    related_terms: ["EMA 指数移动平均线 / Exponential Moving Average"],
    page_refs: ["market-analysis"],
    tags: ["trend"],
  }),
  term("ema", "EMA 指数移动平均线 / Exponential Moving Average", {
    aliases: ["EMA12", "EMA30", "EMA60", "EMA120", "EMA200"],
    family: "trend",
    level: "basic",
    importance: "core",
    summary: "EMA 更重视近期价格，用来观察趋势成本、排列、发散和纠缠。",
    definition: "EMA 对近期收盘价赋予更高权重，所以比 SMA 更快反映趋势变化。它的核心不是“碰线买卖”，而是看短、中、长期市场成本是否同向排列，以及价格回踩后是否仍被趋势成本承接。",
    formula: "EMA_today = Price_today * 2/(N+1) + EMA_yesterday * (1 - 2/(N+1))。",
    how_to_use: "多头排列指短 EMA > 中 EMA > 长 EMA，例如 EMA30 > EMA60 > EMA120，说明近期成本持续抬高，回踩后更容易恢复上行。空头排列相反，反弹更容易被中长期成本压制。均线发散表示多条 EMA 间距扩大，趋势速度提高，但若价格远离均线且 ATR/NATR 同时上升，追价风险也增加。均线纠缠表示多条 EMA 贴近并反复交叉，方向优势不足，此时突破前的 EMA 信号权重应降低。",
    useful_when: "适合做趋势过滤、回踩质量判断和震荡/趋势切换识别。顺势交易优先找价格回踩 EMA 组后重新收回的机会，震荡环境则降低 EMA 信号权重。",
    thresholds: [
      "多头排列：短 EMA > 中 EMA > 长 EMA，且斜率整体向上。",
      "空头排列：短 EMA < 中 EMA < 长 EMA，且斜率整体向下。",
      "均线发散：EMA 间距持续扩大，趋势加速但追价风险升高。",
      "均线纠缠：EMA 间距收窄并反复交叉，等待收盘突破更重要。",
    ],
    risk_note: "EMA 滞后于价格。强趋势末端常出现价格远离均线但短 EMA 仍向上，不能把多头排列直接当成低风险入场。",
    example: "技术指标页中 EMA30 > EMA60 > EMA120，价格回踩 EMA30 后收回，同时 RSI 守在 50 上方，比单纯看到价格在均线上方更接近多头延续证据。",
    page_refs: ["market-analysis", "monitoring-overview", "alert-center"],
    related_terms: ["Vegas 通道 / Vegas Channel", "ADX 平均趋向指数"],
    tags: ["trend", "core"],
  }),
  term("vegas_channel", "Vegas 通道 / Vegas Channel", {
    aliases: ["Vegas", "Vegas Channel"],
    family: "trend",
    importance: "core",
    summary: "Vegas 通道用多组 EMA 描述趋势快慢成本带。",
    definition: "Vegas 通道把短线动能、快轨和慢轨放在同一张图里。快线反映短线资金是否开始加速，慢轨反映趋势成本带是否仍稳定。",
    how_to_use: "EMA12 上穿通道或快轨，通常表示短线动能开始强于中长期成本；只有价格收盘站上并回踩不破时，才更像有效启动。EMA12 下穿表示短线动能弱化，若价格同时跌回慢轨内部，趋势跟随应降级。快轨上穿慢轨可理解为通道金叉，代表短中期成本重新向上排列；快轨下穿慢轨是通道死叉，代表成本带转弱或进入下行修复。价格在通道上方运行时，回踩通道上沿后收回偏趋势延续；价格反复穿越通道内部时，更接近震荡或过渡。",
    thresholds: [
      "EMA12 上穿并收盘站稳：短线动能转强，但仍需成交量或结构确认。",
      "EMA12 下穿并收不回：短线趋势降级，减少追多。",
      "快慢轨金叉：通道方向转强，适合等待回踩确认。",
      "快慢轨死叉：通道方向转弱，检查原趋势失效条件。",
    ],
    risk_note: "Vegas 不是机械买卖线。新闻冲击和高波动行情里，价格可能瞬间穿越通道又快速收回。",
    page_refs: ["market-analysis"],
    related_terms: ["EMA 指数移动平均线 / Exponential Moving Average"],
    tags: ["trend"],
  }),
  term("rsi", "RSI 相对强弱指数 / Relative Strength Index", {
    aliases: ["RSI14"],
    family: "momentum",
    summary: "RSI 衡量上涨幅度相对下跌幅度的强弱。",
    definition: "RSI 是动量位置指标，不是简单的超买超卖开关。强趋势中 RSI 可以长期位于 50 上方甚至 70 附近，弱趋势中也可以长期低于 50。",
    formula: "RSI = 100 - 100 / (1 + RS)，RS 为平均上涨幅度 / 平均下跌幅度。",
    how_to_use: "重点看 RSI 是否确认价格新高/新低，以及回落时是否守住 50 中轴。价格创新高但 RSI 不创新高，更像趋势质量下降；价格回踩但 RSI 守住 50，则说明多头动能尚未破坏。",
    risk_note: "强趋势里逆着 RSI 高低位抄顶摸底，通常比顺势等待回踩更危险。",
    page_refs: ["market-analysis", "alert-center"],
    related_terms: ["Divergence 背离", "MACD"],
    tags: ["momentum", "core"],
  }),
  term("macd", "MACD", {
    aliases: ["MACD Histogram", "MACD柱"],
    family: "momentum",
    summary: "MACD 用快慢 EMA 的差值衡量趋势动能扩张或收缩。",
    formula: "MACD = EMA12 - EMA26；Signal = EMA9(MACD)；Histogram = MACD - Signal。",
    how_to_use: "价格继续上涨但 MACD 柱缩短，说明上行动能边际减弱；若成交量、CVD 也不确认，背离风险更高。金叉死叉滞后明显，最好与结构突破、回踩或失效条件一起看。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["momentum", "core"],
  }),
  term("bollinger_bands", "BOLL 布林带 / Bollinger Bands", {
    aliases: ["BOLL", "BBANDS", "Percent B", "%B", "Bollinger Bandwidth"],
    family: "volatility",
    summary: "布林带用均线和标准差描述价格相对波动范围的位置。",
    formula: "Middle = SMA20；Upper/Lower = Middle ± 2 * 标准差；%B = (Close-Lower)/(Upper-Lower)。",
    how_to_use: "带宽长期收缩后放量突破，更可能进入波动释放。价格沿上轨运行不等于必须回落，可能只是趋势很强；关键要看带宽、收盘位置和成交量。",
    page_refs: ["market-analysis"],
    tags: ["volatility"],
  }),
  term("percent_b", "Percent B / %B", {
    aliases: ["%B"],
    family: "volatility",
    summary: "%B 显示价格在布林带上下轨之间的位置。",
    formula: "%B = (Close - Lower Band) / (Upper Band - Lower Band)。",
    how_to_use: "%B 接近 1 表示价格靠近上轨，接近 0 表示靠近下轨。趋势强时 %B 可长期偏高；震荡时极端 %B 更适合等待回归确认。",
    page_refs: ["market-analysis"],
    tags: ["volatility"],
  }),
  term("bollinger_bandwidth", "Bollinger Bandwidth / 布林带宽度", {
    aliases: ["BB Width", "bbands_width"],
    family: "volatility",
    summary: "布林带宽度衡量波动压缩和释放。",
    formula: "Bandwidth = (Upper Band - Lower Band) / Middle Band。",
    how_to_use: "带宽收窄说明波动压缩，不代表方向；带宽扩张同时收盘突破关键位，才更接近可交易的波动释放。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volatility"],
  }),
  term("atr", "ATR 平均真实波幅", {
    aliases: ["ATR14"],
    family: "volatility",
    summary: "ATR 衡量真实波动幅度，用于止损距离和仓位缩放。",
    formula: "TR = max(H-L, |H-C_prev|, |L-C_prev|)，ATR 是 TR 的 Wilder 平滑。",
    how_to_use: "ATR 升高时，同样百分比仓位承担的实际价格风险更大。止损距离、试探仓和杠杆倍数都应该随 ATR 调整。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volatility"],
  }),
  term("natr", "NATR 标准化波幅 / Normalized ATR", {
    aliases: ["NATR14", "NATR 14"],
    family: "volatility",
    summary: "NATR 把 ATR 转成百分比，便于比较不同标的的波动风险。",
    formula: "NATR = ATR / Close * 100。",
    how_to_use: "NATR 位于高分位时，应降低杠杆和市价追单；低分位则要警惕压缩后的波动释放。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volatility"],
  }),
  term("adx", "ADX 平均趋向指数", {
    aliases: ["ADX14", "+DI", "-DI", "plus_di", "minus_di"],
    family: "trend",
    summary: "ADX 衡量趋势强度，+DI/-DI 描述方向优势。",
    how_to_use: "ADX 上升且 +DI 高于 -DI，偏多趋势质量更好；ADX 高但 +DI/-DI 频繁交叉，可能只是剧烈震荡。",
    thresholds: ["18 以下趋势弱", "22-30 趋势开始成形", "30 以上趋势强但拥挤风险升高"],
    page_refs: ["market-analysis"],
    tags: ["trend"],
  }),
  term("kdj", "KDJ 随机指标", {
    aliases: ["K", "D", "J", "KDJ J"],
    family: "momentum",
    summary: "KDJ 用价格在近期高低区间中的位置衡量短线动量。",
    how_to_use: "J 值上穿 K/D 常表示短线反弹动量增强；J 值极端高并回落，说明短线过热降温。它更适合执行层确认，不适合作为高周期方向依据。",
    risk_note: "震荡中 KDJ 很敏感，趋势中又容易长期钝化，必须配合结构位置。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["momentum"],
  }),
  term("cci", "CCI 顺势指标 / Commodity Channel Index", {
    aliases: ["CCI20"],
    family: "momentum",
    summary: "CCI 衡量价格偏离典型价格均值的程度。",
    how_to_use: "CCI 上穿 100 说明价格进入强势偏离区，下破 -100 说明弱势偏离。趋势中可用来确认加速，震荡中更适合等待极端后的回归。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["momentum"],
  }),
  term("obv", "OBV 能量潮", {
    aliases: ["On-Balance Volume"],
    family: "volume",
    summary: "OBV 把上涨日成交量累加、下跌日成交量扣除，观察量能是否支持方向。",
    how_to_use: "价格横盘但 OBV 抬升，可能代表买盘吸收卖压；价格新高但 OBV 不跟随，说明突破可能缺少量能确认。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volume"],
  }),
  term("volume_surge_ratio", "Volume Surge Ratio / 成交量放大倍数", {
    aliases: ["volume surge", "volume ratio"],
    family: "volume",
    summary: "成交量放大倍数比较当前成交量和近期均量。",
    formula: "Volume Surge Ratio = 当前成交量 / 近期平均成交量。",
    how_to_use: "突破伴随放量更可信；高位放量但价格推进变慢，可能是派发或换手加剧。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volume"],
  }),
  term("divergence", "Divergence 背离", {
    aliases: ["背离"],
    category: "alert",
    family: "risk",
    summary: "价格与动能或量能不同步，提示趋势质量下降。",
    definition: "背离不是反向开仓信号，而是趋势效率下降的证据。有效背离至少要确认价格收盘形成新高/新低，指标没有同步确认，随后结构出现收回、破坏或回踩失败。",
    how_to_use: "只有价格和指标背离时，更适合作为风险提醒；若随后关键位失守，才接近可交易信号。",
    page_refs: ["alert-center", "market-analysis"],
    tags: ["alert", "risk"],
  }),
  term("breakout", "Breakout / 突破", {
    aliases: ["False Breakout", "假突破", "突破"],
    family: "structure",
    summary: "有效突破要求收盘离开关键区间，并得到后续行为确认。",
    how_to_use: "至少要求一次收盘突破，再看回踩是否守住，最后看成交量、CVD 或 OI 是否确认。只有 high/low 插针不算高质量突破。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure"],
  }),
];

const structureItems = [
  term("market_structure", "Market Structure / 市场结构", {
    aliases: ["HH", "HL", "LH", "LL", "Swing", "Pivot"],
    family: "swing",
    summary: "用摆动高低点序列判断趋势延续或转弱。",
    definition: "连续 HH/HL 表示买方能不断推高并守住回撤，连续 LH/LL 表示卖方压低反弹并继续打低。",
    how_to_use: "不要只看最后一个点，要看高低点序列是否连续、突破是否收盘确认、回撤是否守住关键 swing。",
    page_refs: ["market-structure"],
    tags: ["structure", "core"],
  }),
  term("swing_high_low", "Swing High / Swing Low / 摆动高低点", {
    aliases: ["Swing High", "Swing Low"],
    family: "swing",
    summary: "摆动高低点是结构判断的基本节点。",
    how_to_use: "高周期 swing 更重要；低周期 swing 常用于入场触发和止损定位。",
    page_refs: ["market-structure"],
    tags: ["structure"],
  }),
  term("pivot_fractal", "Pivot / Fractal / 枢轴与分形", {
    aliases: ["Pivot", "Fractal"],
    family: "swing",
    summary: "枢轴点用局部高低点识别短期转折。",
    how_to_use: "枢轴越靠近高周期关键位，信号价值越高；孤立低周期分形容易产生噪声。",
    page_refs: ["market-structure"],
    tags: ["structure"],
  }),
  term("hh_hl_lh_ll", "HH / HL / LH / LL", {
    aliases: ["Higher High", "Higher Low", "Lower High", "Lower Low"],
    family: "swing",
    summary: "HH/HL 是上升结构，LH/LL 是下降结构。",
    how_to_use: "多头结构失效通常不是没有创新高，而是关键 HL 被有效跌破；空头结构失效则是关键 LH 被有效站回。",
    page_refs: ["market-structure"],
    tags: ["structure"],
  }),
  term("bos_choch", "BOS / Break of Structure 与 CHOCH / Change of Character", {
    aliases: ["BOS", "CHOCH", "Break of Structure", "Change of Character"],
    family: "swing",
    summary: "BOS 偏趋势延续，CHOCH 偏角色切换预警。",
    how_to_use: "BOS 需要收盘突破、回踩不破和量能确认；CHOCH 需要看到原趋势关键位失守，并且反抽无法重新收回。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure", "core"],
  }),
  term("support_resistance", "Support / Resistance / 支撑与阻力", {
    aliases: ["Support", "Resistance"],
    family: "levels",
    summary: "支撑阻力是市场反复出现成交反应的位置。",
    how_to_use: "关键不在于画线精确，而在于价格接近该区间时是否出现收回、放量、CVD 确认或失败。",
    page_refs: ["market-structure", "market-analysis"],
    tags: ["structure"],
  }),
  term("retest", "Retest / 回踩确认", {
    aliases: ["回踩"],
    family: "levels",
    summary: "回踩确认用于验证突破后市场是否接受新价格区。",
    how_to_use: "突破后回踩不破关键位，且成交量没有异常衰竭，才更适合顺势执行。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure"],
  }),
  term("liquidity_sweep", "Liquidity Sweep / 流动性扫单", {
    aliases: ["Sweep", "扫流动性"],
    family: "levels",
    summary: "价格刺穿明显高低点后快速收回，常代表扫止损或诱导成交。",
    how_to_use: "扫高后收回区间偏假突破风险，扫低后收回区间偏假跌破修复；必须用收盘和后续结构确认。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure", "risk"],
  }),
  term("range_consolidation", "Range / Consolidation / 区间整理", {
    aliases: ["Range", "Consolidation"],
    family: "regime",
    summary: "区间整理表示价格在被接受的上下边界内换手。",
    how_to_use: "区间中部不要追，边界附近看拒绝或接受；突破后若快速回到区间，优先当作假突破处理。",
    page_refs: ["market-structure"],
    tags: ["structure"],
  }),
  term("acceptance_rejection", "Acceptance / Rejection / 接受与拒绝", {
    aliases: ["Acceptance", "Rejection"],
    family: "regime",
    summary: "接受表示价格能停留并成交，拒绝表示价格离开后快速收回。",
    how_to_use: "判断突破质量时，接受比刺穿重要；价格在新区间停留越久，突破越可信。",
    page_refs: ["market-structure"],
    tags: ["structure"],
  }),
  term("volume_profile", "Volume Profile / 成交量轮廓", {
    aliases: ["POC", "VAH", "VAL", "Value Area"],
    family: "profile",
    summary: "按价格分布成交量，用来识别 POC、VAH、VAL 和成本迁移。",
    definition: "POC 是成交最密集价格，VAH/VAL 是覆盖主要成交量的价值区上下沿。价格在价值区内代表市场仍接受该区间，离开价值区并得到确认才更像结构迁移。",
    how_to_use: "POC 上移代表市场公平价格抬高，POC 下移代表成本重心下移。价格突破 VAH 后回踩不回区间，偏多头接受；突破后回到区间，说明接受度不足。",
    risk_note: "样本太短或流动性太低会让 POC 跳动很大，不要把 POC 当固定支撑阻力。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["profile"],
  }),
  term("regime", "Regime / 市场状态", {
    aliases: ["trend", "balance", "transition"],
    family: "regime",
    summary: "把市场环境压缩成趋势、平衡或过渡，决定策略权重。",
    how_to_use: "Trend 适合顺势等回踩，Balance 适合等边界，Transition 应降低仓位并等待方向重新确认。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure"],
  }),
];

const alertItems = [
  term("signal_to_trade_pipeline", "Signal-to-Trade Pipeline / 信号到交易流程", {
    aliases: ["信号到交易", "trade pipeline"],
    family: "decision",
    importance: "core",
    summary: "方向信号必须经过状态置信、执行触发、风险门控和仓位许可，才变成交易。",
    definition: "本系统把分析结论拆成五步：方向证据说明市场偏多或偏空；状态置信说明证据是否够完整；盘口执行质量说明能不能以合理成本成交；交易触发说明入场条件是否已经发生；风险与仓位门控决定是否允许现货或合约参与。",
    how_to_use: "看到偏多不等于能开多合约，看到状态置信高也不等于胜率高。只有方向、置信、执行、风险、证据质量和高周期一致性同时达标，合约仓位才允许非零。",
    page_refs: ["alert-center", "risk"],
    related_terms: ["Confidence Label / 置信标签", "Execution Label / 执行标签", "Risk Label / 风险标签"],
    tags: ["decision", "core"],
  }),
  term("chip_structure", "Chip Structure / 筹码结构", {
    aliases: ["accumulation", "distribution", "proxy", "confirmed"],
    family: "chip",
    summary: "用价格位置、量能和微观结构推断吸筹、派发或普通换手。",
    definition: "这里的筹码结构不是链上持仓，也不是交易所真实账户分布，而是把成交密集区、价值区位置、OBV/CVD、OI、资金费率、深度和滑点合成，用来判断卖压是否被吸收、上方是否在派发，或只是区间换手。",
    how_to_use: "缺少 CVD、OI、深度、滑点或资金费率时，只能输出 proxy，不能当成 confirmed。吸筹 confirmed 需要价格承接、主动买盘改善、杠杆没有异常拥挤和执行环境可用。",
    page_refs: ["alert-center"],
    tags: ["chip", "core"],
  }),
  term("evidence_quality", "Evidence Quality / 证据质量", {
    aliases: ["proxy_only", "partially_confirmed", "confirmed"],
    family: "decision",
    summary: "证据质量说明结论是代理判断、部分确认还是完整确认。",
    how_to_use: "proxy_only 适合观察，partially_confirmed 适合小仓验证，confirmed 才能进入正常仓位评估。",
    page_refs: ["alert-center", "risk"],
    tags: ["decision"],
  }),
  term("confidence_label", "Confidence Label / 置信标签", {
    aliases: ["state confidence", "状态置信"],
    family: "decision",
    summary: "置信标签说明状态判断的证据完整度，不是胜率。",
    how_to_use: "状态置信较高但交易触发未完成时，仍应等待；状态置信较高但盘口执行差时，合约仓位仍应为 0。",
    page_refs: ["alert-center"],
    tags: ["decision"],
  }),
  term("execution_label", "Execution Label / 执行标签", {
    aliases: ["execution quality", "盘口执行质量"],
    family: "decision",
    summary: "执行标签说明盘口、滑点和波动是否支持成交，不等于已经触发入场。",
    how_to_use: "盘口执行质量良好只是说明成本可控；交易触发状态仍需独立确认。",
    page_refs: ["alert-center"],
    tags: ["decision"],
  }),
  term("risk_label", "Risk Label / 风险标签", {
    aliases: ["risk gate", "risk off"],
    family: "decision",
    summary: "风险标签优先级高于方向许可。",
    how_to_use: "risk_off、observe_only、wait_confirmation 会压制合约仓位，即使方向偏多也不能绕过。",
    page_refs: ["alert-center", "risk"],
    tags: ["decision"],
  }),
  term("entry_trigger", "Entry Trigger / 入场触发", {
    aliases: ["交易触发"],
    family: "execution",
    summary: "入场触发是从观察信号进入执行信号的最后一步。",
    how_to_use: "常见触发包括回踩不破、收盘重新站回关键位、突破后接受、背离后的结构失效。没有触发时，合约仓位必须保持 0。",
    page_refs: ["alert-center", "risk"],
    tags: ["execution"],
  }),
  term("observe_only", "Observe Only / 仅观察", {
    family: "execution",
    summary: "仅观察表示信号有信息价值，但不允许新增风险敞口。",
    how_to_use: "用于数据缺失、证据 proxy、方向冲突或风险门控未通过的场景。",
    page_refs: ["alert-center"],
    tags: ["execution"],
  }),
  term("wait_confirmation", "Wait Confirmation / 等待确认", {
    family: "execution",
    summary: "等待确认表示方向或状态有苗头，但触发条件还没完成。",
    how_to_use: "可以列出确认条件，但不应把它渲染成“正常参与”。",
    page_refs: ["alert-center"],
    tags: ["execution"],
  }),
  term("funding_rate", "Funding Rate / 资金费率", {
    aliases: ["funding", "Funding Z-Score", "funding_zscore"],
    family: "derivatives",
    summary: "资金费率反映永续合约多空支付关系和拥挤度。",
    definition: "正费率通常表示多头为持仓付费，负费率表示空头付费。它更像杠杆情绪和拥挤度指标，不是单独方向信号。",
    how_to_use: "高正费率叠加价格上涨和 OI 上升，说明多头拥挤但趋势可能仍强；高正费率但价格无法继续上涨，容易出现多头去杠杆。高负费率且价格不再下跌，可能出现空头回补。",
    risk_note: "强趋势中高资金费率可以持续很久，不能只因费率高就逆势做空。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["derivatives"],
  }),
  term("basis_rate", "Basis Rate / 基差率", {
    aliases: ["basis", "Basis Z-Score"],
    family: "derivatives",
    summary: "基差衡量合约价格相对现货或指数价格的升贴水。",
    how_to_use: "正基差扩大常见于杠杆多头拥挤，负基差扩大常见于恐慌或空头拥挤。基差 Z-Score 用来判断当前偏离是否异常。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["derivatives"],
  }),
  term("mark_price", "Mark Price / 标记价", {
    aliases: ["mark"],
    family: "derivatives",
    summary: "标记价是合约风控参考价，影响未实现盈亏和强平风险。",
    how_to_use: "成交价相对标记价偏离过大，说明短期成交可能被流动性冲击扭曲，市价单和杠杆都应降级。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["derivatives"],
  }),
  term("index_price", "Index Price / 指数价", {
    aliases: ["index"],
    family: "derivatives",
    summary: "指数价聚合多个市场，用作合约公允价格锚。",
    how_to_use: "最新成交价、标记价和指数价三者分离时，优先把执行风险提高，而不是把偏离直接当方向信号。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["derivatives"],
  }),
  term("price_deviation", "Price Deviation / 价格偏离", {
    aliases: ["Price-to-Mark Deviation", "Price-to-Index Deviation", "deviation"],
    family: "derivatives",
    summary: "价格偏离衡量最新成交价相对标记价或指数价的偏离程度。",
    how_to_use: "偏离过大时，短线成交质量下降，追价和止损滑点风险上升。",
    page_refs: ["alert-center"],
    tags: ["derivatives"],
  }),
  term("open_interest", "OI / Open Interest / 未平仓量", {
    aliases: ["OI", "OI Change"],
    family: "microstructure",
    summary: "OI 是未平仓合约存量，用来区分新仓推动和平仓释放。",
    how_to_use: "价格上涨且 OI 上升，说明新仓参与增加；价格上涨且 OI 下降，可能是空头回补。价格下跌且 OI 上升，可能是新空或多头被套加剧。",
    risk_note: "OI 本身不告诉多空方向，必须结合价格、CVD 和资金费率。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["microstructure"],
  }),
  term("cvd", "CVD 累计成交量差", {
    aliases: ["Delta", "CVD Delta"],
    family: "microstructure",
    summary: "CVD 累计主动买入与主动卖出成交差。",
    how_to_use: "价格上涨且 CVD 同步上升，说明主动买盘确认；价格上涨但 CVD 横盘或下降，突破质量下降。价格横盘但 CVD 持续上升，可能是吸收卖压。",
    page_refs: ["alert-center"],
    tags: ["microstructure"],
  }),
  term("depth_slippage_spread", "Depth / Slippage / Spread / 深度、滑点与价差", {
    aliases: ["Depth 10bps", "Depth 50bps", "Depth 100bps", "Slippage", "Spread", "liquidity"],
    family: "microstructure",
    summary: "深度、滑点和价差共同衡量执行质量。",
    definition: "盘口深度回答当前价格附近有多少可成交流动性；spread 回答立即买卖要付出多少价差；slippage 回答指定金额吃单后平均成交价会偏离中间价多少。三者描述的是能不能以合理成本执行，不是方向。",
    how_to_use: "10bps 深度代表近端流动性，适合判断小单是否容易成交；50/100bps 深度代表更大冲击下的承接能力。spread 扩大说明立即成交成本升高；买入滑点高说明上方卖盘薄，追多成本高；卖出滑点高说明下方买盘薄，止损可能踩踏。",
    thresholds: ["10bps 深度下降：近端成交质量变差", "50/100bps 深度下降：大单冲击风险升高", "spread 扩大：市价成交成本升高", "单边滑点升高：对应方向追价风险升高"],
    risk_note: "盘口是瞬时快照，新闻和大单期间撤单很快。深度好不代表能承接所有市价冲击。",
    page_refs: ["alert-center", "risk"],
    tags: ["liquidity", "microstructure"],
  }),
  term("stop_loss", "Stop Loss / 止损", {
    family: "risk",
    summary: "止损是交易假设失效的位置，不是随意亏损额度。",
    how_to_use: "止损应放在结构失效点外侧，并结合 ATR/NATR 调整距离。太近容易被噪声扫掉，太远会放大单笔风险。",
    page_refs: ["risk", "alert-center"],
    tags: ["risk"],
  }),
  term("take_profit", "Take Profit / 止盈", {
    family: "risk",
    summary: "止盈用于在目标区或风险收益下降时锁定收益。",
    how_to_use: "可结合 VAH/VAL、前高前低、ATR 倍数或 trailing stop，而不是固定百分比机械退出。",
    page_refs: ["risk"],
    tags: ["risk"],
  }),
  term("position_sizing", "Position Sizing / 仓位 sizing", {
    aliases: ["Risk per Trade", "Max Leverage", "Exposure", "Concentration Risk"],
    family: "risk",
    summary: "仓位 sizing 把信号强度转成实际资金风险。",
    how_to_use: "仓位上限应同时考虑状态置信、交易触发、盘口执行、波动、强平距离和单笔风险。方向再强，也不能绕过风险门控。",
    page_refs: ["alert-center", "risk"],
    tags: ["risk"],
  }),
  term("liquidation_distance", "Liquidation / Liquidation Distance / 强平距离", {
    aliases: ["Liquidation", "强平"],
    family: "risk",
    summary: "强平距离衡量价格离强制平仓还有多远。",
    how_to_use: "高波动或滑点环境下，即使方向正确，过近的强平距离也会让合约仓位不合格。",
    page_refs: ["risk", "alert-center"],
    tags: ["risk"],
  }),
  term("invalidation_level", "Invalidation Level / 失效位", {
    family: "risk",
    summary: "失效位是交易假设被证明错误的位置。",
    how_to_use: "若价格重新回到区间中部，或关键 HL/LH 被收盘破坏，原方向假设应降级或失效。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["risk"],
  }),
  term("risk_reward_ratio", "Risk-Reward Ratio / 风险收益比", {
    aliases: ["RR"],
    family: "risk",
    summary: "风险收益比比较潜在收益和计划亏损。",
    how_to_use: "高胜率但盈亏比太差，长期可能仍不划算；低胜率策略必须有更高盈亏比补偿。",
    page_refs: ["risk"],
    tags: ["risk"],
  }),
];

const macroItems = [
  term("cpi", "CPI / Consumer Price Index / 消费者物价指数", {
    aliases: ["US CPI", "Core CPI", "通胀"],
    family: "inflation",
    summary: "CPI 衡量居民消费价格变化，是利率预期的重要输入。",
    how_to_use: "市场看的是相对预期和分项结构。核心 CPI、核心服务和住房分项若高于预期，通常推高利率预期并压制风险资产；低于预期则可能改善流动性预期。",
    risk_note: "CPI 发布时先看实际值相对预期，再看美债收益率、DXY 和风险资产是否同向确认。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "inflation"],
  }),
  term("nfp", "NFP / Nonfarm Payrolls / 非农就业", {
    aliases: ["Nonfarm Payrolls", "非农"],
    family: "labor",
    summary: "NFP 衡量美国非农新增就业，是增长和工资通胀的重要信号。",
    how_to_use: "强就业叠加强工资，可能推迟降息并压制风险资产；就业转弱但工资也回落，可能改善降息预期。要同时看失业率、劳动参与率和前值修订。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "labor"],
  }),
  term("fomc", "FOMC / Federal Open Market Committee / 美联储议息会议", {
    aliases: ["Fed", "Dot Plot", "Powell"],
    family: "policy",
    summary: "FOMC 决定美国货币政策路径，影响全球流动性和风险偏好。",
    how_to_use: "不要只看是否加息降息。点阵图、声明措辞、通胀评价、就业评价和发布会语气都会改变利率路径预期。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "policy"],
  }),
  term("dxy", "DXY / US Dollar Index / 美元指数", {
    aliases: ["US Dollar Index", "美元指数"],
    family: "fx",
    summary: "DXY 衡量美元相对一篮子主要货币的强弱。",
    how_to_use: "DXY 上升常代表美元流动性收紧或避险需求增强，对 BTC 等风险资产不利；DXY 下行通常改善全球美元流动性背景。",
    risk_note: "DXY 权重偏欧元，不能完整代表所有美元流动性环境。",
    page_refs: ["monitoring-overview", "market-events"],
    tags: ["macro", "fx"],
  }),
  term("us10y", "US10Y / 美国10年期国债收益率", {
    aliases: ["US 10Y", "10Y Treasury"],
    family: "rates",
    summary: "US10Y 是长期无风险利率和贴现率的重要代理。",
    how_to_use: "US10Y 上行会提高风险资产估值折现压力；若由增长强推动，影响可能较温和，若由通胀或期限溢价推动，风险资产压力更大。",
    page_refs: ["monitoring-overview", "macro-calendar"],
    tags: ["macro", "rates"],
  }),
  term("us2y", "US2Y / 美国2年期国债收益率", {
    aliases: ["US 2Y"],
    family: "rates",
    summary: "US2Y 更敏感地反映近期政策利率预期。",
    how_to_use: "US2Y 快速上行通常意味着市场重新定价更鹰派的联储路径。",
    page_refs: ["monitoring-overview", "macro-calendar"],
    tags: ["macro", "rates"],
  }),
  term("ten_two_spread", "10Y-2Y Spread / 10年-2年利差", {
    aliases: ["10Y2Y", "2s10s"],
    family: "rates",
    summary: "10Y-2Y 利差反映收益率曲线形态和经济周期预期。",
    how_to_use: "倒挂加深常代表紧缩压力，倒挂修复需要区分是增长改善还是短端降息预期增强。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "rates"],
  }),
  term("real_yield", "Real Yield / 实际收益率", {
    family: "rates",
    summary: "实际收益率约等于名义收益率扣除通胀预期。",
    how_to_use: "实际收益率上升通常压制黄金、BTC 等无现金流资产；下降则改善流动性和估值环境。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "rates"],
  }),
  term("vix", "VIX / 波动率指数", {
    family: "risk",
    summary: "VIX 衡量美股隐含波动率和风险厌恶程度。",
    how_to_use: "VIX 快速上升时，加密市场突破更需要额外确认，杠杆应降级。",
    page_refs: ["monitoring-overview", "market-events"],
    tags: ["macro", "risk"],
  }),
  term("hy_oas", "HY OAS / 高收益债利差", {
    family: "credit",
    summary: "HY OAS 衡量高收益债相对国债的信用风险溢价。",
    how_to_use: "利差扩大说明信用风险上升，通常不利于高 beta 风险资产。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "credit"],
  }),
  term("financial_conditions", "Financial Conditions / 金融条件", {
    family: "liquidity",
    summary: "金融条件综合利率、信用、股市和美元等变量。",
    how_to_use: "金融条件收紧时，技术突破需要更高质量的成交量和结构确认。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "liquidity"],
  }),
  term("tga", "TGA / Treasury General Account / 美国财政部现金账户", {
    family: "liquidity",
    summary: "TGA 变化会影响银行体系准备金和市场流动性。",
    how_to_use: "TGA 快速上升可能吸走流动性，快速下降可能释放流动性。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "liquidity"],
  }),
  term("on_rrp", "ON RRP / 隔夜逆回购", {
    family: "liquidity",
    summary: "ON RRP 是货币市场资金停放在美联储的工具。",
    how_to_use: "ON RRP 下降可能释放资金进入其他短端资产，但需要结合准备金和 TGA 判断。",
    page_refs: ["monitoring-overview"],
    tags: ["macro", "liquidity"],
  }),
  term("ism_pmi", "ISM PMI / 采购经理人指数", {
    family: "growth",
    summary: "ISM PMI 衡量制造业或服务业景气度。",
    how_to_use: "PMI 高于 50 表示扩张，低于 50 表示收缩；价格分项和就业分项会影响通胀与增长预期。",
    page_refs: ["macro-calendar"],
    tags: ["macro", "growth"],
  }),
  term("unemployment_rate", "Unemployment Rate / 失业率", {
    family: "labor",
    summary: "失业率衡量劳动力市场松紧。",
    how_to_use: "失业率上升可能强化降息预期，但若伴随衰退担忧，风险资产未必上涨。",
    page_refs: ["macro-calendar"],
    tags: ["macro", "labor"],
  }),
  term("average_hourly_earnings", "Average Hourly Earnings / 平均时薪", {
    family: "labor",
    summary: "平均时薪是工资通胀压力的重要代理。",
    how_to_use: "工资增速高于预期会提高服务通胀粘性预期，可能推高短端利率。",
    page_refs: ["macro-calendar"],
    tags: ["macro", "labor"],
  }),
  term("risk_on_off", "Risk-On / Risk-Off / 风险偏好", {
    family: "risk",
    summary: "Risk-On 表示资金愿意承担风险，Risk-Off 表示资金转向防御。",
    how_to_use: "加密突破若发生在 Risk-Off 背景下，需要更严格的成交量和结构确认。",
    page_refs: ["monitoring-overview", "market-events", "alert-center"],
    tags: ["macro", "risk"],
  }),
  term("gold", "Gold / 黄金", {
    family: "cross_asset",
    summary: "黄金用于观察实际利率、美元和避险需求。",
    how_to_use: "黄金和 BTC 同涨可能是流动性或货币属性交易，黄金涨而 BTC 跌更可能是避险或风险偏好下降。",
    page_refs: ["monitoring-overview", "market-events"],
    tags: ["macro", "risk"],
  }),
];

const dataQualityItems = [
  term("stale_data", "Stale Data / 数据滞后", {
    aliases: ["stale"],
    family: "quality",
    summary: "数据滞后表示本地快照可用，但已经落后于最新源数据。",
    how_to_use: "可以阅读旧结果，但不要把它当作最新交易依据。页面应显示 stale/updating 状态。",
    page_refs: ["market-analysis", "market-structure", "alert-center"],
    tags: ["quality"],
  }),
  term("cache_state", "Cache State / 缓存状态", {
    aliases: ["fresh", "stale", "missing", "updating", "error"],
    family: "quality",
    summary: "缓存状态说明页面快照当前可用性。",
    how_to_use: "fresh 可直接使用；stale 可先读旧结果并后台更新；missing 显示骨架并排队；error 需要手动重试或查看日志。",
    page_refs: ["knowledge-base"],
    tags: ["quality"],
  }),
  term("warmup", "Warmup / 预热", {
    family: "quality",
    summary: "预热是在用户打开页面前准备常用标的和周期数据。",
    how_to_use: "预热不足时，长周期指标可能先显示 missing，等待后台生成。",
    page_refs: ["knowledge-base"],
    tags: ["quality"],
  }),
  term("lookback", "Lookback / 回看窗口", {
    family: "quality",
    summary: "回看窗口决定指标或结构使用多少历史样本。",
    how_to_use: "窗口太短会让指标不稳定，窗口太长会让结果对最新变化反应迟缓。",
    page_refs: ["market-analysis", "market-structure"],
    tags: ["quality"],
  }),
  term("immature_indicator", "Immature Indicator / 未成熟指标", {
    family: "quality",
    summary: "样本不足时，指标数值尚未稳定。",
    how_to_use: "EMA200、周线结构和长窗口波动率需要足够 K 线，否则只能降级显示。",
    page_refs: ["market-analysis"],
    tags: ["quality"],
  }),
  term("source_availability", "Source Availability / 数据源可用性", {
    family: "quality",
    summary: "数据源可用性说明 Gate.io、宏观或事件源是否能返回数据。",
    how_to_use: "数据源不可用时，页面应读本地快照并显示降级，而不是阻塞渲染。",
    page_refs: ["monitoring-overview"],
    tags: ["quality"],
  }),
  term("data_freshness", "Data Freshness / 数据新鲜度", {
    family: "quality",
    summary: "数据新鲜度衡量最新源数据距离当前时间有多远。",
    how_to_use: "高频页面看分钟级新鲜度，结构和宏观页面可接受更长延迟。",
    page_refs: ["market-analysis", "market-structure"],
    tags: ["quality"],
  }),
  term("mvrv", "MVRV / 市值实现价值比", {
    family: "onchain",
    summary: "MVRV 比较市场市值和链上实现价值，用于观察周期估值。",
    how_to_use: "本系统若未接入链上源，应显示数据不可用，不应伪造确认。",
    page_refs: ["monitoring-overview"],
    tags: ["onchain"],
  }),
  term("sth_mvrv", "STH-MVRV / 短期持有者 MVRV", {
    family: "onchain",
    summary: "短期持有者 MVRV 观察短线持币者盈亏压力。",
    page_refs: ["monitoring-overview"],
    tags: ["onchain"],
  }),
  term("lth_mvrv", "LTH-MVRV / 长期持有者 MVRV", {
    family: "onchain",
    summary: "长期持有者 MVRV 观察长期筹码周期位置。",
    page_refs: ["monitoring-overview"],
    tags: ["onchain"],
  }),
  term("exchange_net_position_change", "Exchange Net Position Change / 交易所净流入变化", {
    family: "onchain",
    summary: "交易所净流入上升可能代表卖压准备，净流出可能代表持有倾向。",
    page_refs: ["monitoring-overview"],
    tags: ["onchain"],
  }),
  term("active_addresses", "Active Addresses / 活跃地址", {
    family: "onchain",
    summary: "活跃地址衡量链上使用活跃度，但不能直接等同于买盘。",
    page_refs: ["monitoring-overview"],
    tags: ["onchain"],
  }),
  term("onchain_data_availability", "On-chain Data Availability / 链上数据可用性", {
    family: "onchain",
    summary: "链上数据不可用时，筹码结构只能依赖市场和微观结构 proxy。",
    page_refs: ["monitoring-overview", "alert-center"],
    tags: ["onchain", "quality"],
  }),
];

export const knowledgeSections = [
  {
    id: "technical",
    title: "技术指标与图表",
    description: "趋势、动量、波动和成交量指标的计算口径与使用方式。",
    items: technicalItems,
  },
  {
    id: "structure",
    title: "形态结构",
    description: "摆动结构、关键位、成交量轮廓和市场状态。",
    items: structureItems,
  },
  {
    id: "alerts",
    title: "告警、筹码与风险执行",
    description: "把信号转换成交易前需要经过的证据、风险和仓位门控。",
    items: alertItems,
  },
  {
    id: "macro",
    title: "宏观与跨市场变量",
    description: "利率、美元、就业、通胀和流动性变量如何影响风险资产。",
    items: macroItems,
  },
  {
    id: "quality",
    title: "数据质量与链上可选项",
    description: "数据新鲜度、样本成熟度、源可用性和链上数据可用性。",
    items: dataQualityItems,
  },
];

function normalizeTerm(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[\s\-_/().,:：，、（）]+/g, "")
    .trim();
}

const lookup = new Map();

function register(item, value) {
  const key = normalizeTerm(value);
  if (key && !lookup.has(key)) lookup.set(key, item);
}

for (const section of knowledgeSections) {
  for (const item of section.items) {
    register(item, item.id);
    register(item, item.term);
    for (const alias of item.aliases || []) register(item, alias);
    for (const tag of item.tags || []) register(item, tag);
  }
}

export function findKnowledgeTerm(termName) {
  const normalized = normalizeTerm(termName);
  if (!normalized) return null;
  if (lookup.has(normalized)) return lookup.get(normalized);
  for (const [key, item] of lookup.entries()) {
    if (key.includes(normalized) || normalized.includes(key)) return item;
  }
  return null;
}

export function searchKnowledge(query, filters = {}) {
  const normalized = normalizeTerm(query);
  return knowledgeSections.flatMap((section) =>
    section.items.filter((item) => {
      if (filters.page && filters.page !== "all" && !(item.page_refs || []).includes(filters.page)) {
        return false;
      }
      if (filters.section && filters.section !== "all" && section.id !== filters.section) {
        return false;
      }
      if (filters.family && filters.family !== "all" && item.family !== filters.family) {
        return false;
      }
      if (filters.level && filters.level !== "all" && item.level !== filters.level) {
        return false;
      }
      if (!normalized) return true;
      return [
        item.id,
        item.term,
        item.summary,
        item.definition,
        item.how_to_use,
        item.formula,
        ...(item.aliases || []),
        ...(item.tags || []),
        ...(item.related_terms || []),
      ]
        .map(normalizeTerm)
        .some((value) => value.includes(normalized));
    }),
  );
}
