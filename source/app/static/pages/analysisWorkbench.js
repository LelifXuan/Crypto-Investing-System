import { animateStateChange, animateValueChange, clearRelated } from '../ui/semanticMotion.js';
import { mountContextRail } from '../ui/contextRail.js';
import { buildAnalysisInspections } from './analysisInspection.js';

/** Page adapter for context, scoped actions, and stable chart updates. */
export function mountAnalysisWorkbench({ root, signal, commands, refresh, busy, observeCharts }) {
  const railHost = document.createElement('div');
  railHost.id = 'analysis-context-rail';
  const primary = document.createElement('div');
  primary.className = 'workbench-primary';
  while (root.firstChild) primary.append(root.firstChild);
  // Technical indicators are already self-contained evidence cards and charts.
  // A second detail sidebar duplicated that content and reduced chart width.
  root.append(railHost, primary);
  const currentUrl = new URL(window.location.href);
  if (currentUrl.searchParams.has('inspect') || currentUrl.searchParams.has('keep')) {
    currentUrl.searchParams.delete('inspect');
    currentUrl.searchParams.delete('keep');
    window.history.replaceState(window.history.state, '', currentUrl);
  }

  const rail = mountContextRail(railHost, {});
  const observer = observeCharts(primary, 'analysis-', { signal });
  let contextKey = null;
  let destroyed = false;
  let hasData = false;
  let railModel = {};
  let previous = new Map();
  const chartSnapshots = new Map();
  const disposers = [];
  const focus = (selector) => () => {
    const element = primary.querySelector(selector);
    element?.scrollIntoView({ block: 'center' });
    element?.focus();
  };

  for (const command of [
    { id: 'analysis:refresh', label: '刷新技术指标', enabled: () => !busy(), run: refresh },
    { id: 'analysis:focus-instrument', label: '聚焦分析品种', run: focus('.instrument-pill.is-active') },
    { id: 'analysis:focus-timeframe', label: '聚焦分析周期', run: focus('[data-dropdown-id="analysis-timeframe"]') },
    { id: 'analysis:focus-window', label: '聚焦分析窗口', run: focus('[data-dropdown-id="analysis-window"]') },
  ]) if (commands) disposers.push(commands.register(command));

  const note = (message) => {
    let element = primary.querySelector('.analysis-recovery-note');
    if (!element) {
      element = document.createElement('p');
      element.className = 'analysis-recovery-note';
      element.setAttribute('role', 'status');
      primary.prepend(element);
    }
    element.textContent = message;
  };

  return {
    syncRelations() { clearRelated(primary); },
    hasData: () => hasData,
    beginContext(key, model) {
      if (contextKey !== null && key !== contextKey) {
        previous.clear();
        chartSnapshots.clear();
        hasData = false;
      }
      contextKey = key;
      root.dataset.analysisContext = key;
      root.dataset.analysisAvailability = hasData ? 'ready' : 'pending';
      if (!hasData) {
        rail.update({ ...model, freshness: { value: '等待分析快照', status: 'unavailable' } });
      }
    },
    update(model) {
      if (destroyed) return;
      primary.querySelector('.analysis-recovery-note')?.remove();
      const items = buildAnalysisInspections(model);
      const current = new Map(items.map((item) => [item.id, item]));
      railModel = {
        ...model.context,
        regime: model.bundle.mode || undefined,
        freshness: {
          value: model.bundle.data_ts || model.bundle.snapshot_at || '时间未知',
          status: items[0]?.sources[0]?.status || 'unavailable',
        },
        sourceSummary: {
          value: '分析快照',
          status: items[0]?.sources[0]?.status || 'unavailable',
        },
      };
      rail.update(railModel);
      primary.querySelectorAll('[data-workbench-id]').forEach((element) => {
        const dto = current.get(element.dataset.workbenchId);
        const old = previous.get(dto?.id);
        // Cards remain readable content, not hidden triggers for another panel.
        element.removeAttribute('role');
        element.removeAttribute('aria-label');
        element.removeAttribute('tabindex');
        if (old && dto) {
          animateValueChange(
            element.querySelector('.signal-value') || element,
            JSON.stringify(old.current),
            JSON.stringify(dto.current),
            { signal },
          );
          animateStateChange(
            element.querySelector('.signal-copy') || element,
            old.interpretation,
            dto.interpretation,
            { signal },
          );
        }
      });
      previous = current;
      hasData = true;
      root.dataset.analysisAvailability = 'ready';
      clearRelated(primary);
    },
    failed() {
      if (destroyed) return;
      if (hasData) {
        rail.update({
          ...railModel,
          freshness: { ...railModel.freshness, status: 'stale' },
          sourceSummary: { value: '分析快照 · 刷新失败', status: 'stale' },
        });
        note('刷新失败，保留最近有效分析快照。');
      } else {
        root.dataset.analysisAvailability = 'unavailable';
        note('分析快照暂不可用，可手动刷新重试。');
      }
    },
    chartConfig(key, config) {
      const signature = JSON.stringify(config.data);
      if (chartSnapshots.get(key) === signature) return null;
      if (chartSnapshots.has(key)) config.options = { ...config.options, animation: false };
      chartSnapshots.set(key, signature);
      return config;
    },
    destroy() {
      destroyed = true;
      disposers.forEach((dispose) => dispose());
      delete root.dataset.analysisContext;
      delete root.dataset.analysisAvailability;
      observer.disconnect();
      rail.destroy();
      previous.clear();
      chartSnapshots.clear();
      clearRelated(primary);
    },
  };
}
