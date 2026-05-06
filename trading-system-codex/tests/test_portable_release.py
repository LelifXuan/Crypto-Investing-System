from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
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
        manifest = json.loads(archive.read("release_manifest.json").decode("utf-8"))
    assert manifest["release_type"] == "source_portable"
    assert manifest["file_count"] == len(manifest["files"])
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    assert "E:\\" not in manifest_text
    assert "C:\\" not in manifest_text
    assert "runtime/config/portable.env" not in manifest_text


def test_portable_bundle_preflight_and_healthcheck() -> None:
    _run_python(PROJECT_ROOT / "scripts" / "build_portable_bundle.py", PROJECT_ROOT)
    bundle_root = DIST_DIR / "portable_bundle"
    assert bundle_root.exists()

    preflight = subprocess.run(
        [sys.executable, str(bundle_root / "scripts" / "portable_preflight.py")],
        cwd=str(bundle_root),
        capture_output=True,
        text=True,
        env={**os.environ, "APP_PORT": "8021", "APP_DISTRIBUTION_MODE": "portable"},
        check=True,
    )
    assert "Portable preflight" in preflight.stdout

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8021"],
        cwd=str(bundle_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={
            **os.environ,
            "APP_PORT": "8021",
            "APP_DISTRIBUTION_MODE": "portable",
            "APP_BUNDLE_ROOT": str(bundle_root),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    try:
        for _ in range(20):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8021/health", timeout=1) as response:
                    body = response.read().decode("utf-8")
                    assert response.status == 200
                    assert "ok" in body.lower()
                    break
            except Exception:
                time.sleep(0.5)
        else:
            raise AssertionError("portable bundle service did not become healthy in time")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
