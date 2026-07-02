function asArray(value) {
  return Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined && item !== "") : [];
}

function joinList(value, fallback = "-") {
  const items = asArray(value);
  return items.length ? items.join(" / ") : fallback;
}

function formatConfidence(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Math.round(number)}%`;
}

function freshnessLabel(value) {
  const map = {
    fresh: "新鲜",
    ready: "新鲜",
    live: "新鲜",
    usable_stale: "可降级",
    stale: "过期",
    missing: "缺失",
    error: "异常",
    updating: "更新中",
  };
  return map[String(value || "").toLowerCase()] || value || "未知";
}

function sourceModuleLabel(module) {
  const map = {
    "MarketContextBuilder": "市场上下文",
    "MacroOverviewService": "宏观",
    "ChipStructureService": "筹码结构",
    "BtcDerivativesService": "衍生品",
    "OnchainFeatureEngine": "链上",
    "OnchainProvider": "链上",
    "StrategyGenerator": "策略生成",
    "StrategySignalService": "策略信号",
    "MultiTimeframeStructureEngine": "周期结构",
    "CrossHorizonSynthesisEngine": "跨周期合成",
    "UnifiedRiskGateEngine": "风险门禁",
    "IndicatorObservation": "指标观察",
    "IndicatorMonitoringService": "指标监控",
  };
  return map[module] || module;
}

function sourceTimeframeLabel(timeframe) {
  const map = {
    "1M": "月线",
    "1w": "周线",
    "1d": "日线",
    "4h": "4 小时",
    "1h": "1 小时",
    "15m": "15 分钟",
  };
  return map[timeframe] || timeframe || "-";
}

function renderCard(item, escapeHtml) {
  const conclusionKey = String(item.conclusion_key || "source");
  const title = String(item.conclusion || item.label || "-");
  const body = String(
    item.human_explanation || item.summary || item.message || "暂无解释文本"
  );
  const confidence = formatConfidence(item.confidence);
  const freshness = freshnessLabel(item.freshness);
  const sources = joinList(
    asArray(item.source_modules).map(sourceModuleLabel)
  );
  const timeframes = joinList(
    asArray(item.source_timeframes).map(sourceTimeframeLabel)
  );
  return `
    <article class="strategy-evidence-item">
      <p class="eyebrow">${escapeHtml(conclusionKey)}</p>
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body)}</p>
      <dl class="strategy-evidence-meta">
        <div>
          <dt>置信度</dt>
          <dd>${escapeHtml(confidence)}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>${escapeHtml(sources)}</dd>
        </div>
        <div>
          <dt>周期 / 时效</dt>
          <dd>${escapeHtml(timeframes)} · ${escapeHtml(freshness)}</dd>
        </div>
      </dl>
    </article>
  `;
}

export function renderEvidenceTrace(model, helpers) {
  const { escapeHtml } = helpers;
  const traces = (model.evidence_trace || []).map((item) => renderCard(item, escapeHtml));
  return `
    <section class="strategy-v2-section strategy-evidence-trace card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">EVIDENCE TRACE</p>
          <h2>结论来源与依据</h2>
        </div>
      </div>
      <div class="strategy-v2-grid evidence">${traces.join("") || helpers.emptyState("暂无证据链")}</div>
    </section>
  `;
}