/* Shared governance ledger (data governance footer / panel).

   2026-08-27 §13.2 #3 cleanup: prior to this commit the project carried
   five near-duplicate implementations (gold / ashare-etf / btc-derivatives
   / ai-strategy / monitoring) of the same "data governance" ledger
   pattern. Each implementation had its own JSX shape, its own CSS block,
   and small drifts in dot tone mapping, grid column counts, snapshot
   handling, and head column treatment.

   This module is the single source of truth for the rendered HTML; the
   five pages only differ in `variant` (see GOVERNANCE_VARIANTS) and in
   how they prepare the items[] input.

   See docs/design-guidelines.md §7.7 (governance ledger) and §13.2 #3
   (component duplication debt closed).
*/

/* === Variant configuration ============================================
   Each variant captures the per-page differences that survived the §7.7
   audit: grid column density, head column background, h2 font-size,
   eyebrow copy, and whether items can render a snapshot clock SVG.
   The base class owns everything else (border, head padding, dot
   geometry, data-state → tone mapping, responsive collapse). */
export const GOVERNANCE_VARIANTS = Object.freeze({
  gold: {
    id: "gold-governance-title",
    eyebrow: "DATA GOVERNANCE",
    title: "数据就绪与快照",
    headBg: "muted",          // var(--surface-muted)
    gridCols: 4,              // repeat(4, minmax(0, 1fr))
    h2Size: 20,
    itemMinHeight: 72,
    hasSnapshot: true,
    extraClass: "gold-governance",  // preserved as JS hook (gold_v5.js:566)
    extraId: null,
  },
  ashare_etf: {
    id: "etf-governance-title",
    eyebrow: "DATA GOVERNANCE",
    title: "数据就绪与快照",
    headBg: "muted",
    gridCols: 4,
    h2Size: 20,
    itemMinHeight: 72,
    hasSnapshot: true,
    extraClass: "etf-governance",
    extraId: "etf-governance",      // preserved as JS hook (ashare_etf.js:1407)
  },
  btc: {
    id: "btc-governance-title",
    eyebrow: "DATA GOVERNANCE",
    title: "数据就绪与快照",
    headBg: "transparent",          // btc uses transparent head background
    gridCols: "auto-fit-110",       // repeat(auto-fit, minmax(110px, 1fr))
    h2Size: 20,
    itemMinHeight: 72,
    hasSnapshot: true,
    extraClass: "btc-governance",
    extraId: null,
  },
  strategy: {
    id: "strategy-governance-title",
    eyebrow: "DATA ACCESS",
    title: "数据源接入状态",
    headBg: "none",                 // no head background, panel-embedded
    gridCols: 4,
    h2Size: 15,
    itemMinHeight: 92,
    hasSnapshot: false,
    extraClass: "strategy-governance",
    extraId: null,
  },
  monitoring: {
    id: null,                       // monitoring never wired aria-labelledby
    eyebrow: "DATA GOVERNANCE",
    title: "数据源状态",
    headBg: "muted",
    gridCols: "auto-fit-120",
    h2Size: 20,
    itemMinHeight: 72,
    hasSnapshot: false,
    extraClass: "monitoring-governance",
    extraId: null,
  },
});

/* === Public API ====================================================== */

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function escapeGovernanceHtml(value) {
  return escapeHtml(value);
}

/* Render a single ledger item. `slot: "snapshot"` switches the leading
   icon to a clock SVG instead of the status dot. `tone` overrides the
   default dot colour mapping (used by ashare_etf / monitoring where the
   upstream payload provides a more specific tone than data-state alone
   can express). */
export function renderGovernanceItem(item) {
  const state = escapeHtml(item.state || "missing");
  const label = escapeHtml(item.label || "");
  const value = escapeHtml(item.value || "");
  const detail = item.detail ? escapeHtml(item.detail) : "";
  const toneAttr = item.tone ? ` data-tone="${escapeHtml(item.tone)}"` : "";
  const slotClass = item.slot === "snapshot" ? " governance-ledger__snapshot" : "";

  let leadingIcon;
  if (item.slot === "snapshot") {
    leadingIcon = `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 4.5v3.8l2.4 1.4"/></svg>`;
  } else {
    leadingIcon = `<span class="governance-ledger__dot"${toneAttr} aria-hidden="true"></span>`;
  }

  return `
    <article class="governance-ledger__item${slotClass}" data-state="${state}">
      <div class="governance-ledger__label">
        ${leadingIcon}
        <span>${label}</span>
      </div>
      <strong>${value}</strong>
      <small>${detail}</small>
    </article>
  `;
}

/* Render the full ledger <section>. The base class `.governance-ledger`
   and the per-variant modifier `.governance-ledger--{variant}` together
   drive every visual property; CSS lives in editorial.css. */
export function renderGovernanceLedger({
  variant,
  eyebrow: eyebrowOverride,
  title: titleOverride,
  titleId: titleIdOverride,
  readyCount,
  totalCount,
  items,
  extraClassOverride,
} = {}) {
  const cfg = GOVERNANCE_VARIANTS[variant];
  if (!cfg) {
    throw new Error(`governanceLedger: unknown variant "${variant}"`);
  }
  const eyebrow = eyebrowOverride || cfg.eyebrow;
  const title = titleOverride || cfg.title;
  const titleId = titleIdOverride || cfg.id;
  const labelBy = titleId ? ` aria-labelledby="${escapeHtml(titleId)}"` : "";
  const rootClass = [
    "card",
    "governance-ledger",
    `governance-ledger--${variant}`,
    extraClassOverride || cfg.extraClass || "",
  ]
    .filter(Boolean)
    .join(" ");
  const idAttr = cfg.extraId ? ` id="${escapeHtml(cfg.extraId)}"` : "";
  const readyText = `${readyCount}/${totalCount} 个数据源当前可用`;

  const itemsHtml = (items || []).map(renderGovernanceItem).join("");

  return `
    <section${idAttr} class="${rootClass}"${labelBy}>
      <div class="governance-ledger__head">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        ${titleId ? `<h2 id="${escapeHtml(titleId)}">${escapeHtml(title)}</h2>` : `<h2>${escapeHtml(title)}</h2>`}
        <p><strong>${escapeHtml(readyCount)}/${escapeHtml(totalCount)}</strong> ${escapeHtml("个数据源当前可用")}</p>
      </div>
      <div class="governance-ledger__grid">
        ${itemsHtml}
      </div>
    </section>
  `;
}

/* Map a freshness/state string to a chip-style tone override. Pages can
   pre-compute the tone in their adapter and pass it as item.tone; this
   helper is provided for convenience. */
export function defaultToneForState(state) {
  switch (state) {
    case "fresh":
      return "info";
    case "degraded":
    case "stale":
      return "warning";
    case "missing":
    case "unknown":
      return "neutral";
    case "danger":
    case "error":
      return "danger";
    default:
      return null;  // fall back to data-state CSS rules
  }
}