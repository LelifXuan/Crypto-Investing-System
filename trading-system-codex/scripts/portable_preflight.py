from __future__ import annotations

import os
import socket
import sys
from importlib.util import find_spec
from pathlib import Path

sys.dont_write_bytecode = True

os.environ.setdefault("APP_DISTRIBUTION_MODE", "portable")
os.environ.setdefault("APP_BUNDLE_ROOT", str(Path(__file__).resolve().parents[1]))
PROJECT_ROOT = Path(os.environ["APP_BUNDLE_ROOT"]).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.paths import app_paths, bootstrap_runtime_environment  # noqa: E402


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> int:
    bootstrap_runtime_environment()
    errors: list[str] = []
    warnings: list[str] = []
    port = int(os.getenv("APP_PORT", "8000"))

    if (sys.version_info.major, sys.version_info.minor) not in {(3, 11), (3, 14)}:
        errors.append(
            f"unsupported python version: {sys.version_info.major}.{sys.version_info.minor}"
        )

    for path in (
        app_paths.bundle_root,
        app_paths.runtime_root,
        app_paths.config_dir,
        app_paths.data_dir,
        app_paths.log_dir,
        app_paths.cache_dir,
        app_paths.tmp_dir,
        app_paths.templates_dir,
        app_paths.static_dir,
    ):
        if not path.exists():
            errors.append(f"missing path: {path}")
            continue
        if path.is_dir():
            test_file = path / ".codex_preflight_write_test"
            try:
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
            except Exception as exc:  # pragma: no cover
                errors.append(f"path not writable: {path} ({exc})")

    if app_paths.distribution_mode != "portable":
        errors.append("portable preflight must run with APP_DISTRIBUTION_MODE=portable")

    if not app_paths.portable_env_path.exists():
        warnings.append(f"portable env missing before bootstrap: {app_paths.portable_env_path}")

    if " " in str(app_paths.bundle_root):
        warnings.append("bundle path contains spaces; startup scripts must rely on quoted paths")

    if find_spec("uvicorn") is None:
        errors.append("uvicorn is not installed in the current Python environment")
    if find_spec("fastapi") is None:
        errors.append("fastapi is not installed in the current Python environment")

    try:
        app_paths.database_path.parent.mkdir(parents=True, exist_ok=True)
        with app_paths.database_path.open("ab"):
            pass
    except OSError as exc:
        errors.append(f"database not writable: {app_paths.database_path} ({exc})")

    try:
        from app.main import create_app

        create_app(enable_lifespan=False)
    except Exception as exc:  # pragma: no cover
        errors.append(f"app import/bootstrap failed: {exc}")

    if _port_open("127.0.0.1", port):
        warnings.append(f"port {port} already in use")

    print("Portable preflight")
    print(f"- distribution_mode: {app_paths.distribution_mode}")
    print(f"- runtime_root: {app_paths.runtime_root}")
    print(f"- database_path: {app_paths.database_path}")
    print(f"- app_port: {port}")
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
