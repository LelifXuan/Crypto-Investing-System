import { escapeHtml } from "../core/dom.js";

function present(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function field(label, input, kind = "neutral") {
  if (!present(input)) return null;
  if (typeof input === "object") {
    if (!present(input.value) && !present(input.label)) return null;
    return {
      label: input.label || label,
      value: input.value ?? input.label,
      detail: input.detail || "",
      status: input.status || kind,
    };
  }
  return { label, value: input, detail: "", status: kind };
}

function renderItem(item) {
  return `
    <div class="workbench-context-item" data-context-status="${escapeHtml(item.status || "neutral")}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(String(item.value))}</strong>
      ${item.detail ? `<small>${escapeHtml(item.detail)}</small>` : ""}
    </div>
  `;
}

function render(model = {}) {
  const items = [
    field("研究对象", model.instrument),
    field("当前值", model.primaryValue),
    field("变化", model.change, "market"),
    field("周期", model.timeframe),
    field("市场状态", model.regime, "market"),
    field("风险", model.marketRisk, "market"),
    field("数据", model.freshness, "unavailable"),
    field("信源", model.sourceSummary, "unavailable"),
  ].filter(Boolean);
  return `
    <section class="workbench-context-rail" aria-label="当前研究上下文">
      ${items.map(renderItem).join("")}
    </section>
  `;
}

export function mountContextRail(container, model = {}) {
  if (!container) return { update() {}, destroy() {} };
  const update = (nextModel = {}) => {
    container.innerHTML = render(nextModel);
  };
  update(model);
  return {
    update,
    destroy() { container.replaceChildren(); },
  };
}
