from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"


def _run_python(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PORTABLE_RUNTIME_STUB": "1"},
    )


def test_release_zip_and_portable_bundle_exclude_local_artifacts() -> None:
    _run_python(PROJECT_ROOT / "scripts" / "create_release_zip.py", PROJECT_ROOT)
    _run_python(PROJECT_ROOT / "scripts" / "build_portable_bundle.py", PROJECT_ROOT)

    release_zip = DIST_DIR / "trading-system-fastapi-github.zip"
    portable_zip = DIST_DIR / "portable_bundle.zip"
    portable_sha = DIST_DIR / "portable_bundle.zip.sha256"
    assert release_zip.exists()
    assert portable_zip.exists()
    assert portable_sha.exists()

    forbidden = (
        "run/",
        "runtime/",
        "dist/",
        ".db",
        ".db-wal",
        ".db-shm",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".log",
    )

    for archive_path in (release_zip, portable_zip):
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        assert not any("double-client.err.log" in name for name in names)
        assert not any("trading_system.db" in name for name in names)
        for entry in names:
            normalized = entry.replace("\\", "/")
            assert not any(token in normalized for token in forbidden), normalized
    with zipfile.ZipFile(portable_zip) as archive:
        names = archive.namelist()
        assert "README_PORTABLE.md" in names
        assert "portable.env.example" in names
        assert "release_manifest.json" in names
        assert "runtime_env/python/python.exe" in names
        assert "portable_runtime.lock.json" in names
        assert "requirements-portable.txt" in names
        assert "TradingSystemLauncher.exe" in names
        manifest = json.loads(archive.read("release_manifest.json").decode("utf-8"))
    assert manifest["release_type"] == "embedded_runtime_portable"
    assert manifest["python_embedded"] is True
    assert manifest["platform"] == "win-x64"
    assert manifest["python_runtime_path"] == "runtime_env/python/python.exe"
    assert manifest["file_count"] == len(manifest["files"])
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    assert "E:\\" not in manifest_text
    assert "C:\\" not in manifest_text
    assert "runtime/config/portable.env" not in manifest_text


def test_portable_bundle_preflight_and_healthcheck() -> None:
    _run_python(PROJECT_ROOT / "scripts" / "build_portable_bundle.py", PROJECT_ROOT)
    bundle_root = DIST_DIR / "portable_bundle"
    assert bundle_root.exists()
    assert (bundle_root / "runtime_env" / "python" / "python.exe").exists()
    preflight_source = (bundle_root / "scripts" / "portable_preflight.py").read_text(
        encoding="utf-8"
    )
    start_script = (bundle_root / "start_portable.bat").read_text(encoding="utf-8")
    assert "runtime_env" in preflight_source
    assert "APP_PYTHON_EXE" in start_script
    assert "where python" not in start_script
