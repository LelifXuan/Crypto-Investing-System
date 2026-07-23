import { api } from "../core/api.js";
import { escapeHtml, formatNumber, setRoot } from "../core/dom.js";

let controller = null;
let latestData = null;

function biasChipClass(bias) {
  return {
    strong_bullish: "chip-bullish",
    bullish: "chip-bullish-soft",
    neutral: "chip-neutral",
    bearish: "chip-bearish",
    strong_bearish: "chip-bearish",
    missing: "chip-warning",
  }[bias] || "chip-neutral";
}

function biasLabel(bias) {
  return {
    strong_bullish: "强势看多", bullish: "看多",
    neutral: "中性", bearish: "看空",
    strong_bearish: "强势看空", missing: "数据不足",
  }[bias] || "中性";
}

function money(v, d) { const n = Number(v); return Number.isFinite(n) ? `${formatNumber(n, d || 0)} 元` : "—"; }
function pct(v) { const n = Number(v); return Number.isFinite(n) ? `${formatNumber(n * 100, 1)}%` : "—"; }

function renderHero(data) {
  const shock = data?.liquidity_shock_detected;
  return `
    <section class="hero-card">
      <div>
        <p class="eyebrow">GOLD ALLOCATION</p>
        <h1>黄金宏观与配置</h1>
        <p>${escapeHtml(data?.spot_summary || "加载中…")}</p>
        ${shock ? '<p><span class="chip chip-warning">⚠ 流动性冲击 — VIX≥25 + DXY≥105 + TIPS≥2.0</span></p>' : ""}
      </div>
      <button class="button compact" id="gold-refresh">刷新 XAUT</button>
    </section>
  `;
}

function renderSignalCard(s) {
  return `
    <article class="card gold-signal-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <p class="eyebrow">${escapeHtml(s.label)}</p>
        <span class="gold-code-badge">${escapeHtml(s.code)}</span>
      </div>
      <div class="gold-signal-value">${s.value != null ? formatNumber(s.value, 2) : "—"}<span class="gold-signal-unit">${escapeHtml(s.unit)}</span></div>
      <span class="chip ${biasChipClass(s.bias)}">${biasLabel(s.bias)}</span>
      <p class="gold-signal-reason">${escapeHtml(s.bias_reason)}</p>
      <div class="gold-signal-source">${s.source ? `来源 ${escapeHtml(s.source)}` : ""}${s.observation_ts ? ` · ${escapeHtml(String(s.observation_ts).slice(0,10))}` : ""}</div>
    </article>
  `;
}

function renderSignalStrip(signals) {
  if (!signals?.length) return "";
  return `
    <div>
      <div class="section-head">
        <div>
          <p class="eyebrow">MACRO SIGNALS</p>
          <h2>宏观信号灯</h2>
        </div>
        <p>实际利率、美元、波动率 — 三个核心宏观变量</p>
      </div>
      <div class="gold-signal-grid">
        ${signals.map(renderSignalCard).join("")}
      </div>
    </div>
  `;
}

function renderSpotDca(spot) {
  const w = (spot.current_weight || 0) / (spot.target_max || 0.1) * 100;
  const total = (spot.base_amount || 0) + (spot.base_amount || 0) * (spot.dip_multiplier || 0);
  const inds = spot.indicator_confirmations || [];
  const passedCount = inds.filter(function(i) { return i.passed; }).length;

  return `
    <div class="card" style="display:flex;flex-direction:column;gap:18px">
      <div>
        <p class="eyebrow">SPOT DCA</p>
        <h3>现货定投</h3>
      </div>

      <div>
        <div class="gold-weight-label"><span>当前权重</span><span><b>${pct(spot.current_weight)}</b> / 目标 ${pct(spot.target_min)}–${pct(spot.target_max)}</span></div>
        <div class="gold-weight-bar"><div class="gold-weight-fill" style="width:${Math.min(100,Math.max(0,w))}%"></div></div>
        <span class="chip chip-neutral" style="margin-top:5px">${spot.weight_state === "underweight" ? "低配" : spot.weight_state === "overweight" ? "超配" : "达标"}</span>
      </div>

      <div class="gold-formula-box">
        <div class="gold-formula-item"><span class="gold-formula-var">x</span><span>${money(spot.base_amount)}</span><small>基础</small></div>
        <span class="gold-formula-op">+</span>
        <div class="gold-formula-item"><span class="gold-formula-var gold-formula-dip">n × x</span><span>${money(spot.base_amount * spot.dip_multiplier)}</span><small>加仓 ×${escapeHtml(String(spot.dip_multiplier))}</small></div>
        <span class="gold-formula-op">=</span>
        <div class="gold-formula-total"><strong>${money(total)}</strong><small>触发合计</small></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:6px">
        <p style="font-weight:600;font-size:13px;margin:0">加仓条件门禁</p>
        <div class="gold-gate-row ${spot.macro_gate_passed ? 'passed' : 'blocked'}">
          <span class="gold-gate-num">①</span><span>宏观门禁</span>
          <span class="chip ${spot.macro_gate_passed ? 'chip-bullish-soft' : 'chip-bearish'}">${spot.macro_gate_passed ? '通过' : '关闭'}</span>
          <small>${escapeHtml(spot.macro_gate_reason || "")}</small>
        </div>
        <div class="gold-gate-row ${spot.drawdown_triggered ? 'triggered' : ''}">
          <span class="gold-gate-num">②</span><span>回撤触发</span>
          <span class="chip ${spot.drawdown_triggered ? 'chip-bullish-soft' : 'chip-warning'}">${spot.drawdown_triggered ? '触发' : '未触发'}</span>
          <small>60 日回撤 ${pct(spot.drawdown_60d)} ≥ 阈值 ${pct(spot.drawdown_threshold)}</small>
        </div>
        <div class="gold-gate-row ${passedCount >= spot.confirmations_required ? 'passed' : ''}">
          <span class="gold-gate-num">③</span><span>指标确认</span>
          <span class="chip ${passedCount >= 3 ? 'chip-bullish-soft' : 'chip-warning'}">${passedCount}/${spot.confirmations_required}</span>
          <small>需 ≥ ${spot.confirmations_required} 个通过</small>
        </div>
        <div class="gold-indicator-grid">
          ${inds.map(function(i) { return `
            <div class="gold-indicator-row ${i.passed ? 'gold-indicator-pass' : ''}">
              <span>${escapeHtml(i.label)}</span><span>${escapeHtml(i.display)}</span><small>${escapeHtml(i.condition)}</small>
            </div>
          `; }).join("")}
        </div>
      </div>

      <div class="gold-recommendation">
        <div>
          <span class="gold-recommend-label">本月建议</span>
          <span class="gold-recommend-amount">${money(spot.recommended_amount)}</span>
        </div>
        <div>
          <span class="chip ${spot.recommended_amount > spot.base_amount ? 'chip-bullish-soft' : 'chip-neutral'}">${spot.recommended_amount > spot.base_amount ? '基础+加仓' : '基础定投'}</span>
          <p style="margin:4px 0 0;font-size:12px">${escapeHtml(spot.recommendation_reason)}</p>
        </div>
      </div>
    </div>
  `;
}

function renderContractRef(contract) {
  var belowMA = contract.above_ma50 === false;
  return `
    <div class="card" style="display:flex;flex-direction:column;gap:18px">
      <div>
        <p class="eyebrow">CONTRACT REFERENCE</p>
        <h3>合约参考</h3>
      </div>

      <div class="gold-price-banner ${belowMA ? 'gold-bearish' : ''}">
        <div><span>XAUT 最新价</span><span class="gold-price-value">${formatNumber(contract.price, 0)}</span></div>
        <span class="chip ${belowMA ? 'chip-bearish' : 'chip-bullish-soft'}">${contract.above_ma50 === true ? 'MA50 上方' : contract.above_ma50 === false ? 'MA50 下方' : '—'}</span>
      </div>

      <div class="gold-tech-grid">
        <div class="gold-tech-tile"><span>MA50</span><b>${formatNumber(contract.ma50_value, 0)}</b></div>
        <div class="gold-tech-tile"><span>MA200</span><b>${formatNumber(contract.ma200_value, 0)}</b>${contract.above_ma200 === false ? '<span class="chip chip-bearish" style="margin-top:2px;font-size:10px">下方</span>' : contract.above_ma200 === true ? '<span class="chip chip-bullish-soft" style="margin-top:2px;font-size:10px">上方</span>' : ''}</div>
        <div class="gold-tech-tile"><span>60 日回撤</span><b>${pct(contract.drawdown_60d)}</b></div>
        <div class="gold-tech-tile"><span>NATR(14)</span><b>${pct(contract.natr_14)}</b></div>
        <div class="gold-tech-tile"><span>成交量 Z</span><b>${formatNumber(contract.volume_zscore, 1)}</b></div>
        <div class="gold-tech-tile"><span>7 日变化</span><b class="${(contract.ret_7d||0)<0?'gold-text-bearish':''}">${pct(contract.ret_7d)}</b></div>
      </div>

      <div>
        <p style="font-weight:600;font-size:13px;margin:0 0 6px">衍生品数据</p>
        <div class="gold-tech-grid">
          <div class="gold-tech-tile"><span>OI 变化(4w)</span><b>${contract.oi_change_4w != null ? pct(contract.oi_change_4w) : '<span class="gold-text-muted">数据积累中</span>'}</b></div>
          <div class="gold-tech-tile"><span>资金费率</span><b>${contract.funding_rate != null ? formatNumber(contract.funding_rate * 100, 4) + "%" : '<span class="gold-text-muted">数据积累中</span>'}</b></div>
          <div class="gold-tech-tile"><span>COT 净多分位</span><b>${contract.cot_net_spec_percentile != null ? formatNumber(contract.cot_net_spec_percentile * 100, 0) + "%" : '<span class="gold-text-muted">待录入</span>'}</b></div>
          <div class="gold-tech-tile"><span>更新时间</span><b>${escapeHtml(String(contract.updated_at || "").slice(0,10) || "—")}</b></div>
        </div>
      </div>
    </div>
  `;
}

function renderGovernance(data) {
  return `
    <div class="card gold-governance">
      <div style="display:flex;gap:28px;font-size:12px">
        <div><span>数据治理</span><br><b>XAUT Gate.io 日线代理</b></div>
        <div><span>K线样本</span><br><b>260 天</b></div>
        <div><span>宏观源</span><br><b>FRED · BLS · ISM</b></div>
      </div>
      <div style="display:flex;gap:14px">
        <span class="status-chip chip-bullish-soft">宏观在线</span>
        <span class="status-chip chip-bullish-soft">XAUT 可用</span>
        <span class="status-chip chip-warning">衍生品暂缺</span>
      </div>
    </div>
  `;
}

function renderShell(data) {
  return `
    ${renderHero(data)}
    ${renderSignalStrip(data?.signals)}
    <div class="gold-workbench">
      ${renderSpotDca(data?.spot || {})}
      ${renderContractRef(data?.contract || {})}
    </div>
    ${renderGovernance(data)}
  `;
}

async function loadData() {
  if (controller) controller.abort();
  controller = new AbortController();
  try { latestData = await api.getGoldV3Allocation({ signal: controller.signal }); } catch (e) { if (e?.name !== "AbortError") console.warn(e); }
  try {
    var deriv = await api.getGoldDerivatives({ signal: controller.signal });
    if (latestData?.contract) Object.assign(latestData.contract, deriv);
  } catch (e) { if (e?.name !== "AbortError") console.warn(e); }
  setRoot(renderShell(latestData || {}));
  document.getElementById("gold-refresh")?.addEventListener("click", function() { loadData().catch(function(e) { console.error(e); }); });
}

export async function renderGoldV4() {
  var ready = loadData().catch(function(e) { if (e?.name !== "AbortError") console.error(e); });
  return { unmount: function() { if (controller) controller.abort(); }, ready: ready };
}
