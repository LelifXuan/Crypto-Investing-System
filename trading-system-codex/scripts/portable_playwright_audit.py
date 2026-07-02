from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROUTES = {
    "monitoring": ("/monitoring-page", "#monitoring-topbar"),
    "indicators": ("/indicators-page", ".analysis-hero-grid"),
    "structure": ("/structure-page", ".structure-page"),
    "events": ("/market-events-page", ".events-hero"),
    "macro": ("/macro-calendar-page", "#macro-summary-cards"),
    "knowledge": ("/knowledge-page", ".knowledge-hero"),
    "ashare_etf": ("/ashare-etf-page", "#etf-overview"),
    "btc_derivatives": ("/btc-derivatives-page", ".btc-derivatives-page"),
    "strategy": ("/strategy-page", ".strategy-toolbar"),
    "gold": ("/gold-allocation-page", ".gold-v3-hero"),
}
VIEWPORTS = ((1440, 900), (1280, 800), (768, 900), (390, 844))


@dataclass
class PageAudit:
    page_id: str
    viewport: str
    url: str
    title: str
    content_ok: bool
    overflow: bool
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    failed_responses: list[str] = field(default_factory=list)
    screenshot: str | None = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_database_path(env_path: Path) -> Path | None:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL=sqlite+aiosqlite:///"):
            return Path(line.split("sqlite+aiosqlite:///", 1)[1]).resolve()
    return None


def _wait_health(base_url: str, timeout_seconds: int = 45) -> None:
    import urllib.request

    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"portable server did not become healthy: {last_error}")


def _start_server(portable_root: Path, port: int) -> tuple[subprocess.Popen[bytes], dict[str, str]]:
    embedded_python = portable_root / "runtime_env" / "python" / "python.exe"
    runtime_root = portable_root / "runtime"
    env = os.environ.copy()
    env.update(
        {
            "APP_DISTRIBUTION_MODE": "portable",
            "APP_BUNDLE_ROOT": str(portable_root),
            "APP_RUNTIME_ROOT": str(runtime_root),
            "APP_PORT": str(port),
            "APP_PYTHON_EXE": str(embedded_python),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(portable_root),
            "BTC_DERIVATIVES_LIVE_ENABLED": "false",
            "LOCAL_BOOTSTRAP_WARMUP_ENABLED": "false",
            "PRECOMPUTE_ENABLED": "false",
        }
    )
    process = subprocess.Popen(
        [
            str(embedded_python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=portable_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_health(f"http://127.0.0.1:{port}")
    return process, env


def _stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _audit_page(
    page: Page,
    *,
    base_url: str,
    page_id: str,
    route: str,
    selector: str,
    width: int,
    height: int,
    screenshots: Path,
) -> PageAudit:
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_responses: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "response",
        lambda response: failed_responses.append(
            f"{response.status} {response.request.method} {response.url}"
        )
        if response.status >= 400
        else None,
    )
    page.set_viewport_size({"width": width, "height": height})
    try:
        page.goto(f"{base_url}{route}", wait_until="domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        page_errors.append(f"navigation timed out: {route}: {exc}")
    try:
        page.locator(selector).wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        page_errors.append(f"content selector timed out: {selector}: {exc}")
    if page_id == "btc_derivatives":
        page.locator("#btc-refresh").click()
        page.wait_for_function(
            """
            () => {
              const button = document.querySelector('#btc-refresh');
              return button && !button.disabled;
            }
            """,
            timeout=45_000,
        )
    metrics = page.evaluate(
        """
        () => ({
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
          contentLength: (document.querySelector('main')?.innerText || '').length,
          errorOverlay: Boolean(document.querySelector(
            '.error-state,.render-fatal,[data-render-fatal]'
          )),
        })
        """
    )
    screenshot_path = screenshots / f"{page_id}-{width}.png"
    if page_id in {"btc_derivatives", "monitoring", "strategy", "gold"}:
        page.screenshot(path=str(screenshot_path), full_page=False)
    else:
        screenshot_path = None
    return PageAudit(
        page_id=page_id,
        viewport=f"{width}x{height}",
        url=page.url,
        title=page.title(),
        content_ok=metrics["contentLength"] > 50 and not metrics["errorOverlay"],
        overflow=metrics["scrollWidth"] > metrics["innerWidth"],
        console_errors=console_errors,
        page_errors=page_errors,
        failed_responses=failed_responses,
        screenshot=str(screenshot_path) if screenshot_path else None,
    )


def run_audit(portable_root: Path, report_path: Path, screenshots: Path) -> dict[str, Any]:
    portable_root = portable_root.resolve()
    screenshots.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    process, _ = _start_server(portable_root, port)
    results: list[PageAudit] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for width, height in VIEWPORTS:
                context = browser.new_context(viewport={"width": width, "height": height})
                for page_id, (route, selector) in ROUTES.items():
                    page = context.new_page()
                    print(f"AUDIT {page_id} {width}x{height}", flush=True)
                    results.append(
                        _audit_page(
                            page,
                            base_url=f"http://127.0.0.1:{port}",
                            page_id=page_id,
                            route=route,
                            selector=selector,
                            width=width,
                            height=height,
                            screenshots=screenshots,
                        )
                    )
                    page.close()
                context.close()
            browser.close()
    finally:
        _stop_server(process)
    env_path = portable_root / "runtime" / "config" / "portable.env"
    expected_database_path = (
        portable_root / "runtime" / "data" / "trading_system.db"
    ).resolve()
    configured_database_path = _portable_database_path(env_path)
    database_path = expected_database_path
    database_inside_runtime = configured_database_path == expected_database_path
    before_restart = {
        "env_sha256": _sha256(env_path),
        "database_size": database_path.stat().st_size,
    }
    restart, _ = _start_server(portable_root, _free_port())
    _stop_server(restart)
    after_restart = {
        "env_sha256": _sha256(env_path),
        "database_size": database_path.stat().st_size,
    }
    failures = [
        asdict(item)
        for item in results
        if not item.content_ok
        or item.overflow
        or item.console_errors
        or item.page_errors
        or item.failed_responses
    ]
    payload = {
        "version": "1.7.0",
        "portable_root": str(portable_root),
        "results": [asdict(item) for item in results],
        "restart_persistence": {
            "before": before_restart,
            "after": after_restart,
            "preserved": before_restart == after_restart,
        },
        "runtime_paths": {
            "database_inside_runtime": database_inside_runtime,
            "configured_database_path": str(configured_database_path),
        },
        "failures": failures,
        "passed": (
            not failures
            and before_restart == after_restart
            and database_inside_runtime
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a synced Portable instance.")
    parser.add_argument("--portable-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    args = parser.parse_args()
    payload = run_audit(args.portable_root, args.report, args.screenshots)
    print(json.dumps({"passed": payload["passed"], "failures": len(payload["failures"])}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
