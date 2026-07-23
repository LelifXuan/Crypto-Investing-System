from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

COMMON_PROXY_PORTS = [7890, 7897, 7899, 1080, 10808, 10809, 20170, 2080, 8080]
COMMON_PROXY_HOSTS = ["127.0.0.1"]


@dataclass
class ProxyCandidate:
    url: str
    source: str
    host: str
    port: int
    protocol: str = "http"
    reachable: bool = False


@dataclass
class ProxyDetectionResult:
    proxy_detected: bool
    selected_proxy: Optional[str]
    selected_source: str
    candidates: list[dict]
    checked_at: str


def _tcp_port_open(host: str, port: int, timeout: float = 0.08) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _env_proxy_candidates() -> list[ProxyCandidate]:
    out: list[ProxyCandidate] = []
    for name in [
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
    ]:
        raw = os.getenv(name)
        if not raw:
            continue
        url = raw.strip()
        protocol = url.split(":", 1)[0] if "://" in url else "http"
        host, port = "", 0
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            host = parsed.hostname or ""
            port = int(parsed.port or (443 if protocol == "https" else 80))
        except Exception:
            pass
        if host and port:
            out.append(
                ProxyCandidate(
                    url=url, source=f"env:{name}", host=host, port=port, protocol=protocol
                )
            )
    return out


def _windows_system_proxy_candidates() -> list[ProxyCandidate]:
    if platform.system().lower() != "windows":
        return []
    out: list[ProxyCandidate] = []
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not enabled:
                return []
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            raw = str(proxy_server)
            parts = raw.split(";")
            for part in parts:
                if "=" in part:
                    proto, addr = part.split("=", 1)
                else:
                    proto, addr = "http", part
                if "://" not in addr:
                    addr = f"http://{addr}"
                parsed = urlparse(addr)
                if parsed.hostname and parsed.port:
                    out.append(
                        ProxyCandidate(
                            url=addr,
                            source="windows_system_proxy",
                            host=parsed.hostname,
                            port=int(parsed.port),
                            protocol=proto,
                        )
                    )
    except Exception:
        return []
    return out


def _winhttp_proxy_candidates() -> list[ProxyCandidate]:
    if platform.system().lower() != "windows":
        return []
    try:
        proc = subprocess.run(
            ["netsh", "winhttp", "show", "proxy"],
            capture_output=True,
            text=True,
            timeout=3,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    out: list[ProxyCandidate] = []
    import re

    for host, port in re.findall(r"(127\.0\.0\.1|localhost):([0-9]{2,5})", text):
        url = f"http://{host}:{port}"
        out.append(
            ProxyCandidate(
                url=url, source="winhttp_proxy", host=host, port=int(port), protocol="http"
            )
        )
    return out


def _common_port_candidates() -> list[ProxyCandidate]:
    out: list[ProxyCandidate] = []
    for host in COMMON_PROXY_HOSTS:
        for port in COMMON_PROXY_PORTS:
            for protocol in ["http", "socks5"]:
                out.append(
                    ProxyCandidate(
                        url=f"{protocol}://{host}:{port}",
                        source="common_port_scan",
                        host=host,
                        port=port,
                        protocol=protocol,
                    )
                )
    return out


def _dedupe_candidates(candidates: list[ProxyCandidate]) -> list[ProxyCandidate]:
    seen = set()
    unique: list[ProxyCandidate] = []
    for candidate in candidates:
        key = (candidate.protocol, candidate.host, candidate.port)
        if key in seen or not candidate.host or not candidate.port:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _check_candidates(
    candidates: list[ProxyCandidate],
    *,
    timeout: float = 0.08,
    parallel: bool = False,
) -> list[ProxyCandidate]:
    unique = _dedupe_candidates(candidates)
    if not unique:
        return []
    if not parallel:
        for candidate in unique:
            candidate.reachable = _tcp_port_open(candidate.host, candidate.port, timeout=timeout)
        return unique

    max_workers = min(12, len(unique))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_tcp_port_open, candidate.host, candidate.port, timeout): candidate
            for candidate in unique
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                candidate.reachable = bool(future.result())
            except OSError:
                candidate.reachable = False
    return unique


def _select_proxy(candidates: list[ProxyCandidate]) -> ProxyCandidate | None:
    selected = next(
        (item for item in candidates if item.reachable and item.protocol in {"http", "https"}),
        None,
    )
    if selected is None:
        selected = next((item for item in candidates if item.reachable), None)
    return selected


def detect_proxy() -> ProxyDetectionResult:
    from datetime import datetime, timezone

    checked: list[ProxyCandidate] = []
    priority_candidates = _check_candidates(
        _env_proxy_candidates() + _windows_system_proxy_candidates() + _winhttp_proxy_candidates(),
        timeout=0.08,
    )
    checked.extend(priority_candidates)
    selected = _select_proxy(priority_candidates)
    if selected is None:
        common_candidates = _check_candidates(
            _common_port_candidates(),
            timeout=0.05,
            parallel=True,
        )
        checked.extend(common_candidates)
        selected = _select_proxy(common_candidates)
    return ProxyDetectionResult(
        proxy_detected=selected is not None,
        selected_proxy=selected.url if selected else None,
        selected_source=selected.source if selected else "none",
        candidates=[asdict(c) for c in _dedupe_candidates(checked)[:20]],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def apply_proxy_to_env(result: ProxyDetectionResult) -> None:
    if result.proxy_detected and result.selected_proxy:
        url = result.selected_proxy
        if "://" not in url:
            url = f"http://{url}"
        os.environ.setdefault("HTTPS_PROXY", url)
        os.environ.setdefault("HTTP_PROXY", url)


def redact_proxy_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
    except Exception:
        return "<invalid-proxy-url>"
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    return urlunparse((parsed.scheme or "http", netloc, parsed.path, "", "", ""))


def safe_proxy_state(result: ProxyDetectionResult) -> dict:
    return {
        "proxy_detected": result.proxy_detected,
        "selected_proxy": redact_proxy_url(result.selected_proxy),
        "selected_source": result.selected_source,
        "checked_at": result.checked_at,
        "candidates": [
            {
                **candidate,
                "url": redact_proxy_url(str(candidate.get("url") or "")),
            }
            for candidate in result.candidates
        ],
    }


def write_proxy_state(
    result: ProxyDetectionResult,
    path: Path | None = None,
) -> Path:
    if path is None:
        from app.core.paths import app_paths

        target = app_paths.config_dir / "proxy_state.json"
    else:
        target = path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(safe_proxy_state(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


SOURCE_PROXY_POLICY = {
    "bls": "prefer_proxy",
    "coinmarketcap": "prefer_proxy",
    "fred": "auto",
    "bea": "direct_first",
    "treasury": "direct_first",
    "treasury_fiscaldata": "direct_first",
    "gateio": "direct_first",
    "gateio_rwa": "direct_first",
    "tiingo": "auto",
    "twelvedata": "auto",
    "alpha_vantage": "auto",
    "alphavantage": "auto",
    "openexchangerates": "auto",
    "tushare": "direct_only",
    "zhituapi": "direct_only",
    "agushuju": "direct_only",
    "eastmoney_direct": "direct_only",
    "websearch_cache": "no_network_required",
}


def proxy_for_source(
    source: str, proxy_detected: bool, selected_proxy: Optional[str]
) -> Optional[str]:
    policy = SOURCE_PROXY_POLICY.get(source, "auto")
    if policy == "prefer_proxy":
        return selected_proxy if proxy_detected else None
    if policy == "direct_first":
        return None
    if policy == "direct_only":
        return None
    if policy == "no_network_required":
        return None
    return selected_proxy if proxy_detected else None
