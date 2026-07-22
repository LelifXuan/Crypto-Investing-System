import { api } from "../core/api.js";
import { escapeHtml, formatNumber, setRoot } from "../core/dom.js";

let controller = null;
let latestData = null;

function money(value, digits = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? `${formatNumber(n, digits)} 元` : "—";
}

function formatPct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${formatNumber(n * 100, 1)}%` : "—";
}

function biasClass(bias) {
  return `gold-bias-chip gold-bias-${bias || "neutral"}`;
}

function biasLabel(bias) {
  return {
    strong_bullish: "🟢 强势看多", bullish: "🟢 看多",
    neutral: "🟡 中性", bearish: "🔴 看空",
    strong_bearish: "🔴 强势看空", missing: "⚪ 数据不足",
  }[bias] || "🟡 中性";
}

// ── Signal definitions ──
// Core macro signals: TIPS 实际利率, DXY 美元, VIX 波动

// ── Rendering ──

function renderShell(data) {
  const sigs = data?.signals || [];
  const spot = data?.spot || {};
  const contract = data?.contract || {};
  const shock = data?.liquidity_shock_detected;

  return `
    <section class="gold-v3-page">
      <div class="gold-v3-macro-panel">
        <div class="gold-v3-macro-header">
          <h1>黄金配置 V3</h1>
          <p class="gold-v3-summary">${escapeHtml(data?.spot_summary || "加载中…")}</p>
          ${shock ? '<span class="gold-v3-shock-tag">⚠ 流动性冲击</span>' : ""}
        </div>
        <div class="gold-v3-signal-row">
          ${sigs.map(renderSignalLight).join("")}
        </div>
      </div>

      <div class="gold-v3-workbench">
        <div class="gold-v3-spot">
          ${renderSpotDca(spot, contract)}
        </div>
        <div class="gold-v3-contract">
          ${renderContractRef(contract)}
        </div>
      </div>

      <div class="gold-v3-footer">
        <button class="button compact" id="gold-v3-refresh">刷新数据</button>
      </div>
    </section>
  `;
}

function renderSignalLight(s) {
  return `
    <article class="gold-v3-signal-light">
      <div class="gold-v3-signal-head">
        <strong>${escapeHtml(s.label)}</strong>
        <span class="gold-v3-signal-code">${escapeHtml(s.code)}</span>
      </div>
      <div class="gold-v3-signal-value">
        ${s.value != null ? formatNumber(s.value, 2) : "—"}${escapeHtml(s.unit)}
      </div>
      <span class="${biasClass(s.bias)}">${biasLabel(s.bias)}</span>
      <p class="gold-v3-signal-reason">${escapeHtml(s.bias_reason)}</p>
    </article>
  `;
}

function renderSpotDca(spot) {
  const weightBarPct = Math.min(100, Math.max(0, ((spot.current_weight || 0) / (spot.target_max || 0.1)) * 100));
  const triggerTotal = (spot.base_amount || 0) + (spot.base_amount || 0) * (spot.dip_multiplier || 0);

  return `
    <div class="gold-v3-section-card">
      <p class="eyebrow">现货定投</p>
      <h2>持仓与执行</h2>

      <div class="gold-v3-weight-bar">
        <span>当前 ${formatPct(spot.current_weight)}</span>
        <div class="gold-v3-bar-track">
          <div class="gold-v3-bar-fill" style="width:${weightBarPct}%"></div>
        </div>
        <span>目标 ${formatPct(spot.target_min)}–${formatPct(spot.target_max)}</span>
      </div>

      <div class="gold-v3-formula">
        <div class="gold-v3-formula-item">
          <span class="gold-v3-formula-var">x</span>
          <span>${money(spot.base_amount)}</span>
          <small>基础定投</small>
        </div>
        <span class="gold-v3-formula-op">+</span>
        <div class="gold-v3-formula-item">
          <span class="gold-v3-formula-var">n × x</span>
          <span>${money(spot.base_amount * spot.dip_multiplier)}</span>
          <small>加仓 (×${escapeHtml(String(spot.dip_multiplier))})</small>
        </div>
        <span class="gold-v3-formula-op">=</span>
        <div class="gold-v3-formula-item gold-v3-formula-total">
          <strong>${money(triggerTotal)}</strong>
          <small>触发时合计</small>
        </div>
      </div>

      <div class="gold-v3-gate">
        <h3>加仓条件</h3>

        <div class="gold-v3-gate-row ${spot.macro_gate_passed ? "passed" : "blocked"}">
          <span class="gold-v3-gate-num">①</span>
          <span>宏观门禁</span>
          <span class="chip">${spot.macro_gate_passed ? "✅ 通过" : "❌ 关闭"}</span>
          <small>${escapeHtml(spot.macro_gate_reason || "")}</small>
        </div>

        <div class="gold-v3-gate-row ${spot.drawdown_triggered ? "passed" : ""}">
          <span class="gold-v3-gate-num">②</span>
          <span>回撤触发</span>
          <span class="chip">${spot.drawdown_triggered ? "✅ 触发" : "— 未触发"}</span>
          <small>60日回撤 ${formatPct(spot.drawdown_60d)} ≥ 阈值 ${formatPct(spot.drawdown_threshold)}</small>
        </div>

        <div class="gold-v3-gate-row ${spot.confirmations_passed >= spot.confirmations_required ? "passed" : ""}">
          <span class="gold-v3-gate-num">③</span>
          <span>指标确认 ${spot.confirmations_passed}/${spot.confirmations_required}</span>
          ${(spot.indicator_confirmations || []).map((ind) => `
            <div class="gold-v3-indicator-row ${ind.passed ? "passed" : ""}">
              <span>${escapeHtml(ind.label)}</span>
              <span>${escapeHtml(ind.display)}</span>
              <small>${escapeHtml(ind.condition)}</small>
              <span>${ind.passed ? "✓" : "✗"}</span>
            </div>
          `).join("")}
        </div>
      </div>

      <div class="gold-v3-recommendation">
        <strong>本月建议</strong>
        <span class="gold-v3-recommend-amount">${money(spot.recommended_amount)}</span>
        <p>${escapeHtml(spot.recommendation_reason)}</p>
      </div>
    </div>
  `;
}

function renderContractRef(contract) {
  const ma50Label = contract.above_ma50 === true ? "上方" : contract.above_ma50 === false ? "🔴 下方" : "—";
  const ma200Label = contract.above_ma200 === true ? "上方" : contract.above_ma200 === false ? "🔴 下方" : "—";

  return `
    <div class="gold-v3-section-card">
      <p class="eyebrow">合约参考</p>
      <h2>XAUT + 衍生品</h2>

      <div class="gold-v3-tech-grid">
        <article><span>最新价</span><b>${money(contract.price, 2)}</b></article>
        <article><span>MA50</span><b>${money(contract.ma50_value)} ${ma50Label}</b></article>
        <article><span>MA200</span><b>${money(contract.ma200_value)} ${ma200Label}</b></article>
        <article><span>60日回撤</span><b>${formatPct(contract.drawdown_60d)}</b></article>
        <article><span>NATR(14)</span><b>${formatPct(contract.natr_14)}</b></article>
        <article><span>成交量 Z</span><b>${formatNumber(contract.volume_zscore, 1)}</b></article>
      </div>

      <h3>衍生品数据</h3>
      <div class="gold-v3-tech-grid">
        <article><span>OI 变化(4w)</span><b>${contract.oi_change_4w != null ? formatPct(contract.oi_change_4w) : "—"}</b></article>
        <article><span>资金费率</span><b>${contract.funding_rate != null ? formatNumber(contract.funding_rate * 100, 4) + "%" : "—"}</b></article>
        <article><span>COT 净多分位</span><b>${contract.cot_net_spec_percentile != null ? formatNumber(contract.cot_net_spec_percentile * 100, 0) + "%" : "—"}</b></article>
      </div>
      ${contract.derivatives_note ? `<p class="gold-v3-note">${escapeHtml(contract.derivatives_note)}</p>` : ""}
    </div>
  `;
}

// ── Lifecycle ──

async function loadData() {
  if (controller) controller.abort();
  controller = new AbortController();

  try {
    latestData = await api.getGoldV3Allocation({ signal: controller.signal });
  } catch (e) {
    if (e?.name !== "AbortError") console.warn("V3 allocation unavailable", e);
  }

  try {
    const deriv = await api.getGoldDerivatives({ signal: controller.signal });
    if (latestData?.contract) {
      latestData.contract.oi_change_4w = deriv.oi_change_4w;
      latestData.contract.funding_rate = deriv.funding_rate;
      latestData.contract.cot_net_spec_percentile = deriv.cot_net_spec_percentile;
      latestData.contract.derivatives_note = deriv.derivatives_note;
    }
  } catch (e) {
    if (e?.name !== "AbortError") console.warn("Derivatives unavailable", e);
  }

  setRoot(renderShell(latestData || {}));
  bindEvents();
}

function bindEvents() {
  document.getElementById("gold-v3-refresh")?.addEventListener("click", () => {
    loadData().catch((e) => console.error("gold v3 reload failed", e));
  });
}

export async function renderGoldV3() {
  const ready = loadData().catch((e) => {
    if (e?.name !== "AbortError") console.error("gold v3 initial load failed", e);
  });
  return {
    unmount() {
      if (controller) controller.abort();
    },
    ready,
  };
}
