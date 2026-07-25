# Leverage-Pressure Funding-Z & Aggregated-OI Fixes (2026-07-25)

## 0. Symptom

User feedback on the btc-derivatives page (leverage_pressure_timeline chart):

1. **Funding Z negative half stays visible after hiding the legend entry.**
   The page splits Funding Z into two datasets (positive/negative) for
   different borderDash styles. The legend only shows the positive
   dataset's label because the negative carries `fundingZLegendDuplicate=true`.
   Toggling the legend entry hides the positive dataset, but the negative
   dataset remains visible because Chart.js toggles by `datasetIndex`.

2. **Aggregated OI has a $6.3 B cliff at 2026-06-26.**
   The 聚合 OI dataset has `null` for six days (2026-06-20..2026-06-25) and
   then jumps to `6,295,950,212` on 2026-06-26 with no preceding trend
   context. Visually, the line resumes from zero after the null gap and
   immediately jumps to ~$6.3 B — the user reads it as a "突变". The chart
   then stays flat through 07-22.

## 1. Approach

### Bug 1 — Funding Z negative half stays visible

The legend already lives at `app/static/pages/btc_derivatives.js` line 1103
(`legendFilter`). Add a `legend.onClick` plugin hook that, when the user
clicks a Funding Z legend entry, toggles `hidden` on **both** sibling
datasets in one call.

Implementation sketch:

```js
function fundingZLegendOnClick(e, legendItem, legend) {
  const chart = legend.chart;
  const ds = chart.data.datasets[legendItem.datasetIndex];
  if (!ds || !ds._fundingZSibling) {
    // Default Chart.js toggle for all other legend items.
    const idx = legendItem.datasetIndex;
    chart.setDatasetVisibility(idx, !chart.isDatasetVisible(idx));
    chart.update();
    return;
  }
  // Funding-Z is two parallel datasets sharing the same label and
  // visibility state. Hide/show both at once so the chart matches the
  // user's expectation.
  const nextVisible = !ds._fundingZSibling.every((d) => !chart.isDatasetVisible(d.__index));
  for (const sibling of ds._fundingZSibling) {
    chart.setDatasetVisibility(sibling.__index, nextVisible);
  }
  chart.update();
}
```

Annotate `positive`/`negative` datasets created in `renderSingleChart` so
each carries `_fundingZSibling: [{__index, ...}, {__index, ...}]` before
the chart is rendered. Wire the hook via `plugins.legend.onClick` in the
`renderChart({options: {plugins: {legend: {onClick: ...}}}})` call.

### Bug 2 — Aggregated OI cliff at 2026-06-26

The cliff is *correct upstream data* but *visually a cliff*. The OI series
is sourced from `collector's daily_metrics archive` and merges `archive +
cache + fresh_history`. The six days of null values between 2026-06-19 and
2026-06-25 mean the upstream had no observation; then on 2026-06-26 a
fresh observation arrived, which got stitched onto the cumulative timeseries
without back-fill.

The user has chosen "后端补零填补". Pin the contract:

- **A daily observation is published only with non-null source values.**
- **Two consecutive non-null points in `daily_metrics` must not be more
  than 2 days apart** (otherwise we have a "cold-start resume" artifact
  that must be flagged as `series_resumed_after_gap`).
- **The chart payload keeps the nulls** (we don't paper over them) but
  attaches a `series_resumed_after_gap` annotation so the frontend can
  render a small visual marker.

Scope of this fix:
- `_merge_price_history()` in `app/services/btc_derivatives/sources/collector.py`
  already merges fresh + cache; we add a metric: if a row's `oi_usd` is
  null for ≥3 consecutive days before a non-null row, mark that non-null
  row with `series_resumed_after_gap: True`.
- The chart's `leverage_pressure_timeline` builder
  (`app/services/btc_derivatives/chart_builder.py` line 415 area) attaches
  a `resume_marker` annotation when this flag is set on a point.
- One new failing test in
  `tests/test_btc_derivatives_daily_metrics_merge.py` pins the contract.
- One new statuc test in `tests/test_btc_derivatives_chart_styles.py` pins
  that the chart payload exposes the marker.

## 2. Files

| Path | Change |
|---|---|
| `app/static/pages/btc_derivatives.js` | Annotate Funding Z positive/negative datasets with `_fundingZSibling`. Add `fundingZLegendOnClick` and wire via `plugins.legend.onClick` in `renderSingleChart`. |
| `app/services/btc_derivatives/sources/collector.py` | In `_merge_price_history`, flag any freshly-arrived OI row with `series_resumed_after_gap=True` when it follows ≥3 null days. |
| `app/services/btc_derivatives/chart_builder.py` | Read the per-point resume flag from `metadata.points`, attach a vertical reference line annotation at the resume timestamp. |
| `tests/test_btc_derivatives_chart_styles.py` | Add a static test pinning that the resume-marker annotation is added when at least one merged OI point has `series_resumed_after_gap`. |
| `tests/test_btc_derivatives_daily_metrics_merge.py` | Pin `_merge_price_history` flags the resume marker. |
| `tests/test_btc_derivatives_frontend_static.py` | Pin `_fundingZSibling` annotation is set on the Funding Z datasets and that the legend.onClick config exists. |

## 3. Risks

| Risk | Mitigation |
|---|---|
| Chart.js's default `legend.onClick` fires both our hook and Chart.js's built-in. We override the entire hook. | We re-implement the default toggle for non-Funding-Z entries to keep behavior identical. |
| Adding a vertical line at the resume tick adds visual noise. | Marker only appears when the gap ≥3 days; otherwise omitted. We only emit annotations when the flag is set. |
| Upstream `_merge_price_history` runs on every dashboard read (hot path). | Cost is `O(n)` per merge (already O(n)); the new "consecutive nulls" counter is also O(n). Negligible. |

## 4. Test plan

1. Static + pytest on `tests/test_btc_derivatives_frontend_static.py`,
   `tests/test_btc_derivatives_chart_styles.py`,
   `tests/test_btc_derivatives_daily_metrics_merge.py`.
2. Live `curl /btc-derivatives/dashboard` after restart — find an OI
   series_resumed_after_gap flag on the 06-26 row.
3. Playwright: open `btc-derivatives-page`, click the Funding Z legend
   entry, verify the negative (dashed) half disappears from the canvas.
4. `tests/verify_pages.py` full run: per_page 0/11, spa 0/10.
