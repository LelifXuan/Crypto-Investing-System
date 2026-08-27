from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_monitoring_tracks_backend_refresh_and_rereads_snapshot() -> None:
    source = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    assert "bundle?.refresh_task_key" in source
    assert "waitForPrecomputeTask(taskKey" in source
    assert "getMonitoringDashboard(instrumentId, timeframe, {" in source
    assert "force: true" in source
    assert "signal: controller.signal" in source


def test_shared_precompute_polling_is_abortable() -> None:
    source = (ROOT / "app/static/core/precompute.js").read_text(encoding="utf-8")
    assert "export async function waitForPrecomputeTask" in source
    assert "signal?.aborted" in source
    assert 'status?.status === "error"' in source
    assert 'status?.status === "missing"' in source


def test_public_precompute_priorities_remain_in_range() -> None:
    source = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
    warmup = source[source.index("function queueWarmup"):source.index("function bindRefreshButton")]
    assert "priority: 5" in warmup
    assert "priority: 20" not in warmup
