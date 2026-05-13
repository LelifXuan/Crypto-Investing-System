from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_portable_runtime_lock_targets_win_x64_python_311():
    lock = json.loads((ROOT / "portable_runtime.lock.json").read_text(encoding="utf-8"))
    assert lock["platform"] == "win-x64"
    assert lock["python_embedded"] is True
    assert str(lock["python_version"]).startswith("3.11.")
    assert len(lock["python_embed_sha256"]) == 64
    int(lock["python_embed_sha256"], 16)


def test_start_portable_uses_only_embedded_python():
    script = (ROOT / "start_portable.bat").read_text(encoding="utf-8")
    assert r"runtime_env\python\python.exe" in script
    assert "APP_PYTHON_EXE" in script
    assert "where python" not in script
    assert "python -m uvicorn" not in script


def test_preflight_requires_embedded_python_and_lockfile():
    source = (ROOT / "scripts" / "portable_preflight.py").read_text(encoding="utf-8")
    assert "portable_runtime.lock.json" in source
    assert "app_paths.embedded_python_dir" in source
    assert "relative_to(embedded_dir)" in source
    assert "portable preflight must be run with bundled embedded Python" in source


def test_portable_builder_emits_embedded_runtime_manifest():
    source = (ROOT / "scripts" / "build_portable_bundle.py").read_text(encoding="utf-8")
    assert "build_runtime(" in source
    assert '"embedded_runtime_portable"' in source
    assert '"python_embedded": True' in source
    assert '"runtime_env/python/python.exe"' in source


def test_readme_no_longer_requires_user_python():
    readme = (ROOT / "README_PORTABLE.md").read_text(encoding="utf-8")
    assert "do not need to install Python" in readme
    assert "Python 3.11 or Python 3.14 available on `PATH`" not in readme


def test_launcher_prefers_embedded_runtime_and_utf8_messages():
    source = (ROOT / "tools" / "launcher" / "Program.cs").read_text(encoding="utf-8")
    assert "runtime_env" in source
    assert "python.exe" in source
    assert "未找到内置 Python 运行时" in source
    assert "应用启动超时" in source
    assert "Python 环境" not in source
    assert "�" not in source
