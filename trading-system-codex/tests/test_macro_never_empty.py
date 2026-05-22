from __future__ import annotations

from app.services.macro.fallback_resolver import classify_scoring, fallback_for_indicator
from app.services.network.proxy_detector import ProxyDetectionResult, safe_proxy_state


def test_macro_fallback_placeholder_is_complete_and_unscored() -> None:
    row = fallback_for_indicator("missing_macro_probe", None, "monthly")

    assert row["indicator_id"] == "missing_macro_probe"
    assert row["status"] == "unavailable_placeholder"
    assert row["fallback_level"] == "unavailable_placeholder"
    assert row["value"] is None
    assert row["is_scored"] is False
    assert "不参与评分" in row["score_block_reason"]


def test_macro_scoring_blocks_bad_statuses() -> None:
    for status in ["auth_missing", "rate_limited", "web_cached", "source_error"]:
        allowed, reason = classify_scoring(status, "2026-01-01", "monthly")
        assert allowed is False
        assert reason


def test_proxy_state_redacts_credentials() -> None:
    result = ProxyDetectionResult(
        proxy_detected=True,
        selected_proxy="http://user:pass@127.0.0.1:7890",
        selected_source="env:HTTPS_PROXY",
        candidates=[
            {
                "url": "http://user:pass@127.0.0.1:7890",
                "source": "env:HTTPS_PROXY",
                "host": "127.0.0.1",
                "port": 7890,
                "protocol": "http",
                "reachable": True,
            }
        ],
        checked_at="2026-05-19T00:00:00+00:00",
    )

    state = safe_proxy_state(result)
    assert "pass" not in str(state)
    assert state["selected_proxy"] == "http://127.0.0.1:7890"
