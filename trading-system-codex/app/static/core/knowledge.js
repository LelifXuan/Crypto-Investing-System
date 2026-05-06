export const knowledgeCatalogVersion = "v6-trading";

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
    definition: "一根 K 线把某个周期内的成交路径压缩成开盘、最高、最低、收盘和成交量。它不是行情本身，只是一个时间桶里的摘要。",
    how_to_use: "先看周期，再看一组 K 线的连续性：收盘价是否不断抬高、下影线是否被收回、放量是否发生在突破或回落位置。",
    risk_note: "单根长影线常常只是流动性扫单，不能直接等同于结构反转。",
    page_refs: ["market-analysis", "market-structure", "alert-center"],
    related_terms: ["Timeframe / 周期", "Breakout / 突破"],
    tags: ["price", "core"],
  }),
  term("timeframe", "Timeframe / 周期", {
    aliases: ["1h", "4h", "1d", "1w", "1W", "1M", "30d"],
    family: "timeframe",
    level: "basic",
    definition: "周期决定每根 K 线覆盖的时间长度，也决定信号用途。1h 更接近执行噪声，1d/1w 更接近方向背景。",
    how_to_use: "短周期用于找入场和止损，高周期用于判断是否应该做这类交易。高低周期冲突时，系统应降低仓位或等待确认。",
    page_refs: ["market-analysis", "market-structure", "alert-center"],
    tags: ["timeframe"],
  }),
  term("ema", "EMA 指数移动平均线 / Exponential Moving Average", {
    aliases: ["EMA30", "EMA60", "EMA120", "EMA200"],
    family: "trend",
    level: "basic",
    definition: "EMA 是对近期价格赋予更高权重的均线。它的重点不是“价格碰到线就买卖”，而是观察短、中、长期平均成本是否同向、是否扩散，以及价格回撤时是否仍能守在趋势成本带上。",
    formula: "EMA_today = Price_today × 2/(N+1) + EMA_yesterday × (1 - 2/(N+1))。",
    how_to_use: "多头排列指短周期 EMA 位于中周期 EMA 上方，中周期又位于长周期上方，例如 EMA30 > EMA60 > EMA120，说明近期成交成本持续抬高，回踩后延续上行的概率更高。空头排列相反，例如 EMA30 < EMA60 < EMA120，说明反弹更容易被中长期成本压制。均线发散表示短中长期 EMA 间距扩大，趋势速度提升；若价格远离均线同时 NATR/ATR 升高，要防追高追空。均线纠缠表示多条 EMA 贴近并反复交叉，方向优势不足，突破前更容易假信号。",
    useful_when: "适合用于趋势过滤、回踩质量判断和横盘/趋势切换识别。顺势交易优先寻找价格回踩 EMA 组后重新收回的机会；震荡环境则应降低 EMA 信号权重。",
    thresholds: [
      "多头排列：短 EMA > 中 EMA > 长 EMA，且三者斜率向上",
      "空头排列：短 EMA < 中 EMA < 长 EMA，且三者斜率向下",
      "发散：EMA 间距持续扩大，趋势加速但追价风险同步增加",
      "纠缠：EMA 间距收窄并反复交叉，方向不清，等待收盘突破更重要",
    ],
    risk_note: "EMA 滞后于价格。强趋势末端常出现价格远离均线但短 EMA 仍向上，不能把均线多头排列直接当成低风险入场；横盘中 EMA 频繁交叉也不代表趋势反复反转。",
    example: "技术指标页中 EMA30 > EMA60 > EMA120 且价格回踩 EMA30 后收回，同时 RSI 守在 50 上方，这比单纯“价格在均线上方”更接近可用的多头延续证据。",
    page_refs: ["market-analysis", "monitoring-overview", "alert-center"],
    related_terms: ["Vegas 通道 / Vegas Channel", "ADX 平均趋向指数"],
    tags: ["trend", "core"],
  }),
  term("vegas_channel", "Vegas 通道 / Vegas Channel", {
    aliases: ["Vegas"],
    family: "trend",
    definition: "Vegas 通道用多组 EMA 描述趋势的快慢成本带。快线通常反映短线动能，慢轨代表更稳定的趋势成本区。它适合判断趋势是否刚开始加速、是否进入成熟段，或是否跌回成本带导致趋势失效。",
    how_to_use: "EMA12 上穿通道或短线快轨，通常表示短线动能开始强于中长期成本，但只有价格收盘站上并回踩不破时，才更像有效启动。EMA12 下穿则表示短线动能弱化，若同时价格跌回慢轨内部，趋势跟随应降级。快轨上穿慢轨可理解为通道金叉，代表短中期成本开始向上重新排列；快轨下穿慢轨是通道死叉，代表成本带转弱或进入下行修复。价格在通道上方运行时，回踩通道上沿后收回偏趋势延续；价格进入通道内部时，说明趋势优势变弱；价格跌破通道下沿且无法收回时，原趋势假设应失效。",
    useful_when: "用于趋势交易的三段判断：启动段看 EMA12/快轨穿越，延续段看价格是否沿通道外侧运行，衰竭段看价格是否跌回通道内部并形成死叉。",
    thresholds: [
      "EMA12 上穿并收盘站稳：短线动能转强，但仍需成交量或结构确认",
      "EMA12 下穿并收不回：短线趋势降级，减少追多或追空",
      "快慢轨金叉：通道方向开始转强，适合等待回踩确认",
      "快慢轨死叉：通道方向转弱，趋势单应检查失效条件",
      "价格在通道内部反复穿越：震荡/过渡，降低通道信号权重",
    ],
    risk_note: "Vegas 通道不是机械买卖线。新闻冲击或高波动行情中，价格可能瞬间穿越通道又快速收回；没有收盘确认和回踩确认时，EMA12 穿越容易变成假启动。",
    example: "若 ETH 4h 中 EMA12 上穿快轨且价格收在 Vegas 通道上方，随后回踩通道上沿不破，同时 MACD 柱重新扩张，这比单独看到 EMA12 上穿更适合作为趋势延续观察点。",
    page_refs: ["market-analysis"],
    related_terms: ["EMA 指数移动平均线 / Exponential Moving Average"],
    tags: ["trend"],
  }),
  term("rsi", "RSI 相对强弱指数 / Relative Strength Index", {
    aliases: ["RSI14"],
    family: "momentum",
    definition: "RSI 衡量上涨幅度相对下跌幅度的强弱，是动量位置指标，不是单纯的超买超卖开关。",
    formula: "RSI = 100 - 100 / (1 + RS)，RS 为平均上涨幅度 / 平均下跌幅度。",
    how_to_use: "强趋势中 RSI 可以长期位于 50 上方甚至 70 附近；真正有用的是价格创新高时 RSI 是否同步创新高，或价格回落时 RSI 是否守住中轴。",
    thresholds: ["50 上方偏多头动量区", "70 以上可能是强趋势，也可能是过热", "30 以下可能是弱势，也可能是超卖反弹区"],
    risk_note: "在单边行情里逆着 RSI 高低位抄顶摸底，通常比顺势等待回踩更危险。",
    page_refs: ["market-analysis", "alert-center"],
    related_terms: ["Divergence 背离", "MACD"],
    tags: ["momentum", "core"],
  }),
  term("macd", "MACD", {
    aliases: ["MACD Histogram", "MACD柱"],
    family: "momentum",
    definition: "MACD 用快慢 EMA 的差值衡量趋势动能。柱状值不是价格涨跌本身，而是动能相对信号线的扩张或收缩。",
    formula: "MACD = EMA12 - EMA26；Signal = EMA9(MACD)；Histogram = MACD - Signal。",
    how_to_use: "价格继续上涨但 MACD 柱缩短，说明上涨仍在发生但边际动能减弱；若同时成交量和 CVD 不确认，背离风险更高。",
    risk_note: "金叉死叉滞后明显，更适合与结构突破或回收一起看。",
    page_refs: ["market-analysis", "alert-center"],
    related_terms: ["RSI 相对强弱指数 / Relative Strength Index", "Divergence 背离"],
    tags: ["momentum", "core"],
  }),
  term("bollinger_bands", "BOLL 布林带 / Bollinger Bands", {
    aliases: ["BOLL", "BBANDS", "Percent B"],
    family: "volatility",
    definition: "布林带用均线和标准差描述价格相对近期波动范围的位置。带宽反映波动收缩或释放，%B 表示价格在上下轨之间的位置。",
    formula: "Middle = SMA20；Upper/Lower = Middle ± 2 × 标准差；%B = (Close-Lower)/(Upper-Lower)。",
    how_to_use: "带宽长期收缩后放量突破，更可能进入波动释放；价格沿上轨运行不等于必须回落，可能是趋势很强。",
    risk_note: "只看触碰上下轨容易误判，关键要看带宽、收盘位置和成交量。",
    page_refs: ["market-analysis"],
    tags: ["volatility"],
  }),
  term("atr", "ATR 平均真实波幅", {
    aliases: ["ATR14"],
    family: "volatility",
    definition: "ATR 衡量真实波动幅度，会考虑当根高低点以及与前收盘的跳变。它更适合描述风险空间，而不是方向。",
    formula: "TR = max(H-L, |H-C_prev|, |L-C_prev|)，ATR 是 TR 的 Wilder 平滑。",
    how_to_use: "止损距离、仓位上限和杠杆强度应随 ATR 调整。ATR 升高时，同样百分比仓位承担的实际价格风险更大。",
    page_refs: ["market-analysis", "alert-center"],
    related_terms: ["NATR 标准化波幅 / Normalized ATR"],
    tags: ["volatility"],
  }),
  term("natr", "NATR 标准化波幅 / Normalized ATR", {
    aliases: ["NATR14", "NATR 14"],
    family: "volatility",
    definition: "NATR 把 ATR 除以价格，转成百分比波动，因此可以比较 BTC、ETH、山寨币之间的相对波动风险。",
    formula: "NATR = ATR / Close × 100。",
    how_to_use: "NATR 位于高分位时，告警中心应更重视波动风险和滑点风险；低分位则要警惕压缩后的波动释放。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volatility"],
  }),
  term("adx", "ADX 平均趋向指数", {
    aliases: ["ADX14", "+DI", "-DI", "plus_di", "minus_di"],
    family: "trend",
    definition: "ADX 衡量趋势强度，+DI 与 -DI 描述上行动能和下行动能的相对优势。ADX 高说明趋势更强，但不直接说明方向。",
    how_to_use: "ADX 上升且 +DI 明显高于 -DI，偏多趋势质量更好；ADX 高但 +DI/-DI 交叉频繁，可能只是剧烈震荡。",
    thresholds: ["18 以下通常趋势弱", "22-30 趋势开始成形", "30 以上趋势强但也更容易出现拥挤"],
    page_refs: ["market-analysis"],
    tags: ["trend"],
  }),
  term("obv", "OBV 能量潮", {
    aliases: ["On-Balance Volume"],
    family: "volume",
    definition: "OBV 把上涨 K 线的成交量累计为正、下跌 K 线的成交量累计为负，尝试观察成交量是否持续支持价格方向。",
    how_to_use: "价格横盘但 OBV 抬升，说明上行动能可能在累积；价格新高但 OBV 不跟随，说明突破可能缺少量能确认。",
    risk_note: "OBV 对交易所成交量质量敏感，异常刷量或单一市场数据会扭曲判断。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["volume"],
  }),
  term("divergence", "Divergence 背离", {
    aliases: ["背离"],
    category: "alert",
    family: "risk",
    definition: "背离是价格方向和动量/量能方向不一致。它提示趋势质量下降，而不是自动反向交易信号。",
    how_to_use: "看背离时至少确认三件事：价格是否真正收盘创新高/新低，指标是否没有同步确认，结构是否出现收回或失效点。",
    risk_note: "强趋势可以连续背离很多次，过早逆势会被趋势延续反复止损。",
    page_refs: ["alert-center", "market-analysis"],
    related_terms: ["RSI 相对强弱指数 / Relative Strength Index", "MACD"],
    tags: ["alert", "risk"],
  }),
  term("breakout", "Breakout / 突破", {
    aliases: ["False Breakout", "突破", "假突破"],
    category: "structure",
    family: "structure",
    definition: "突破是价格用收盘价离开关键区间、摆动高低点或价值区边界。假突破是突破后无法延续并重新收回原区间。",
    how_to_use: "有效突破通常需要收盘突破、后续回踩不破、成交量或 CVD/OI 的同步确认。",
    risk_note: "只用 high/low 插针判断突破，容易把扫止损误判成趋势启动。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure"],
  }),
];

const structureItems = [
  term("market_structure", "Market Structure / 市场结构", {
    aliases: ["HH", "HL", "LH", "LL", "Swing", "Pivot"],
    category: "structure",
    family: "swing",
    definition: "市场结构用一连串摆动高低点描述趋势是否延续。HH/HL 表示买方仍能推高并守住回撤，LH/LL 表示卖方逐步控制反弹。",
    how_to_use: "结构判断不应只看最后一个点，要看高低点序列、突破是否收盘确认，以及回撤是否守住关键位置。",
    page_refs: ["market-structure"],
    tags: ["structure", "core"],
  }),
  term("bos_choch", "BOS / Break of Structure 与 CHOCH / Change of Character", {
    aliases: ["BOS", "CHOCH", "Break of Structure", "Change of Character"],
    category: "structure",
    family: "swing",
    definition: "BOS 是沿原趋势方向打破关键摆动点，CHOCH 是趋势角色可能切换的早期迹象。",
    how_to_use: "BOS 更偏延续，CHOCH 更偏警告。两者都需要收盘确认和后续行为验证，尤其要看是否被快速收回。",
    page_refs: ["market-structure", "alert-center"],
    related_terms: ["Market Structure / 市场结构"],
    tags: ["structure", "core"],
  }),
  term("volume_profile", "Volume Profile / 成交量轮廓", {
    aliases: ["POC", "VAH", "VAL", "Value Area"],
    category: "structure",
    family: "profile",
    definition: "成交量轮廓把一段时间的成交量按价格分布展开，显示市场主要成交成本在哪里，而不是成交发生在什么时间。",
    how_to_use: "POC 是最大成交量价格，常代表短期公平价；VAH/VAL 是价值区边界，价格离开价值区并获得确认时，才更像结构迁移。",
    risk_note: "低流动性或样本过短会让 POC 跳动很大，不能把它当成固定支撑阻力。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["profile"],
  }),
  term("regime", "Regime / 市场状态", {
    aliases: ["trend", "balance", "transition"],
    category: "structure",
    family: "fusion",
    definition: "Regime 是对当前环境的压缩判断：trend 强调方向延续，balance 强调区间均衡，transition 强调多空角色正在切换。",
    how_to_use: "trend 可以顺势等待回踩，balance 更适合等待边界，transition 应降低仓位并等待方向重新确认。",
    page_refs: ["market-structure", "alert-center"],
    tags: ["structure"],
  }),
];

const alertItems = [
  term("chip_structure", "Chip Structure / 筹码结构", {
    aliases: ["accumulation", "distribution", "proxy", "confirmed"],
    category: "alert",
    family: "chip",
    definition: "筹码结构不是链上真实持仓，而是用成交密集区、价格相对价值区的位置、量能变化和微观结构证据推断吸收或派发状态。",
    how_to_use: "价格在价值区下沿反复被接住、OBV/CVD 改善且 OI 没有异常挤压时，更接近吸收；价格高位放量但 CVD/OI 不确认时，更接近派发或诱多。",
    risk_note: "缺少 CVD、OI、深度、滑点或资金费率时，只能输出 proxy，不能当作 confirmed。",
    page_refs: ["alert-center"],
    related_terms: ["Evidence Quality / 证据质量", "CVD 累计成交量差"],
    tags: ["chip", "core"],
  }),
  term("evidence_quality", "Evidence Quality / 证据质量", {
    aliases: ["proxy_only", "partially_confirmed", "confirmed"],
    category: "alert",
    family: "decision",
    definition: "证据质量描述当前结论有多少独立来源确认。OHLCV 只能给代理证据；加入 CVD/OI/depth/funding 后，结论才可能进入部分确认或确认。",
    how_to_use: "proxy_only 适合观察，partially_confirmed 适合小仓验证，confirmed 才能进入正常仓位评估。",
    page_refs: ["alert-center", "risk"],
    tags: ["decision"],
  }),
  term("confidence_label", "Confidence Label / 置信标签", {
    aliases: ["confidence"],
    category: "risk",
    family: "decision",
    definition: "置信标签衡量方向证据是否完整、一致、新鲜。它回答“这个方向判断靠不靠谱”，不是回答“现在能不能进场”。",
    how_to_use: "置信高但执行标签差时，等待回踩或突破确认；置信一般但风险低时，可以只保留观察或试探。",
    page_refs: ["alert-center", "risk"],
    related_terms: ["Execution Label / 执行标签", "Risk Label / 风险标签"],
    tags: ["decision"],
  }),
  term("execution_label", "Execution Label / 执行标签", {
    aliases: ["execution"],
    category: "risk",
    family: "decision",
    definition: "执行标签关注当前价位是否适合行动：是否追高追空、离失效点多远、波动和流动性是否允许成交。",
    how_to_use: "方向正确但执行差，应该等回踩、等重新突破，或缩小仓位。",
    page_refs: ["alert-center", "risk"],
    tags: ["decision"],
  }),
  term("risk_label", "Risk Label / 风险标签", {
    aliases: ["risk", "risk off", "observe only", "wait confirmation"],
    category: "risk",
    family: "decision",
    definition: "风险标签是最终约束层。即使方向和置信较好，只要风险门禁触发，也必须压制仓位或禁止合约建议。",
    how_to_use: "risk_off、observe_only、wait_confirmation 优先级高于方向许可。",
    page_refs: ["alert-center", "risk"],
    tags: ["decision"],
  }),
  term("funding_rate", "Funding Rate / 资金费率", {
    aliases: ["funding"],
    category: "microstructure",
    family: "derivatives",
    definition: "资金费率是永续合约多空双方定期交换的费用，通常用来让合约价格贴近现货/指数价格。它也反映杠杆资金哪一侧更拥挤。",
    how_to_use: "极端正费率说明多头愿意付费持仓，若价格无法继续上涨，容易出现多头踩踏；极端负费率反过来提示空头拥挤。",
    risk_note: "资金费率不是方向信号，趋势强时高资金费率可以持续很久。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["derivatives"],
  }),
  term("mark_price", "Mark Price / 标记价", {
    aliases: ["mark", "标记价", "Index Price", "Basis", "Deviation"],
    category: "microstructure",
    family: "derivatives",
    definition: "标记价是交易所用于合约风控和未实现盈亏计算的参考价，通常综合指数价格和资金费率基础。它比最新成交价更能代表强平和保证金风险。",
    how_to_use: "最新成交价偏离标记价/指数价过大时，说明短期成交可能被流动性或杠杆冲击扭曲，执行标签应降级。",
    page_refs: ["market-analysis", "alert-center"],
    tags: ["derivatives"],
  }),
  term("open_interest", "OI / Open Interest / 未平仓量", {
    aliases: ["OI", "OI Change"],
    category: "microstructure",
    family: "derivatives",
    definition: "OI 是尚未平掉的合约数量，代表杠杆仓位存量。价格变化配合 OI 变化，可以区分新资金入场、平仓推动或被动挤压。",
    how_to_use: "价格上涨且 OI 上升，偏新多/新空博弈加剧；价格上涨但 OI 下降，可能是空头回补；价格下跌且 OI 上升，可能是新空加仓。",
    risk_note: "OI 不告诉你多空方向，需要结合价格、资金费率和 CVD。",
    page_refs: ["alert-center", "monitoring-overview"],
    tags: ["microstructure"],
  }),
  term("cvd", "CVD 累计成交量差", {
    aliases: ["CVD", "Delta"],
    category: "microstructure",
    family: "flow",
    definition: "CVD 累计主动买入成交量与主动卖出成交量的差。它观察的是谁在主动跨价成交，而不是挂单意愿。",
    how_to_use: "价格创新高但 CVD 不创新高，说明突破可能更多来自流动性薄或被动成交；价格横盘但 CVD 抬升，说明主动买盘在吸收卖压。",
    risk_note: "不同交易所的 trade side 标记可能不同，CVD 更适合看斜率和背离，不适合看绝对值。",
    page_refs: ["alert-center"],
    tags: ["microstructure"],
  }),
  term("depth_slippage_spread", "Depth / Slippage / Spread / 深度、滑点与价差", {
    aliases: ["Depth 10bps", "Depth 50bps", "Depth 100bps", "Slippage", "Spread", "盘口深度", "滑点", "价差"],
    category: "microstructure",
    family: "liquidity",
    definition: "盘口深度衡量当前价格附近有多少可成交挂单；spread 是最优买卖价之间的空隙；slippage 是用一定金额吃单后，相对中间价发生的平均成交偏移。三者共同回答“这个信号能不能以接近预期的价格执行”。",
    how_to_use: "深度按 10/50/100bps 分层看：10bps 代表近端流动性，50-100bps 代表冲击吸收能力。买入滑点高说明上方卖盘薄，卖出滑点高说明下方买盘薄。",
    useful_when: "用于判断是否降低合约仓位、是否拆单、是否等待流动性恢复。",
    risk_note: "盘口是瞬时快照，新闻或大单期间会快速撤单，不能把静态深度当成真实承接。",
    page_refs: ["alert-center", "risk"],
    tags: ["liquidity", "microstructure"],
  }),
];

const macroItems = [
  term("cpi", "CPI / Consumer Price Index / 消费者物价指数", {
    aliases: ["US CPI", "Core CPI", "通胀"],
    category: "macro",
    family: "inflation",
    definition: "CPI 衡量居民消费价格变化，是市场判断通胀压力和美联储政策路径的核心数据。核心 CPI 剔除食品和能源，更常被用来观察粘性通胀。",
    how_to_use: "CPI 高于预期通常推升加息或高利率维持预期，利空风险资产；低于预期通常缓和利率压力，利好流动性敏感资产。",
    risk_note: "市场反应看“相对预期”，不是只看同比高低；还要看核心服务、住房等分项。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "inflation"],
  }),
  term("nfp", "NFP / Nonfarm Payrolls / 非农就业", {
    aliases: ["US NFP", "Nonfarm Payrolls", "非农"],
    category: "macro",
    family: "growth_labor",
    definition: "NFP 衡量美国非农部门新增就业，是判断劳动力市场强弱、工资压力和经济韧性的关键数据。",
    how_to_use: "就业强且薪资强，市场通常上修利率路径；就业明显转弱，则衰退交易和降息预期可能升温。",
    risk_note: "非农初值修订幅度可能很大，要同时看失业率、劳动参与率和平均时薪。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "labor"],
  }),
  term("fomc", "FOMC / Federal Open Market Committee / 美联储议息会议", {
    aliases: ["Fed", "Dot Plot", "Powell", "议息"],
    category: "macro",
    family: "policy",
    definition: "FOMC 决定联邦基金利率目标区间，并通过声明、点阵图和主席发布会影响未来政策预期。",
    how_to_use: "风险资产更关心前瞻指引是否偏鹰或偏鸽：更久高利率通常压制估值，降息路径明确通常改善流动性预期。",
    risk_note: "会议当天波动常来自措辞和发布会细节，不只是是否加息或降息。",
    page_refs: ["macro-calendar", "monitoring-overview", "market-events"],
    tags: ["macro", "policy"],
  }),
  term("dxy", "DXY / US Dollar Index / 美元指数", {
    aliases: ["美元指数", "Dollar Index"],
    category: "macro",
    family: "fx",
    definition: "DXY 衡量美元相对一篮子主要货币的强弱。美元走强通常意味着全球美元流动性变紧，非美资产和加密资产承压。",
    how_to_use: "DXY 上行且美债收益率上行时，风险资产反弹质量通常较差；DXY 回落则有利于流动性修复。",
    risk_note: "DXY 权重偏欧元，不能完整代表所有美元流动性环境。",
    page_refs: ["monitoring-overview", "market-events"],
    tags: ["macro", "fx"],
  }),
  term("us10y", "US10Y / 美国10年期国债收益率", {
    aliases: ["US 10Y", "10Y Treasury", "美债10年"],
    category: "macro",
    family: "rates",
    definition: "US10Y 是美国10年期国债收益率，常被视为全球风险资产估值的长期折现率锚。",
    how_to_use: "收益率上行会提高风险资产折现率，压制高久期资产；收益率快速下行若来自衰退担忧，也未必直接利好风险资产。",
    risk_note: "要区分“增长强导致收益率上行”和“通胀/期限溢价导致收益率上行”。",
    page_refs: ["monitoring-overview", "macro-calendar"],
    tags: ["macro", "rates"],
  }),
  term("risk_on_off", "Risk-On / Risk-Off / 风险偏好", {
    aliases: ["risk on", "risk off", "避险"],
    category: "macro",
    family: "risk",
    definition: "Risk-On 表示资金愿意承担风险，Risk-Off 表示资金偏向现金、美元、美债或黄金等防御资产。",
    how_to_use: "加密市场的突破若发生在 Risk-Off 背景下，需要更严格的成交量和结构确认。",
    page_refs: ["monitoring-overview", "market-events", "alert-center"],
    tags: ["macro", "risk"],
  }),
  term("gold", "Gold / 黄金", {
    aliases: ["XAU", "XAUUSD"],
    category: "macro",
    family: "risk",
    definition: "黄金同时受实际利率、美元、避险需求和央行买盘影响。它常用于观察市场是否在交易通胀、避险或美元信用压力。",
    how_to_use: "黄金和 BTC 同涨可能是流动性/货币属性交易，黄金涨而 BTC 跌更可能是避险或风险偏好下降。",
    page_refs: ["monitoring-overview", "market-events"],
    tags: ["macro", "risk"],
  }),
];

export const knowledgeSections = [
  {
    id: "technical",
    title: "技术指标与图表",
    summary: "趋势、动量、波动、量能和背离判断中真正会用到的指标。",
    items: technicalItems,
  },
  {
    id: "structure",
    title: "形态结构",
    summary: "结构页用于方向融合、确认和失效判断的核心概念。",
    items: structureItems,
  },
  {
    id: "alerts",
    title: "告警、筹码与微观结构",
    summary: "筹码、置信度、执行、风险和盘口流动性相关术语。",
    items: alertItems,
  },
  {
    id: "macro",
    title: "宏观与跨市场变量",
    summary: "CPI、NFP、FOMC、DXY、US10Y 等影响风险偏好的核心变量。",
    items: macroItems,
  },
];

const knowledgeDepthOverrides = {
  rsi: {
    summary: "衡量上涨/下跌动能的相对位置，重点看中轴、背离和趋势环境。",
    definition:
      "RSI 不是简单的超买超卖开关，而是把一段时间内上涨力度和下跌力度压缩到 0-100 的动量温度计。它最有价值的部分是判断动能区间：强趋势会长时间停留在 50 上方，弱趋势会长时间压在 50 下方；70/30 只是情绪温度偏高或偏低，不等于马上反转。",
    how_to_use:
      "先判断环境再读 RSI：多头趋势中，回调时 RSI 守住 40-50 区间，通常说明只是动能降温；空头趋势中，反弹时 RSI 无法站上 50-60，说明上行动能仍弱。价格创新高但 RSI 没有创新高，是上行动能边际衰退；价格创新低但 RSI 不创新低，是下行动能衰退。背离只有在结构失效或收回关键位后才有交易意义。",
    useful_when:
      "适合识别趋势回调是否健康、突破是否有动能跟随、以及背离风险是否开始积累。",
    thresholds: [
      "50 上方：偏多动能区，强趋势可长期维持",
      "40-50：多头趋势中的常见回调防线",
      "50-60：空头趋势中的反弹压力区",
      "70 以上：强势或过热，需要结合结构和量能",
      "30 以下：弱势或超卖，不能单独抄底",
    ],
    risk_note:
      "RSI 最大的误用是看到 70 就做空、看到 30 就做多。强趋势会让 RSI 长时间钝化，逆势交易需要等价格结构也出现确认。",
    example:
      "技术指标页中 BTC 4h 价格回踩 EMA 组，RSI 从 70 降到 48 后重新站回 55，同时 MACD 柱不再缩短，这比 RSI 单纯低于 70 更能说明多头回调可能结束。",
  },
  macd: {
    summary: "用快慢 EMA 差值观察趋势动能扩张、收缩和背离。",
    definition:
      "MACD 衡量的是快线成本和慢线成本之间的距离变化。DIF 高于 DEA 且柱体扩张，说明动能正在加速；DIF 仍在零轴上方但柱体缩短，说明趋势仍偏多但推进效率下降。零轴附近的反复金叉死叉多半是震荡噪音。",
    how_to_use:
      "MACD 要分三层读：第一看零轴，零轴上方偏多头动能环境，零轴下方偏空头动能环境；第二看柱体，柱体连续扩张说明边际动能增强，柱体连续缩短说明趋势可能进入衰减；第三看背离，价格创新高但柱体峰值降低，说明上涨仍在发生但推动力不如前一段。金叉死叉只有和结构突破、回踩确认配合时才更有价值。",
    useful_when:
      "适合判断趋势段的动能是否还在扩张，以及结构突破是否获得动能确认。",
    thresholds: [
      "零轴上方金叉：偏多环境中的动能恢复",
      "零轴下方死叉：偏空环境中的下行动能延续",
      "零轴附近频繁交叉：多为震荡噪音",
      "价格新高但柱体不新高：上行动能背离",
    ],
    risk_note:
      "MACD 滞后明显，单独用金叉追涨容易买在一段趋势的后半段；最好等待回踩不破或突破收盘确认。",
  },
  bollinger_bands: {
    summary: "用均线和标准差描述价格相对波动区间，重点看带宽、收缩和突破质量。",
    definition:
      "布林带把价格放进一个动态波动容器里：中轨代表近期均值，上下轨代表常见波动边界。带宽收窄说明波动被压缩，不代表一定上涨或下跌；带宽扩张说明价格开始释放波动。%B 用来衡量价格处在上下轨之间的相对位置。",
    how_to_use:
      "布林带要把位置和带宽分开读：价格贴上轨运行，在强趋势中可能是趋势延续，不是天然做空点；价格跌破下轨后快速收回，若成交量没有继续放大，可能是扫流动性；长期窄带后放量收盘突破，才更像波动释放。中轨常用作趋势中的动态回踩观察位。",
    useful_when:
      "适合判断压缩后的波动释放、趋势中的回踩位置，以及价格是否处于极端波动边界。",
    thresholds: [
      "带宽收窄：波动压缩，等待方向选择",
      "收盘突破上/下轨且带宽扩张：波动释放",
      "%B 接近 1：靠近上轨，不等于必然回落",
      "%B 接近 0：靠近下轨，不等于必然反弹",
    ],
    risk_note:
      "布林带边界不是固定阻力支撑。趋势越强，价格越可能沿轨道运行，逆势摸顶摸底风险很高。",
  },
  atr: {
    summary: "衡量真实波动空间，用于止损、仓位和杠杆，而不是判断方向。",
    definition:
      "ATR 统计一段时间内市场真实波动幅度，会把跳空或跨周期跳变纳入计算。它回答的是“正常波动会有多大”，不是“价格会往哪走”。因此 ATR 更接近风险尺，而不是方向信号。",
    how_to_use:
      "设置止损时，不应把止损放在小于当前 ATR 的随机噪音范围内；仓位管理时，ATR 越高，同样名义仓位承受的价格风险越大，应降低杠杆或缩小仓位。趋势突破后 ATR 温和上升通常代表波动释放；ATR 急剧上升且价格远离均线，则更要防止追价滑点和反抽。",
    useful_when:
      "适合做波动自适应止损、仓位上限、杠杆降级和异常波动识别。",
    thresholds: [
      "止损距离小于 1 倍 ATR：容易被正常噪音扫出",
      "ATR 快速抬升：波动风险上升，仓位应收缩",
      "ATR 低位压缩：后续可能出现波动释放",
    ],
    risk_note:
      "ATR 上升不等于趋势变强，也可能只是恐慌扫单或消息冲击。方向仍要看结构、动能和成交确认。",
  },
  natr: {
    summary: "把 ATR 标准化为百分比，便于比较不同币种的波动风险。",
    definition:
      "NATR = ATR / Close × 100，把绝对价格波动转成百分比。BTC 的 1000 美元 ATR 和小币种的 1 美元 ATR 不能直接比较，NATR 可以让不同价格等级的标的放在同一风险尺上。",
    how_to_use:
      "NATR 高时，系统应降低仓位、放宽止损或减少杠杆；NATR 低时，不代表安全，而是说明波动被压缩，后续突破时可能突然扩张。跨标的比较时，优先看 NATR 而不是 ATR 绝对值。",
    useful_when:
      "适合做跨币种风险比较、波动分位告警和合约仓位折扣。",
    risk_note:
      "低 NATR 常常发生在突破前的平静期，不能把低波动简单理解成低风险。",
  },
  adx: {
    summary: "衡量趋势强度，方向要结合 +DI / -DI 和价格结构判断。",
    definition:
      "ADX 只描述趋势是否有力度，不直接描述多空方向。+DI 代表上行动向强度，-DI 代表下行动向强度；ADX 抬升说明市场更像趋势环境，但方向必须由 +DI/-DI 相对位置和结构共同决定。",
    how_to_use:
      "当 +DI 高于 -DI 且 ADX 上行，说明多头趋势质量改善；当 -DI 高于 +DI 且 ADX 上行，说明空头趋势质量改善。若 ADX 高但 +DI/-DI 频繁交叉，通常是高波动震荡，不适合把它当趋势延续。ADX 从低位抬升配合收盘突破，比单独看 ADX 高值更有效。",
    useful_when:
      "适合区分趋势策略和区间策略：ADX 低时少追突破，ADX 抬升时更重视顺势回踩。",
    thresholds: [
      "18 以下：趋势弱或震荡",
      "22-30：趋势开始成形",
      "30 以上：趋势强，但也可能拥挤",
      "+DI/-DI 反复交叉：方向质量不足",
    ],
    risk_note:
      "ADX 高常常已经滞后于趋势启动，追单前要检查价格是否远离均线和是否接近结构失效位。",
  },
  obv: {
    summary: "用成交量累计方向观察量能是否支持价格趋势。",
    definition:
      "OBV 将上涨 K 线的成交量加总、下跌 K 线的成交量扣减，试图观察量能是否持续流向当前价格方向。它不关心单根 K 线涨了多少，而关心成交量是否在上涨日持续积累、在下跌日持续流出。",
    how_to_use:
      "价格横盘但 OBV 稳步抬升，可能代表买盘在吸收卖压；价格新高但 OBV 不新高，说明上涨缺少量能确认；价格下跌但 OBV 不再创新低，可能说明主动卖压衰退。OBV 的斜率比绝对值更重要。",
    useful_when:
      "适合辅助判断突破是否有量能、平台整理是否在吸筹，以及背离风险是否积累。",
    risk_note:
      "交易所成交量会受刷量、迁移和异常成交影响。OBV 应结合 CVD、成交额和结构位置，而不是孤立使用。",
  },
  divergence: {
    summary: "价格与动能/量能不同步，提示趋势质量下降，不等于立即反转。",
    definition:
      "背离描述的是价格继续沿原方向推进，但 RSI、MACD、OBV、CVD 等动能或量能指标没有同步确认。它本质上是趋势效率下降的证据，而不是自动反向开仓信号。",
    how_to_use:
      "有效背离至少需要三步：价格必须用收盘价形成新高或新低；指标没有同步形成新高或新低；随后价格出现关键位收回、结构破坏或回踩失败。只有前两步时更适合作为风险提醒，第三步出现后才接近交易信号。",
    useful_when:
      "适合识别趋势后半段风险、突破质量不足和告警中心的风险降级。",
    thresholds: [
      "价格创新高 + RSI/MACD 不创新高：上行动能背离",
      "价格创新低 + RSI/MACD 不创新低：下行动能背离",
      "背离后仍未跌破结构：仅风险提醒",
      "背离后关键位失守：反转风险显著提高",
    ],
    risk_note:
      "强趋势可以连续背离很多次。没有结构确认就逆势交易，容易被趋势延续反复止损。",
  },
  breakout: {
    summary: "有效突破要看收盘离开关键区、回踩不破和量价确认。",
    definition:
      "突破不是影线刺穿，而是价格用收盘价离开重要区间、摆动高低点或价值区边界。假突破则是突破后无法延续，并重新收回原区间，常见于扫止损和流动性诱导。",
    how_to_use:
      "先要求至少一次收盘突破，再观察回踩是否守住突破位，最后看成交量、CVD 或 OI 是否确认。如果只有 high/low 插针而收盘回到区间内，应优先视为扫流动性；如果突破后量能萎缩且很快回到区间，假突破概率升高。",
    useful_when:
      "适合结构页判断 BOS/CHOCH 的有效性，也适合告警页识别追涨追空风险。",
    thresholds: [
      "收盘突破：最低确认条件",
      "回踩不破：延续质量确认",
      "放量/CVD/OI 同向：提高有效性",
      "突破后快速收回区间：假突破风险",
    ],
    risk_note:
      "突破后的第一根大阳/大阴往往滑点最大。更稳妥的做法是等回踩确认或等待下一根收盘延续。",
  },
  market_structure: {
    summary: "用 HH/HL/LH/LL 和摆动点序列判断趋势延续或转弱。",
    definition:
      "市场结构关注价格摆动点之间的相对关系。连续 HH/HL 表示买方能不断推高并守住回撤，连续 LH/LL 表示卖方压低反弹并继续打低。结构判断比单根 K 线更慢，但能过滤大量噪音。",
    how_to_use:
      "不要只看最后一个高低点，要看序列是否连续、突破是否收盘确认、回撤是否守住关键 swing。上升结构中，HL 被有效跌破往往比单次冲高失败更重要；下降结构中，LH 被有效突破才说明空头结构被破坏。",
    useful_when:
      "适合形态结构页做方向骨架，也适合最终决策判断趋势证据是否成立。",
    risk_note:
      "周期越低，摆动点越多、噪音越大。1h 的 CHOCH 可能只是 1d 趋势中的普通回调。",
  },
  bos_choch: {
    summary: "BOS 偏趋势延续，CHOCH 偏角色切换预警，都需要收盘和后续确认。",
    definition:
      "BOS 是价格沿原趋势方向突破关键摆动点，说明原结构仍在推进；CHOCH 是价格打破原趋势中应当守住的位置，提示市场角色可能从多头主导转为空头主导，或反过来。",
    how_to_use:
      "BOS 更适合顺势交易的确认，CHOCH 更适合风险预警。高质量 BOS 应有收盘突破、回踩不破和量能确认；高质量 CHOCH 应看到原趋势关键位失守，并且反抽无法重新收回。只有影线穿越不能直接当 BOS/CHOCH。",
    useful_when:
      "适合结构页解释摆动结构，也适合告警中心判断趋势失效条件。",
    risk_note:
      "过度标记 BOS/CHOCH 会让结构页变成噪音地图。真正重要的是高周期关键摆动点和收盘确认。",
  },
  volume_profile: {
    summary: "按价格分布成交量，识别 POC、价值区和成本迁移。",
    definition:
      "成交量轮廓把一段时间的成交量投射到价格轴上，回答“市场主要在哪些价格成交”，而不是“成交发生在什么时间”。POC 是成交最密集价格，VAH/VAL 是覆盖主要成交量的价值区上沿和下沿。",
    how_to_use:
      "价格在价值区内部运行，通常代表市场仍在接受该价格区间；价格离开 VAH/VAL 并回踩不回区间，说明价值可能迁移；价格突破后又回到价值区，说明突破接受度不足。POC 上移代表市场公平价格抬升，POC 下移则代表成本重心下移。",
    useful_when:
      "适合判断区间上下沿、突破是否被市场接受，以及筹码结构中的吸筹/派发位置。",
    risk_note:
      "样本太短或流动性太低会让 POC 跳动很大。不要把 POC 当成固定价格线，要看它是否持续迁移。",
  },
  regime: {
    summary: "把市场环境压缩成趋势、平衡或过渡，决定应采用哪类策略。",
    definition:
      "Regime 是交易环境标签，不是方向信号。Trend 表示方向延续占优，Balance 表示价格在价值区或区间内往复，Transition 表示旧结构正在失效但新结构尚未稳定。",
    how_to_use:
      "Trend 环境优先顺势等回踩，少做逆势摸顶摸底；Balance 环境优先等待边界和均值回归，不追区间中部；Transition 环境应降低仓位，因为多空证据正在切换，假突破和来回扫损更常见。",
    useful_when:
      "适合决定技术指标权重：趋势环境提高 EMA/ADX 权重，平衡环境提高 Volume Profile 和区间边界权重。",
    risk_note:
      "Regime 变化通常滞后。看到 transition 时，不是马上反向，而是先降低执行强度。",
  },
  chip_structure: {
    summary: "用价格位置、量能和微观结构推断吸筹/派发，但缺证据只能 proxy。",
    definition:
      "筹码结构在本系统中不是链上持仓，也不是交易所真实账户分布，而是把成交密集区、价值区位置、OBV/CVD、OI、资金费率、深度和滑点合成，推断市场是在吸收卖压、派发筹码，还是只是普通区间换手。",
    how_to_use:
      "吸筹更常见于价格位于价值区下半部或关键支撑附近，卖压被反复接住，OBV/CVD 改善，OI 没有异常挤压；派发更常见于价格高位放量但推进变慢，CVD/OI 不确认，突破后无法接受更高价格。缺少 CVD、OI、深度、滑点或资金费率时，只能输出 proxy，不能当 confirmed。",
    useful_when:
      "适合告警中心判断仓位是否应保守、是否等待确认，以及风险提示是否要降级为观察。",
    risk_note:
      "筹码结构最怕把 OHLCV 的形态想象成真实持仓。没有微观结构确认时，结论必须降级。",
  },
  funding_rate: {
    summary: "永续合约多空交换费用，反映杠杆拥挤和合约价格贴水/升水压力。",
    definition:
      "资金费率让永续合约价格向指数价格靠拢。正费率通常表示多头为持仓付费，负费率表示空头付费。它更像杠杆情绪和拥挤度指标，而不是单独的方向指标。",
    how_to_use:
      "高正费率配合价格上涨和 OI 上升，说明多头拥挤，趋势可能仍强但踩踏风险也升高；高正费率但价格无法继续上涨，容易出现多头去杠杆。高负费率配合价格不再下跌，可能出现空头回补。资金费率回到中性区，说明拥挤压力缓和。",
    useful_when:
      "适合判断合约仓位是否过热、是否降低杠杆，以及反向挤压风险。",
    risk_note:
      "强趋势中高资金费率可以持续很久，不能只因费率高就逆势做空。",
  },
  mark_price: {
    summary: "合约风控参考价，和最新成交价的偏离会影响执行与强平风险。",
    definition:
      "标记价通常由指数价、资金费率基差和交易所风控模型决定，用来计算未实现盈亏和强平风险。它比最新成交价更稳定，但也意味着成交价和标记价偏离过大时，盘面可能存在短时流动性冲击。",
    how_to_use:
      "最新价高于标记价很多，说明追涨成交可能偏离风控参考价；最新价低于标记价很多，说明恐慌成交或薄盘口可能正在放大下跌。执行时要同时看 index、mark、basis 和 deviation，偏离过大时降低市价单和杠杆。",
    useful_when:
      "适合技术页实时标记价、告警页合约风险和执行标签判断。",
    risk_note:
      "标记价不是一定能成交的价格。它用于风控，不等于盘口最优价。",
  },
  open_interest: {
    summary: "未平仓合约存量，用来区分新资金入场、平仓推动和挤压风险。",
    definition:
      "OI 表示仍然打开的合约数量。价格变化告诉你结果，OI 变化帮助判断这段价格变化背后是新仓推动，还是旧仓平掉。OI 上升代表杠杆风险累积，OI 下降代表仓位释放。",
    how_to_use:
      "价格上涨且 OI 上升，说明新仓参与增加，但需要 CVD 判断主动买盘是否确认；价格上涨且 OI 下降，可能是空头回补，延续性未必强；价格下跌且 OI 上升，说明新空或被套多空博弈加剧；价格下跌且 OI 下降，多半是去杠杆释放。",
    useful_when:
      "适合判断突破质量、挤压风险、资金费率拥挤是否危险。",
    risk_note:
      "OI 本身不告诉多空方向，必须和价格、CVD、资金费率一起看。",
  },
  cvd: {
    summary: "累计主动买卖成交差，观察谁在主动跨价推动价格。",
    definition:
      "CVD 把主动买入成交量减去主动卖出成交量并累积。它关注的是成交侵略性：买方是否愿意吃掉卖单，卖方是否愿意砸掉买单。它比普通成交量更接近订单流方向。",
    how_to_use:
      "价格上涨且 CVD 同步上升，说明主动买盘确认；价格上涨但 CVD 横盘或下降，可能是被动成交或薄盘口推高，突破质量下降。价格横盘但 CVD 持续上升，可能是吸收卖压；价格横盘但 CVD 持续下降，可能是上方派发或买盘衰退。",
    useful_when:
      "适合确认突破、识别背离、区分吸筹和派发。",
    risk_note:
      "CVD 依赖交易所 trade side 标记，跨交易所口径可能不同。看斜率和背离比看绝对值更可靠。",
  },
  depth_slippage_spread: {
    summary: "从盘口厚度、买卖价差和吃单冲击衡量流动性质量。",
    definition:
      "盘口深度回答“当前价格附近有多少可成交流动性”，spread 回答“立刻买卖要付多少价差成本”，slippage 回答“用指定金额吃单后平均成交价会偏离中间价多少”。三者合起来衡量的是执行质量，而不是方向。",
    how_to_use:
      "10bps 深度代表近端流动性，适合判断小单是否容易成交；50/100bps 深度代表更大冲击下的承接能力。spread 扩大说明立即成交成本升高；买入滑点高说明上方卖盘薄，追多成本高；卖出滑点高说明下方买盘薄，止损或恐慌盘可能踩踏。若信号方向很好但滑点/spread 变差，执行标签应降级。",
    useful_when:
      "适合决定是否拆单、是否降低合约仓位、是否等待流动性恢复。",
    thresholds: [
      "10bps 深度下降：近端成交质量变差",
      "50/100bps 深度下降：大单冲击风险升高",
      "spread 扩大：市价成交成本升高",
      "单边滑点显著升高：对应方向追价风险升高",
    ],
    risk_note:
      "盘口是瞬时快照，新闻和大单期间撤单很快。深度好不代表真正能承接所有市价冲击。",
  },
};

for (const section of knowledgeSections) {
  for (const item of section.items) {
    if (knowledgeDepthOverrides[item.id]) {
      Object.assign(item, knowledgeDepthOverrides[item.id]);
    }
  }
}

function normalizeTerm(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[\s\-_/()（）·:：]+/g, "")
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
        ...(item.aliases || []),
        ...(item.tags || []),
      ]
        .map(normalizeTerm)
        .some((value) => value.includes(normalized));
    }),
  );
}
