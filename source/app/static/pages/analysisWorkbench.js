import { animateStateChange, animateValueChange, clearRelated } from '../ui/semanticMotion.js';
import { buildAnalysisInspections } from './analysisInspection.js';

/** Page adapter for context, scoped actions, and stable chart updates. */
export function mountAnalysisWorkbench({ root, signal, commands, refresh, busy, observeCharts }) {
  const primary = document.createElement('div');
  primary.className = 'workbench-primary';
  while (root.firstChild) primary.append(root.firstChild);
  // Technical indicators are already self-contained evidence cards and charts.
  // A second detail sidebar duplicated that content and reduced chart width.
  // The context rail that used to sit above this strip was removed for the same
  // reason: instrument / timeframe / regime / data / source were already carried
  // by the hero, the statusbar and the per-chart captions, so the rail cost a
  // full row of vertical space to repeat them.
  root.append(primary);
  const currentUrl = new URL(window.location.href);
  if (currentUrl.searchParams.has('inspect') || currentUrl.searchParams.has('keep')) {
    currentUrl.searchParams.delete('inspect');
    currentUrl.searchParams.delete('keep');
    window.history.replaceState(window.history.state, '', currentUrl);
  }

  const observer = observeCharts(primary, 'analysis-', { signal });
  let contextKey = null;
  let destroyed = false;
  let hasData = false;
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
    beginContext(key) {
      if (contextKey !== null && key !== contextKey) {
        previous.clear();
        chartSnapshots.clear();
        hasData = false;
      }
      contextKey = key;
      root.dataset.analysisContext = key;
      root.dataset.analysisAvailability = hasData ? 'ready' : 'pending';
    },
    update(model) {
      if (destroyed) return;
      primary.querySelector('.analysis-recovery-note')?.remove();
      const items = buildAnalysisInspections(model);
      const current = new Map(items.map((item) => [item.id, item]));
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
      previous.clear();
      chartSnapshots.clear();
      clearRelated(primary);
    },
  };
}
