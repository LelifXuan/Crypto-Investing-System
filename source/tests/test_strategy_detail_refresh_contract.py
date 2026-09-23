"""Guards for the strategy detail drawer's refresh contract (2026-09-22).

The drawer used to render one payload and stop. When the read path reported a
queued rebuild the panel kept the promise on screen ("正在重新推演") with nothing
behind it, so the user waited minutes and nothing ever arrived. Two rules:

1. A payload that is still being built (missing / warming / expired snapshot)
   is re-read on a bounded timer, and the panel says it is refreshing.
2. A payload that is fresh, but whose plan the live mark price has already left
   behind, is terminal — the plan's levels are structural, so re-reading returns
   the same answer. That state must not advertise a recompute, and it needs a
   manual way out.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "app/static/pages/strategy/renderDetailPanel.js"
SCAN_PAGE = ROOT / "app/static/pages/strategy/index.js"


def _panel_source() -> str:
    return PANEL.read_text(encoding="utf-8")


def _pending_helper_module() -> str:
    source = _panel_source()
    start = source.index("function hasPublishedDetail")
    end = source.index("function renderPendingDetail")
    return source[start:end]


def _rebuild_pending(model) -> bool:
    if shutil.which("node") is None:
        pytest.skip("node not available")
    script = (
        _pending_helper_module()
        + f"\nconsole.log(JSON.stringify(detailRebuildPending({json.dumps(model)})));\n"
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode == 0, f"node failed: {result.stderr}"
    return bool(json.loads(result.stdout.strip()))


def _published_snapshot() -> dict:
    return {
        "market_decision_snapshot": {"snapshot_id": "eth-usdt-perp:abc"},
        "timeframe_stack": [{"timeframe": "1d"}],
    }


def test_missing_snapshot_is_treated_as_still_building():
    assert _rebuild_pending({"cache_state": "missing"}) is True
    assert _rebuild_pending({"cache_state": "stale"}) is True
    assert _rebuild_pending({"cache_state": "warming"}) is True


def test_fresh_snapshot_with_an_invalidated_plan_is_not_polled():
    """Nothing is queued for this state — polling would repeat the same answer."""
    model = _published_snapshot() | {"cache_state": "fresh", "recompute_status": "enqueued"}
    assert _rebuild_pending(model) is False


def test_forced_rebuild_response_without_a_cache_state_is_not_polled():
    model = _published_snapshot() | {"recompute_status": "complete"}
    assert _rebuild_pending(model) is False


def test_unpublished_payload_without_a_cache_state_is_still_building():
    assert _rebuild_pending({"cache_state": "", "status": "degraded"}) is True


def test_panel_polls_on_a_bounded_timer_and_stops_on_close():
    source = _panel_source()

    assert "REFRESH_MAX_ATTEMPTS" in source
    assert "scheduleRefreshPoll" in source
    assert "setRefreshNote" in source
    # The poll must be cancelled when the drawer closes, otherwise it keeps
    # hitting the API after the user navigated away (AGENTS.md §九.2).
    close_start = source.index("const close = () => {")
    close_end = source.index('overlay.addEventListener("click", close)')
    assert "stopRefreshPoll()" in source[close_start:close_end]


def test_drawer_always_offers_a_manual_rebuild():
    source = _panel_source()

    assert 'id="strategy-detail-rebuild"' in source
    assert "重新推演" in source
    # The terminal invalidation state has no automatic recovery, so the header
    # action must not be conditional on `degraded` / `pending`.
    header_start = source.index("strategy-detail-header-actions")
    header = source[header_start:source.index("</div>", header_start)]
    assert "strategy-detail-rebuild" in header


def test_invalidated_plan_copy_no_longer_promises_a_rerun():
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    plan = (ROOT / "app/static/pages/strategy/renderExecutionPlan.js").read_text(encoding="utf-8")
    guard = (ROOT / "app/services/strategy_unified/trade_decision.py").read_text(encoding="utf-8")

    assert 'SETUP_INVALIDATED: "候选计划已失效",' in adapter
    assert 'INVALIDATED: "候选计划已失效",' in plan
    assert "正在重新推演。" not in adapter
    # The service layer cannot know whether a rebuild was queued.
    assert "旧计划已作废，正在重新推演。" not in guard
    assert "旧计划已作废。" in guard


def test_recompute_status_is_shown_in_user_words():
    audit = (ROOT / "app/static/pages/strategy/renderDecisionAudit.js").read_text(encoding="utf-8")

    assert "humanizeRecomputeStatus" in audit
    assert "escapeHtml(model.recompute_status)" not in audit


def _without_comments(source: str) -> str:
    """Strip `//` comments — several of these guards name the thing they ban."""
    return "\n".join(line.split("//", 1)[0] for line in source.splitlines())


def test_poll_bypasses_the_client_response_cache():
    """A plain unforced read is served from api.js's 30 s client cache.

    The poll would re-read the drawer's own stale copy, see no change, and give
    up while the fresh snapshot was already published server-side.
    """
    panel = _panel_source()
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    assert "loadStrategy(instrumentId, timeframe, { bypassCache: true })" in panel
    assert "const bypassCache = loadOpts.bypassCache ?? false;" in index
    assert "api.getUnifiedStrategy(iid, { force, bypassCache," in index


def test_drawer_uses_the_shared_datetime_formatter():
    panel = _panel_source()

    # The pass-through stub printed raw ISO strings
    # ("2026-09-22T09:20:45.583117+00:00") for 生成时间 / 策略时间 / 价格时间.
    assert 'formatDateTime: (v) => v || "-",' not in panel
    assert "  formatDateTime,\n" in panel


def test_scan_failure_renders_into_the_live_panels_and_uses_a_realistic_budget():
    source = _without_comments(SCAN_PAGE.read_text(encoding="utf-8"))

    # `#strategy-scan-status` does not exist in the scanned shell: writes to it
    # were no-ops, so a failed scan left the loading dots up forever.
    assert "strategy-scan-status" not in source
    assert "renderScanError" in source
    assert '"strategy-scan-matrix"' in source
    # A forced scan rebuilds every instrument serially (~84 s measured for a
    # 13-instrument universe); the old 60 s budget aborted it every time.
    force_timeout = int(
        source.split("const FORCE_SCAN_TIMEOUT_MS = ", 1)[1].split(";", 1)[0]
    )
    assert force_timeout >= 180000
