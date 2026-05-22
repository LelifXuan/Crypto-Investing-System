from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True

from build_embedded_python_runtime import build_runtime  # noqa: E402
from release_common import DIST_DIR as DIST_ROOT  # noqa: E402
from release_common import PROJECT_ROOT, should_skip  # noqa: E402

PORTABLE_ROOT = DIST_ROOT / "portable_bundle"
PORTABLE_ZIP = DIST_ROOT / "portable_bundle.zip"
PORTABLE_SHA256 = DIST_ROOT / "portable_bundle.zip.sha256"
RUNTIME_LOCK = PROJECT_ROOT / "portable_runtime.lock.json"
PORTABLE_REQUIREMENTS = PROJECT_ROOT / "requirements-portable.txt"
LAUNCHER_EXE = PROJECT_ROOT / "tools" / "launcher" / "publish" / "TradingSystemLauncher.exe"


def _archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_release_enabled() -> bool:
    return os.getenv("RELEASE_STRICT") == "1" or os.getenv("CI_RELEASE") == "1"


def _stub_runtime_requested() -> bool:
    return os.getenv("PORTABLE_RUNTIME_STUB") == "1"


def _run_verifier(*, strict: bool) -> None:
    verifier = PROJECT_ROOT / "scripts" / "verify_portable_release.py"
    if not verifier.exists():
        raise RuntimeError(f"portable release verifier is missing: {verifier}")
    command = [
        sys.executable,
        str(verifier),
        "--repo",
        str(PROJECT_ROOT),
        "--portable-root",
        str(PORTABLE_ROOT),
        "--zip",
        str(PORTABLE_ZIP),
        "--json-out",
        str(PROJECT_ROOT / "reports" / "verify_portable_release.json"),
    ]
    if strict:
        command.append("--strict")
    subprocess.run(command, cwd=str(PROJECT_ROOT), check=True)


def _write_manifest(runtime_metadata: dict[str, object]) -> None:
    files = [
        str(path.relative_to(PORTABLE_ROOT)).replace("\\", "/")
        for path in sorted(PORTABLE_ROOT.rglob("*"))
        if path.is_file()
    ]
    if "release_manifest.json" not in files:
        files.append("release_manifest.json")
        files.sort()
    forbidden = [
        name
        for name in files
        if name == "storage_manifest.json"
        or name.startswith(("runtime/", "run/", "logs/", "data/", "cache/", "tmp/"))
        or "/.git/" in f"/{name}/"
        or "/.venv/" in f"/{name}/"
        or "__pycache__" in name
        or name.endswith((".db", ".db-wal", ".db-shm", ".log", ".pyc", ".pyo"))
    ]
    if forbidden:
        joined = ", ".join(forbidden[:10])
        raise RuntimeError(f"portable bundle contains forbidden runtime artifacts: {joined}")
    lock = json.loads((PORTABLE_ROOT / RUNTIME_LOCK.name).read_text(encoding="utf-8"))
    manifest = {
        "release_type": "embedded_runtime_portable",
        "description": "Windows win-x64 portable bundle with embedded Python runtime.",
        "platform": "win-x64",
        "python_embedded": True,
        "python_version": lock["python_version"],
        "python_runtime_path": "runtime_env/python/python.exe",
        "portable_runtime_lock": RUNTIME_LOCK.name,
        "runtime": runtime_metadata,
        "generated_at": datetime.now(UTC).isoformat(),
        "file_count": len(files),
        "files": files,
    }
    (PORTABLE_ROOT / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    strict_release = _strict_release_enabled()
    stub_runtime = _stub_runtime_requested()
    if strict_release and stub_runtime:
        raise RuntimeError(
            "PORTABLE_RUNTIME_STUB=1 is only allowed for fast tests; official releases must "
            "use the embedded Python runtime."
        )
    if PORTABLE_ROOT.exists():
        shutil.rmtree(PORTABLE_ROOT)
    PORTABLE_ROOT.mkdir(parents=True, exist_ok=True)
    if PORTABLE_ZIP.exists():
        PORTABLE_ZIP.unlink()
    if PORTABLE_SHA256.exists():
        PORTABLE_SHA256.unlink()

    for path in PROJECT_ROOT.iterdir():
        if should_skip(path, root=PROJECT_ROOT):
            continue
        destination = PORTABLE_ROOT / path.name
        if path.is_dir():
            shutil.copytree(
                path,
                destination,
                dirs_exist_ok=True,
                ignore=lambda src, names: [
                    name for name in names if should_skip(Path(src) / name, root=PROJECT_ROOT)
                ],
            )
        else:
            shutil.copy2(path, destination)

    runtime_metadata = build_runtime(
        PORTABLE_ROOT / "runtime_env" / "python",
        lock_path=RUNTIME_LOCK,
        requirements=PORTABLE_REQUIREMENTS,
        stub=stub_runtime,
    )

    shutil.copy2(PROJECT_ROOT / "start_portable.bat", PORTABLE_ROOT / "start_portable.bat")
    shutil.copy2(PROJECT_ROOT / "start_portable.sh", PORTABLE_ROOT / "start_portable.sh")
    shutil.copy2(PROJECT_ROOT / "portable.env.example", PORTABLE_ROOT / "portable.env.example")
    shutil.copy2(PROJECT_ROOT / "README_PORTABLE.md", PORTABLE_ROOT / "README_PORTABLE.md")
    portable_env = PROJECT_ROOT / ".env"
    if portable_env.exists():
        runtime_config = PORTABLE_ROOT / "runtime" / "config"
        runtime_config.mkdir(parents=True, exist_ok=True)
        shutil.copy2(portable_env, runtime_config / "portable.env")
    shutil.copy2(RUNTIME_LOCK, PORTABLE_ROOT / RUNTIME_LOCK.name)
    shutil.copy2(PORTABLE_REQUIREMENTS, PORTABLE_ROOT / PORTABLE_REQUIREMENTS.name)
    if LAUNCHER_EXE.exists():
        shutil.copy2(LAUNCHER_EXE, PORTABLE_ROOT / "TradingSystemLauncher.exe")
    _write_manifest(runtime_metadata)
    archive_base = str(PORTABLE_ZIP.with_suffix(""))
    shutil.make_archive(archive_base, "zip", root_dir=PORTABLE_ROOT)
    PORTABLE_SHA256.write_text(
        f"{_archive_sha256(PORTABLE_ZIP)}  {PORTABLE_ZIP.name}\n",
        encoding="utf-8",
    )
    print(f"portable bundle created at {PORTABLE_ROOT}")
    print(f"portable zip created at {PORTABLE_ZIP}")
    print(f"portable sha256 created at {PORTABLE_SHA256}")
    if not stub_runtime:
        _run_verifier(strict=strict_release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
