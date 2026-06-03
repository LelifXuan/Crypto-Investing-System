from __future__ import annotations

import json
import os
import socket
import sys
from importlib.util import find_spec
from pathlib import Path

sys.dont_write_bytecode = True

os.environ.setdefault("APP_DISTRIBUTION_MODE", "portable")
os.environ.setdefault("APP_BUNDLE_ROOT", str(Path(__file__).resolve().parents[1]))
PROJECT_ROOT = Path(os.environ["APP_BUNDLE_ROOT"]).resolve()
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portable_modules import parse_requirements  # noqa: E402

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
    lock_path = app_paths.bundle_root / "portable_runtime.lock.json"
    lock: dict[str, object] = {}
    if lock_path.exists():
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"portable runtime lock is invalid JSON: {exc}")
    else:
        errors.append(f"portable runtime lock missing: {lock_path}")

    expected_version = str(lock.get("python_version", "3.11"))
    expected_major_minor = ".".join(expected_version.split(".")[:2])
    actual_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    if actual_major_minor != expected_major_minor:
        errors.append(
            f"unsupported embedded Python version: expected {expected_major_minor}.x, "
            f"got {actual_major_minor}"
        )

    embedded_dir = app_paths.embedded_python_dir.resolve()
    executable = Path(sys.executable).resolve()
    declared_executable = os.getenv("APP_PYTHON_EXE")
    if declared_executable and Path(declared_executable).resolve() != executable:
        errors.append(f"APP_PYTHON_EXE does not match running interpreter: {declared_executable}")
    try:
        executable.relative_to(embedded_dir)
    except ValueError:
        errors.append(
            "portable preflight must be run with bundled embedded Python: "
            f"expected under {embedded_dir}, got {executable}"
        )

    if not (embedded_dir / "python.exe").exists() and os.name == "nt":
        errors.append(f"embedded python.exe missing: {embedded_dir / 'python.exe'}")
    if not app_paths.immutable_runtime_root.exists():
        errors.append(f"embedded runtime directory missing: {app_paths.immutable_runtime_root}")

    for path in (
        app_paths.runtime_root,
        app_paths.config_dir,
        app_paths.data_dir,
        app_paths.log_dir,
        app_paths.cache_dir,
        app_paths.tmp_dir,
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

    for path in (app_paths.bundle_root, app_paths.templates_dir, app_paths.static_dir):
        if not path.exists():
            errors.append(f"missing bundle path: {path}")

    if app_paths.distribution_mode != "portable":
        errors.append("portable preflight must run with APP_DISTRIBUTION_MODE=portable")

    if not app_paths.portable_env_path.exists():
        warnings.append(f"portable env missing before bootstrap: {app_paths.portable_env_path}")

    if " " in str(app_paths.bundle_root):
        warnings.append("bundle path contains spaces; startup scripts must rely on quoted paths")

    requirements_path = PROJECT_ROOT / "requirements-portable.txt"
    required_modules: list[str] = []
    if requirements_path.exists():
        try:
            required_modules = parse_requirements(requirements_path)
        except Exception as exc:  # pragma: no cover
            errors.append(f"failed to parse requirements-portable.txt: {exc}")
    else:
        errors.append(f"requirements-portable.txt missing: {requirements_path}")
    for module in required_modules:
        if find_spec(module) is None:
            errors.append(f"{module} is not installed in the embedded Python environment")

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
    print(f"- embedded_python: {sys.executable}")
    print(f"- database_path: {app_paths.database_path}")
    print(f"- app_port: {port}")
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
