// Page-private identity and field adapter. No indicator calculations or new
// market judgements belong here: descriptions come from the existing renderer.
export const SIGNAL_IDS = ['ema-trend', 'adx', 'macd', 'rsi', 'volatility', 'vwap', 'obv', 'kdj', 'cci'];
export const CHART_OBJECTS = {
  'analysis-price': ['ema-trend', 'ema-trend', 'ema-trend', 'ema-trend', 'vwap', 'vwap'],
  'analysis-vegas': ['vegas', 'vegas', 'vegas', 'vegas', 'vegas'],
  'analysis-boll': ['volatility', 'volatility', 'volatility', 'volatility'],
  'analysis-rsi': ['rsi'], 'analysis-volume': ['volume'], 'analysis-macd': ['macd', 'macd', 'macd'],
};
const RELATIONS = {
  'ema-trend': ['directional-bias'], adx: ['directional-bias'],
  macd: ['directional-bias'], rsi: ['directional-bias'], vwap: ['directional-bias'],
  obv: ['directional-bias'], volatility: ['volatility-phase'],
  'directional-bias': ['ema-trend', 'adx', 'macd', 'rsi', 'vwap', 'obv'],
  'volatility-phase': ['volatility'],
};
const last = (values) => values?.at?.(-1);
const present = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
export const analysisObjectId = (key) => `analysis:${key}`;

export function buildAnalysisInspections({ analysis: a, cards, bundle, phase, direction, descriptions }) {
  const fields = {
    'ema-trend': [['EMA 30', last(a.ema30)], ['EMA 60', last(a.ema60)], ['EMA 120', last(a.ema120)]],
    adx: [['ADX', last(a.adxValues.adxValues)], ['+DI', last(a.adxValues.plusDi)], ['-DI', last(a.adxValues.minusDi)]],
    macd: [['MACD 柱', last(a.macdValues.hist)], ['MACD', last(a.macdValues.line)], ['信号线', last(a.macdValues.signal)]],
    rsi: [['RSI 14', last(a.rsiValues)]],
    volatility: [['BOLL 宽度', last(a.boll.width)], ['ATR 14', last(a.atrValues)], ['上轨', last(a.boll.upper)], ['下轨', last(a.boll.lower)]],
    vwap: [['VWAP 50', last(a.vwapValues.vwap50)], ['VWAP 100', last(a.vwapValues.vwap100)]],
    obv: [['OBV', last(a.obvValues)]],
    kdj: [['K', last(a.kdjValues.k)], ['D', last(a.kdjValues.d)], ['J', last(a.kdjValues.j)]],
    cci: [['CCI 20', last(a.cciValues)]],
    vegas: [['EMA 12', last(a.ema12)], ['快轨下沿', last(a.vegasFastLow)], ['快轨上沿', last(a.vegasFastHigh)], ['慢轨下沿', last(a.vegasSlowLow)], ['慢轨上沿', last(a.vegasSlowHigh)]],
    volume: [['成交量', last(a.volumes)]],
  };
  const timestamp = bundle.data_ts || bundle.snapshot_at || null;
  // AnalysisBundleRead has cache metadata, not a provider's live status.
  const status = ['stale', 'stale_revalidating'].includes(bundle.cache_state) || bundle.status === 'stale'
    ? 'stale' : ['error', 'degraded'].includes(bundle.status) ? 'degraded' : 'unavailable';
  const sources = [{ name: '分析快照', status, updatedAt: timestamp }];
  const objects = [];
  const rows = [...cards, { key: 'vegas', title: 'Vegas 通道', desc: descriptions.vegas },
    { key: 'volume', title: '成交量', desc: descriptions.volume }];
  for (const row of rows) {
    const facts = (fields[row.key] || []).filter(([, value]) => present(value));
    if (!facts.length) continue;
    const id = analysisObjectId(row.key);
    const marketTone = ['bullish', 'bearish', 'neutral'].includes(row.tone) ? row.tone : 'neutral';
    const relatedIds = (RELATIONS[row.key] || []).map(analysisObjectId);
    const evidence = facts.map(([label, value], index) => ({
      id: `${id}:evidence:${index}`, label, value, relatedIds: [id], sourceId: 'analysis-snapshot',
    }));
    objects.push({ id, type: '技术指标', title: row.title,
      current: { label: evidence[0].label, value: evidence[0].value, marketTone },
      interpretation: row.desc, evidence, relatedIds, sources, updatedAt: timestamp });
  }
  for (const [key, title, value] of [
    ['volatility-phase', '波动阶段', phase], ['directional-bias', '方向环境', direction],
  ]) {
    if (!value?.label) continue;
    objects.push({ id: analysisObjectId(key), type: '环境分类', title,
      current: { label: title, value: value.label }, interpretation: value.summary || '',
      evidence: [], relatedIds: (RELATIONS[key] || []).map(analysisObjectId), sources, updatedAt: timestamp });
  }
  const ids = new Set(objects.map((item) => item.id));
  return objects.map((item) => ({ ...item, relatedIds: item.relatedIds.filter((id) => ids.has(id)) }));
}
