import { escapeHtml } from "../core/dom.js";

const VALID_VARIANTS = new Set(["section", "section-compact", "inline"]);

function dataAttributeName(key) {
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/[^a-zA-Z0-9_-]/g, "-")
    .toLowerCase();
}

function renderDataAttributes(data) {
  return Object.entries(data || {})
    .map(([key, value]) => ` data-${dataAttributeName(key)}="${escapeHtml(value)}"`)
    .join("");
}

/**
 * Render the canonical disclosure control used by section headers.
 * Page modules continue to own business state and the controlled body's
 * `hidden` attribute; this helper owns anatomy, labels and ARIA metadata.
 */
export function renderDisclosureToggle({
  controls,
  expanded = false,
  expandLabel = "展开",
  collapseLabel = "收起",
  variant = "section",
  id = "",
  className = "",
  data = {},
  disabled = false,
} = {}) {
  const safeVariant = VALID_VARIANTS.has(variant) ? variant : "section";
  const classes = [
    "disclosure-toggle",
    `disclosure-toggle--${safeVariant}`,
    className,
  ].filter(Boolean).join(" ");
  const currentLabel = expanded ? collapseLabel : expandLabel;
  const idAttribute = id ? ` id="${escapeHtml(id)}"` : "";
  const controlsAttribute = controls ? ` aria-controls="${escapeHtml(controls)}"` : "";
  const disabledAttribute = disabled ? " disabled aria-disabled=\"true\"" : "";

  return `
    <button${idAttribute}
      class="${escapeHtml(classes)}"
      type="button"
      aria-expanded="${String(Boolean(expanded))}"
      ${controlsAttribute}
      data-disclosure-expand-label="${escapeHtml(expandLabel)}"
      data-disclosure-collapse-label="${escapeHtml(collapseLabel)}"${renderDataAttributes(data)}${disabledAttribute}>
      <span class="disclosure-toggle__label" data-disclosure-label>${escapeHtml(currentLabel)}</span>
      <span class="disclosure-toggle__chevron" aria-hidden="true">
        <svg viewBox="0 0 16 16" focusable="false"><path d="M3.5 6l4.5 4 4.5-4" /></svg>
      </span>
    </button>
  `;
}

/** Keep a rendered disclosure trigger synchronized with page-owned state. */
export function setDisclosureState(button, expanded) {
  if (!button) return;
  const nextExpanded = Boolean(expanded);
  button.setAttribute("aria-expanded", String(nextExpanded));
  const label = button.querySelector("[data-disclosure-label]");
  if (!label) return;
  label.textContent = nextExpanded
    ? button.dataset.disclosureCollapseLabel || "收起"
    : button.dataset.disclosureExpandLabel || "展开";
}
