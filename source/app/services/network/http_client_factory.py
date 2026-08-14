from __future__ import annotations

import threading
from typing import Any

import httpx

from app.services.network.proxy_detector import (
    ProxyDetectionResult,
    detect_proxy,
    proxy_for_source,
    safe_proxy_state,
    write_proxy_state,
)

_LOCK = threading.Lock()
_PROXY_STATE: ProxyDetectionResult | None = None


def init_network() -> ProxyDetectionResult:
    """Detect proxy once and persist a redacted state file for diagnostics."""

    result = get_proxy_state(force=True)
    write_proxy_state(result)
    return result


def get_proxy_state(*, force: bool = False) -> ProxyDetectionResult:
    global _PROXY_STATE
    with _LOCK:
        if force or _PROXY_STATE is None:
            _PROXY_STATE = detect_proxy()
            write_proxy_state(_PROXY_STATE)
        return _PROXY_STATE


def client_for_source(
    source_key: str,
    *,
    timeout: float | httpx.Timeout = 20,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create an AsyncClient using the configured per-source proxy policy.

    The factory never requires users to set HTTPS_PROXY manually. It detects
    local proxies automatically, applies them only to sources that should use
    them, and stores only redacted diagnostic state.
    """

    result = get_proxy_state()
    proxy = proxy_for_source(source_key, result.proxy_detected, result.selected_proxy)
    client_kwargs: dict[str, Any] = {"timeout": timeout, **kwargs}
    if headers:
        client_kwargs["headers"] = headers
    if proxy and proxy.startswith(("http://", "https://")):
        client_kwargs["proxy"] = proxy
    return httpx.AsyncClient(**client_kwargs)


def current_network_status() -> dict[str, Any]:
    return safe_proxy_state(get_proxy_state())
