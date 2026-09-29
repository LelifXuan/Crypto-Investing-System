"""Build the portable application bundle from the workspace.

The bundle ships application code plus the embedded Windows runtime and never
credentials: ``source/.env`` is a local-machine artifact that this builder
neither requires, reads, nor includes. After the archive is written it is
re-opened and scanned again by a secret gate — any credential-like filename,
or a non-placeholder value behind a sensitive variable name in a config-surface
file, fails the build and deletes the artifact. Gate messages name the file,
line, and variable only; secret values are never printed.

Runtime caches are excluded by path, not by the word 'cache', because
app/cache is application source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

PREFIX = "CIS-Workbench-UI2/"
EXCLUDED_DIRS = {
    ".git",
    ".zcode",
    ".agents",
    ".venv",
    "node_modules",
    "runtime_python",
    "runtime_dev",
    "runtime",
    "runtime_env",
    "dist",
    "logs",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "reports",
    "screenshots",
    ".local_secrets",
    "_codex_secret_backups",
    ".opencode_backups",
    ".cache",
}
EXCLUDED_SUFFIXES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".sqlite",
    ".sqlite3",
    ".sqlite3-wal",
    ".sqlite3-shm",
    ".log",
    ".pyc",
    ".pyo",
    ".zip",
    ".7z",
    ".pem",
    ".key",
    ".pfx",
)

# --- P0-SEC-001 credential isolation gate -----------------------------------
# Filenames that look like credential bundles are rejected outright; the .env
# family is allowed only for explicit template names. Placeholder-only values
# behind sensitive variable names pass; anything else fails the build.
ALLOWED_ENV_BASENAMES = {".env.example", ".env.template", ".env.sample"}
CREDENTIAL_STEMS = {"credentials", "secrets"}
CREDENTIAL_SUFFIXES = {"pem", "key", "pfx"}
SCAN_SUFFIXES = {
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".example",
    ".template",
    ".sample",
    ".bat",
    ".cmd",
    ".ps1",
    ".json",
}
SENSITIVE_NAME = re.compile(
    r"[A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET|SECRET_ID|SECRET_KEY"
    r"|TOKEN|PASSWORD|PASSWD|PASSPHRASE|ACCESS_TOKEN|APP_ID)"
)
SENSITIVE_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?\"?([A-Z0-9_]+)\"?\s*[=:]\s*(.+?)\s*$")
PLACEHOLDER_VALUE = re.compile(
    r"^(?:change[-_]?me|your[_-].*|xxx+|<[^>]*>|\$\{[^}]*\}|example[^a-z0-9]?.*|placeholder.*"
    r"|dummy.*|sample.*|test.*|none|null|true|false|0|1)$",
    re.IGNORECASE,
)

# Public artifacts that legitimately live inside the embedded runtime and are
# not credential material: stdlib/module *source* files named secrets.py, and
# certifi's public CA bundle. Scoped to the runtime_python directory only —
# the same names anywhere else in the tree still fail the gate.
RUNTIME_PUBLIC_DIRNAME = "runtime_python"
RUNTIME_PUBLIC_BASENAMES = {"secrets.py", "cacert.pem"}


def _runtime_public_artifact(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if RUNTIME_PUBLIC_DIRNAME not in parts:
        return False
    return PurePosixPath(name).name.lower() in RUNTIME_PUBLIC_BASENAMES


class SecretGateError(RuntimeError):
    """Raised when a distribution manifest contains credential material."""


def credential_filename_violation(name: str) -> str | None:
    """Return the offending basename when *name* looks like a credential file."""
    lower = PurePosixPath(name).name.lower()
    if lower in ALLOWED_ENV_BASENAMES:
        return None
    if lower == ".env" or lower.startswith(".env."):
        return lower
    stem, _, suffix = lower.rpartition(".")
    if stem in CREDENTIAL_STEMS or (not stem and lower in CREDENTIAL_STEMS):
        return lower
    if suffix in CREDENTIAL_SUFFIXES:
        return lower
    return None


def _should_content_scan(name: str) -> bool:
    lower = PurePosixPath(name).name.lower()
    return lower.startswith(".env") or PurePosixPath(name).suffix.lower() in SCAN_SUFFIXES


def collect_secret_violations(names, read_text) -> list[str]:
    """Collect gate violations for *names*; values are never included."""
    violations: list[str] = []
    for name in sorted(names):
        if _runtime_public_artifact(name):
            continue
        reason = credential_filename_violation(name)
        if reason:
            violations.append(f"{name}: credential-like filename ({reason})")
            continue
        if not _should_content_scan(name):
            continue
        text = read_text(name)
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = SENSITIVE_ASSIGNMENT.match(line)
            if not match or not SENSITIVE_NAME.fullmatch(match.group(1)):
                continue
            value = match.group(2).strip().strip('"').strip("'")
            if value and not PLACEHOLDER_VALUE.match(value):
                violations.append(
                    f"{name}:{line_no}: sensitive variable {match.group(1)} "
                    "has a non-placeholder value (value not shown)"
                )
    return violations


def run_secret_gate(names, read_text) -> None:
    violations = collect_secret_violations(names, read_text)
    if violations:
        raise SecretGateError(
            "secret gate failed for distribution manifest:\n" + "\n".join(violations[:20])
        )


def include_source(name: str) -> bool:
    path = PurePosixPath(name)
    if EXCLUDED_DIRS.intersection(path.parts) or path.name.lower() in {"nul", ".coverage"}:
        return False
    if path.name.endswith(EXCLUDED_SUFFIXES):
        return False
    if path.name.lower().startswith(".env"):
        return path.name.lower() in ALLOWED_ENV_BASENAMES
    return True


NOTES = """# CIS UI 2.0 — {delivery}（内部便携包）

{security_notice}
包含 Windows Python 3.11、依赖、当前工作区代码；无需安装系统 Python。
完整解压后双击 start.bat，访问 http://127.0.0.1:8002/monitoring-page。
按 Ctrl+C 停止服务。不要直接从压缩包内部启动。

不含历史数据库、运行缓存、日志、验收截图，也不含任何密钥或凭证；
app/cache 是业务源码，已保留。
启动器将运行目录与数据库限定在当前解压目录。没有历史数据时显示构建中或降级状态。
需要第三方数据源时，请自行复制 source/.env.example 为 source/.env 并填写密钥；
禁止把真实密钥放回交付目录后重新打包。
本包不代表外部数据源可用性认证。
正式 Workbench 页面：{workbench_pages}；不是完整 P2 页面迁移交付。
旧版本首次升级后请 Ctrl+Shift+R 一次；之后 HTML 与子模块自动协商缓存更新。
"""


def package_notes(manifest: dict) -> str:
    """Derive warnings from the actual manifest, never from a stale release label."""
    encryption = "ZIP 已加密" if manifest["encrypted"] else "ZIP 未加密"
    contents = (
        "包含原样 source/.env 和密钥" if manifest["contains_secrets"] else "不包含任何密钥或凭证"
    )
    return NOTES.format(
        delivery=manifest["delivery"],
        security_notice=f"警告：{encryption}，{contents}。仅限授权内部使用，禁止公开上传。",
        workbench_pages="、".join(manifest["workbench_pages"]),
    )


START = (
    r"""@echo off
setlocal
cd /d "%~dp0source"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "APP_RUNTIME_ROOT=%~dp0source\runtime"
set "DATABASE_URL=sqlite+aiosqlite:///%APP_RUNTIME_ROOT:\=/%/data/trading_system.db"
if not exist "runtime_python\python.exe" (
  echo [ERROR] Please extract the complete bundle.
  pause
  exit /b 1
)
"runtime_python\python.exe" -c "import fastapi,sqlalchemy,uvicorn,httpx"
if errorlevel 1 exit /b 1
echo PORTABLE PACKAGE - NO CREDENTIALS INCLUDED
if not exist ".env" echo [NOTICE] No source\.env found: key-backed sources will run degraded. """
    r"""Copy .env.example to .env and fill in your own keys.
"runtime_python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8002
pause
"""
)


def build(root: Path, destination: Path) -> dict:
    root = root.resolve()
    runtime = root / "source/runtime_python"
    if not (runtime / "python.exe").is_file():
        raise RuntimeError("Missing embedded Python runtime (source/runtime_python)")
    git_env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            env=git_env,
        )
        .decode("utf-8")
        .split("\0")
    )
    files = {name: root / name for name in names if name and include_source(name)}
    files = {name: path for name, path in files.items() if path.is_file() and not path.is_symlink()}
    for path in runtime.rglob("*"):
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts:
            if path.suffix not in {".pyc", ".pyo", ".log"}:
                files[path.relative_to(root).as_posix()] = path
    extras = {
        "start.bat": START.replace("\n", "\r\n").encode("ascii"),
    }
    if "source/README.md" not in files:
        extras["source/README.md"] = (root / "README.md").read_bytes()
    dependency_json = subprocess.check_output(
        [
            str(runtime / "python.exe"),
            "-c",
            "import sys,json,importlib.metadata as m; "
            "print(json.dumps({'python':sys.version,'packages':"
            "{d.metadata['Name']:d.version for d in m.distributions()}}))",
        ],
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
    )
    manifest = {
        "kind": "private-windows-portable",
        "contains_secrets": False,
        "secret_gate": "fail-closed scan before and after archive write",
        "encrypted": False,
        "delivery": "P1 Frozen + P2 Operator Core + Analysis/Structure Migration",
        "application_version": tomllib.loads(
            (root / "source/pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"],
        "ui_release": "V2.3",
        "workbench_pages": ["Monitoring", "BTC", "Events", "Macro", "Analysis", "Structure"],
        "stage_acceptance": {
            "H0": "PASS / FROZEN", "H1": "PASS / FROZEN", "H2": "PASS / FROZEN",
            "H3": "PASS / FROZEN", "H4": "PASS / FROZEN",
        },
        "acceptance_record": "docs/ui2-page-migration-acceptance.md",
        "strategy": "ADR 0023: existing Detail Panel plus four commands; no Inspector",
        "full_p2_migration": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, env=git_env, text=True
        ).strip(),
        "runtime": json.loads(dependency_json),
        "files": {},
    }
    extras["PACKAGE-README.md"] = package_notes(manifest).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def fail_closed(message: str) -> SecretGateError:
        destination.unlink(missing_ok=True)
        destination.with_suffix(".zip.sha256").unlink(missing_ok=True)
        return SecretGateError(message)

    # Gate 1: pre-write scan over the staged file list.
    run_secret_gate(
        files.keys(),
        lambda name: files[name].read_text(encoding="utf-8", errors="ignore"),
    )
    with ZipFile(destination, "x", ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(files.keys() | extras.keys()):
            data = extras[name] if name in extras else files[name].read_bytes()
            archive.writestr(PREFIX + name, data)
            manifest["files"][name] = hashlib.sha256(data).hexdigest()
        archive.writestr(
            PREFIX + "PACKAGE-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(PREFIX + name)).hexdigest() == digest
        assert PREFIX + "source/app/cache/market_cache.py" in archive.namelist()
        # Gate 2: post-write rescan of the real archive manifest.
        staged = [
            name[len(PREFIX):]
            for name in archive.namelist()
            if name != PREFIX + "PACKAGE-MANIFEST.json"
        ]
        try:
            run_secret_gate(
                staged,
                lambda name: archive.read(PREFIX + name).decode("utf-8", errors="ignore"),
            )
        except SecretGateError as error:
            raise fail_closed(str(error)) from error
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    return {
        "archive": str(destination),
        "files": len(manifest["files"]),
        "bytes": destination.stat().st_size,
        "sha256": digest,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[2], args.output), ensure_ascii=False))
