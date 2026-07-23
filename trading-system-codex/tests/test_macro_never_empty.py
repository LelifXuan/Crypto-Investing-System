from __future__ import annotations

import time
from types import SimpleNamespace

from app.services.macro.fallback_resolver import classify_scoring, fallback_for_indicator
from app.services.network import http_client_factory, proxy_detector
from app.services.network.proxy_detector import (
    ProxyCandidate,
    ProxyDetectionResult,
    safe_proxy_state,
)


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


def test_proxy_detection_short_circuits_after_system_proxy(monkeypatch) -> None:
    monkeypatch.setattr(proxy_detector, "_env_proxy_candidates", lambda: [])
    monkeypatch.setattr(
        proxy_detector,
        "_windows_system_proxy_candidates",
        lambda: [
            ProxyCandidate(
                url="http://127.0.0.1:7890",
                source="windows_system_proxy",
                host="127.0.0.1",
                port=7890,
                protocol="http",
            )
        ],
    )
    monkeypatch.setattr(proxy_detector, "_winhttp_proxy_candidates", lambda: [])

    checked: list[tuple[str, int]] = []

    def fake_port_open(host: str, port: int, timeout: float = 0.08) -> bool:
        checked.append((host, port))
        return True

    monkeypatch.setattr(proxy_detector, "_tcp_port_open", fake_port_open)
    monkeypatch.setattr(
        proxy_detector,
        "_common_port_candidates",
        lambda: (_ for _ in ()).throw(AssertionError("common scan should be skipped")),
    )

    result = proxy_detector.detect_proxy()

    assert result.proxy_detected is True
    assert result.selected_source == "windows_system_proxy"
    assert checked == [("127.0.0.1", 7890)]


def test_proxy_state_writes_to_runtime_config(monkeypatch, tmp_path) -> None:
    from app.core import paths

    monkeypatch.setattr(paths, "app_paths", SimpleNamespace(config_dir=tmp_path))
    result = ProxyDetectionResult(
        proxy_detected=False,
        selected_proxy=None,
        selected_source="none",
        candidates=[],
        checked_at="2026-05-19T00:00:00+00:00",
    )

    written = proxy_detector.write_proxy_state(result)

    assert written == tmp_path / "proxy_state.json"
    assert written.exists()


def test_init_network_fast_path_under_500ms(monkeypatch, tmp_path) -> None:
    result = ProxyDetectionResult(
        proxy_detected=True,
        selected_proxy="http://127.0.0.1:7890",
        selected_source="test",
        candidates=[],
        checked_at="2026-05-19T00:00:00+00:00",
    )
    monkeypatch.setattr(http_client_factory, "detect_proxy", lambda: result)
    monkeypatch.setattr(http_client_factory, "write_proxy_state", lambda _result: tmp_path)

    start = time.perf_counter()
    detected = http_client_factory.init_network()
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert detected is result
    assert elapsed_ms < 500
