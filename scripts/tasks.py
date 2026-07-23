from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PYTHONS = {(3, 11), (3, 14)}
DEV_COMMANDS = {"install", "dev", "dev-local", "test", "lint", "check", "release-v18"}
COMMAND_DEPENDENCIES = {
    "dev": ("uvicorn",),
    "dev-local": ("uvicorn",),
    "test": ("pytest",),
    "lint": ("ruff",),
    "check": ("ruff", "pytest"),
    "release-v18": ("ruff", "pytest", "playwright"),
}


class TaskError(RuntimeError):
    """Raised when a task cannot run in the current environment."""


def format_python_version(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def active_python_version() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def format_supported_pythons() -> str:
    ordered = sorted(SUPPORTED_PYTHONS)
    return " or ".join(format_python_version(version) for version in ordered)


def ensure_supported_python(command: str) -> None:
    if command not in DEV_COMMANDS:
        return
    if active_python_version() in SUPPORTED_PYTHONS:
        return
    raise TaskError(
        f"{command} requires Python {format_supported_pythons()}. "
        f"Current interpreter is {format_python_version(active_python_version())} "
        f"at {sys.executable}."
    )


def in_virtualenv() -> bool:
    return sys.prefix != sys.base_prefix


def ensure_virtualenv(command: str) -> None:
    if command not in DEV_COMMANDS:
        return
    if in_virtualenv():
        return
    raise TaskError(
        f"{command} must run inside an activated virtual environment. "
        "The project now runs against the active Python interpreter with "
        "its dependencies installed there (e.g. `pip install -r "
        "requirements.txt`). On Windows you can also run "
        "`scripts\\dev_env.ps1 -StartServer`."
    )


def ensure_dependencies(command: str) -> None:
    missing = [
        name
        for name in COMMAND_DEPENDENCIES.get(command, ())
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        formatted = ", ".join(sorted(missing))
        raise TaskError(
            f"Missing required tools for {command}: {formatted}. "
            "Run `python scripts/tasks.py install` from an activated supported virtual environment."
        )


def run_step(args: list[str]) -> None:
    completed = subprocess.run(args, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run_step_with_env(
    args: list[str],
    extra_env: dict[str, str],
    *,
    cwd: Path = PROJECT_ROOT,
) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    completed = subprocess.run(args, cwd=cwd, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def ensure_node_for_check() -> None:
    if shutil.which("node"):
        return
    raise TaskError(
        "check requires `node` on PATH so browser page modules can be syntax-checked. "
        "Install Node.js, reopen the terminal, then re-run `python scripts/tasks.py check`."
    )


def _collect_frontend_files() -> list[str]:
    static_root = PROJECT_ROOT / "app" / "static"
    if not static_root.is_dir():
        return []
    paths: list[str] = []
    for js_file in sorted(static_root.rglob("*.js")):
        rel = str(js_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        paths.append(rel)
    return paths


def build_check_steps() -> list[list[str]]:
    steps = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "compileall", "app", "tests", "scripts/tasks.py"],
        [sys.executable, "-c", "import app.main"],
    ]
    for path in _collect_frontend_files():
        steps.append(["node", "--check", path])
    return steps


def run_install() -> None:
    run_step([sys.executable, "-m", "pip", "install", "-e", ".[dev]"])


def _port_from_env_or_default(default: int) -> int:
    raw = os.getenv("APP_PORT")
    if raw is None or raw.strip() == "":
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise TaskError(f"APP_PORT must be an integer, got {raw!r}.") from exc
    if not 1 <= port <= 65535:
        raise TaskError(f"APP_PORT must be between 1 and 65535, got {port}.")
    return port


def _can_bind_localhost(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _select_dev_port(preferred: int, *, fallback_span: int = 20) -> int:
    for port in range(preferred, min(preferred + fallback_span, 65536)):
        if _can_bind_localhost(port):
            return port
    raise TaskError(
        f"No available localhost port found in range {preferred}-"
        f"{min(preferred + fallback_span - 1, 65535)}."
    )


def run_dev(port: int) -> None:
    requested_port = _port_from_env_or_default(port)
    selected_port = _select_dev_port(requested_port)
    if selected_port != requested_port:
        print(
            f"Port {requested_port} is unavailable; using {selected_port} instead.",
            flush=True,
        )
    print(f"Starting dev server at http://127.0.0.1:{selected_port}", flush=True)
    run_step(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(selected_port),
            "--reload",
        ]
    )


def run_test() -> None:
    run_step([sys.executable, "-m", "pytest", "-q"])


def run_lint() -> None:
    run_step([sys.executable, "-m", "ruff", "check", "."])


def run_check() -> None:
    ensure_node_for_check()
    steps = build_check_steps()
    passed = 0
    for i, step in enumerate(steps):
        label = f"[{i + 1}/{len(steps)}] {' '.join(step[:3])}..."
        try:
            run_step(step)
            passed += 1
        except SystemExit:
            print(f"  FAILED: {label}")
    print(f"\n===== check complete: {passed}/{len(steps)} steps passed =====")
    if passed < len(steps):
        raise SystemExit(1)


def run_clean() -> None:
    run_step([sys.executable, "scripts/clean_workspace.py"])


def run_release_zip() -> None:
    run_step([sys.executable, "scripts/create_release_zip.py"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project task runner for local Windows-first development."
    )
    parser.add_argument(
        "command",
        choices=[
            "install",
            "dev",
            "dev-local",
            "test",
            "lint",
            "check",
            "clean",
            "release-zip",
        ],
    )
    return parser.parse_args()


def main() -> int:
    command = parse_args().command
    try:
        ensure_supported_python(command)
        ensure_virtualenv(command)
        ensure_dependencies(command)
        {
            "install": run_install,
            "dev": lambda: run_dev(8000),
            "dev-local": lambda: run_dev(8002),
            "test": run_test,
            "lint": run_lint,
            "check": run_check,
            "clean": run_clean,
            "release-zip": run_release_zip,
        }[command]()
    except TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
