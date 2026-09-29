"""Build an explicitly authorized, unencrypted internal bundle from the workspace.

Never invoke this builder for a public release: source/.env is included byte-for-byte.
No secret values are printed. Runtime caches are excluded by path, not by the
word 'cache', because app/cache is application source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def include_source(name: str) -> bool:
    path = PurePosixPath(name)
    if EXCLUDED_DIRS.intersection(path.parts) or path.name.lower() in {"nul", ".coverage"}:
        return False
    if path.name.endswith(EXCLUDED_SUFFIXES):
        return False
    return not path.name.startswith(".env") or path.name == ".env.example"


NOTES = """# CIS UI 2.0 — {delivery}（内部便携包）

{security_notice}
包含 Windows Python 3.11、依赖、当前工作区代码；无需安装系统 Python。
完整解压后双击 start.bat，访问 http://127.0.0.1:8002/monitoring-page。
按 Ctrl+C 停止服务。不要直接从压缩包内部启动。

不含历史数据库、运行缓存、日志或验收截图；app/cache 是业务源码，已保留。
启动器将运行目录与数据库限定在当前解压目录。没有历史数据时显示构建中或降级状态。
代理与第三方密钥沿用现有 .env；跨机器请检查代理设置。本包不代表外部数据源可用性认证。
正式 Workbench 页面：{workbench_pages}；不是完整 P2 页面迁移交付。
旧版本首次升级后请 Ctrl+Shift+R 一次；之后 HTML 与子模块自动协商缓存更新。
"""


def package_notes(manifest: dict) -> str:
    """Derive warnings from the actual manifest, never from a stale release label."""
    encryption = "ZIP 已加密" if manifest["encrypted"] else "ZIP 未加密"
    contents = "包含原样 source/.env 和密钥" if manifest["contains_secrets"] else "不包含密钥"
    return NOTES.format(
        delivery=manifest["delivery"],
        security_notice=f"警告：{encryption}，{contents}。仅限授权内部使用，禁止公开上传。",
        workbench_pages="、".join(manifest["workbench_pages"]),
    )


START = r"""@echo off
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
echo INTERNAL UNENCRYPTED PACKAGE - CONTAINS SECRETS
echo Open http://127.0.0.1:8002/monitoring-page - Ctrl+C to stop.
"runtime_python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8002
pause
"""


def build(root: Path, destination: Path) -> dict:
    root = root.resolve()
    runtime = root / "source/runtime_python"
    env_path = root / "source/.env"
    if not env_path.is_file() or not (runtime / "python.exe").is_file():
        raise RuntimeError("Missing authorized .env or embedded Python")
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
    files["source/.env"] = env_path
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
        "contains_secrets": True,
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
        assert archive.read(PREFIX + "source/.env") == env_path.read_bytes()
        assert PREFIX + "source/app/cache/market_cache.py" in archive.namelist()
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
    parser.add_argument("--include-authorized-env", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[2], args.output), ensure_ascii=False))
