from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=merged_env,
        check=False,
    )


def test_strict_release_rejects_stub_runtime_request():
    result = _run(
        [sys.executable, "scripts/build_portable_bundle.py"],
        env={"RELEASE_STRICT": "1", "PORTABLE_RUNTIME_STUB": "1"},
    )
    assert result.returncode != 0
    assert "PORTABLE_RUNTIME_STUB=1" in (result.stderr + result.stdout)


@pytest.mark.skipif(
    os.getenv("RUN_PORTABLE_RELEASE_TESTS") != "1" and os.getenv("RELEASE_STRICT") != "1",
    reason="real embedded runtime build is release-only because it downloads and installs deps",
)
def test_strict_release_build_and_verifier_pass():
    build = _run([sys.executable, "scripts/build_portable_bundle.py"], env={"RELEASE_STRICT": "1"})
    assert build.returncode == 0, build.stderr + build.stdout

    verify = _run(
        [
            sys.executable,
            "scripts/verify_portable_release.py",
            "--repo",
            ".",
            "--portable-root",
            "dist/portable_bundle",
            "--zip",
            "dist/portable_bundle.zip",
            "--strict",
            "--json-out",
            "reports/verify_portable_release.json",
        ]
    )
    assert verify.returncode == 0, verify.stderr + verify.stdout
