from datetime import UTC, datetime, timedelta

from app.services.cross_page_consistency import (
    apply_check_to_monitoring_summary,
    compare_published_conclusions,
)

NOW = datetime(2026, 9, 28, 9, 30, tzinfo=UTC)


def _check(
    *,
    monitor_bias="偏多",
    daily="SHORT",
    four_hour="SHORT",
    skew=timedelta(minutes=4),
    strategy_state="fresh",
):
    summary = {
        "regime": "强趋势偏多",
        "bias": monitor_bias,
        "headline": "BTC 偏多。",
        "confidence": 72,
    }
    strategy = {
        "snapshot_key": "published:v3",
        "trade_decision": {"side": "SHORT", "permission": "conditional"},
        "timeframe_stack": [
            {"timeframe": "1d", "direction": daily, "freshness": "fresh", "confidence": 64},
            {"timeframe": "4h", "direction": four_hour, "freshness": "fresh"},
        ],
    }
    verdict = compare_published_conclusions(
        summary,
        strategy,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        monitoring_snapshot_at=NOW,
        strategy_snapshot_at=NOW + skew,
        monitoring_cache_state="fresh",
        strategy_cache_state=strategy_state,
    )
    return summary, strategy, verdict


def test_same_timeframe_opposition_resolves_to_canonical_direction():
    summary, strategy, verdict = _check()
    assert verdict["status"] == "conflict"
    visible = apply_check_to_monitoring_summary(summary, verdict, strategy)
    assert visible["regime"] == "日线偏空"
    assert visible["bias"] == "偏空"
    assert visible["technical_regime"] == "强趋势偏多"
    assert visible["trade_decision"]["side"] == "SHORT"
    assert visible["confidence"] == 64
    assert "日线判断偏空" in visible["headline"]
    assert "冲突" not in visible["headline"]
    assert "cross_page_check" not in visible


def test_timeframe_divergence_is_distinct_from_same_timeframe_conflict():
    _, _, verdict = _check(daily="LONG", four_hour="SHORT")
    assert verdict["status"] == "timeframe_divergence"
    assert verdict["monitoring_direction"] == verdict["strategy_direction"] == "LONG"


def test_aligned_and_stale_snapshots_do_not_report_conflict():
    _, _, aligned = _check(monitor_bias="偏空")
    assert aligned["status"] == "aligned"
    _, _, stale = _check(skew=timedelta(hours=7))
    assert stale["status"] == "stale_sources"
    _, _, stale_state = _check(strategy_state="stale")
    assert stale_state["status"] == "stale_sources"


def test_missing_source_is_unavailable_and_not_actionable():
    verdict = compare_published_conclusions(
        {"bias": "偏多"},
        None,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        monitoring_snapshot_at=NOW,
        strategy_snapshot_at=None,
        monitoring_cache_state="fresh",
        strategy_cache_state="missing",
    )
    assert verdict["status"] == "unavailable"
    visible = apply_check_to_monitoring_summary({"headline": "技术面偏多"}, verdict, None)
    assert "等待后台更新" in visible["headline"]
    assert visible["trade_decision"] is None
