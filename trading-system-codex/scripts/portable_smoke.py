from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

from release_common import DIST_DIR  # noqa: E402

PORTABLE_ZIP = DIST_DIR / "portable_bundle.zip"
HEALTH_ENDPOINTS = (
    "/health",
    "/monitoring-page",
    "/alerts-page",
    "/structure-page",
    "/api/v1/structure/tab/bundle?instrument_id=btc-usdt-perp&timeframe=1h",
    "/api/v1/alerts/chip-structure?instrument_id=btc-usdt-perp&timeframe=1h",
    "/api/v1/alerts/divergence?instrument_id=btc-usdt-perp&timeframe=1h",
)


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http_ok(base_url: str, path: str, timeout_s: float = 40.0) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"portable smoke check failed for {path}: {last_error}")


def main() -> int:
    if not PORTABLE_ZIP.exists():
        raise SystemExit(f"portable bundle not found: {PORTABLE_ZIP}")

    with tempfile.TemporaryDirectory(prefix="portable-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(PORTABLE_ZIP) as zf:
            zf.extractall(temp_root)

        bundle_root = temp_root / "portable_bundle"
        if not bundle_root.exists():
            extracted = [path for path in temp_root.iterdir() if path.is_dir()]
            if (temp_root / "app").exists() and (temp_root / "scripts").exists():
                bundle_root = temp_root
            elif len(extracted) == 1:
                bundle_root = extracted[0]
            else:
                raise SystemExit("portable bundle extraction failed: cannot determine bundle root")

        runtime_root = bundle_root / "runtime"
        port = pick_port()
        env = os.environ.copy()
        env.update(
            {
                "APP_DISTRIBUTION_MODE": "portable",
                "APP_BUNDLE_ROOT": str(bundle_root),
                "APP_RUNTIME_ROOT": str(runtime_root),
                "APP_PORT": str(port),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            }
        )

        subprocess.run(
            [sys.executable, str(bundle_root / "scripts" / "portable_preflight.py")],
            cwd=bundle_root,
            env=env,
            check=True,
        )

        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=bundle_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            for endpoint in HEALTH_ENDPOINTS:
                wait_http_ok(base_url, endpoint)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()
                server.wait(timeout=5)

    print("portable smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
