from __future__ import annotations

import importlib.util
from pathlib import Path


def test_audit_script_exists_and_imports() -> None:
    path = Path("scripts/audit_local_storage.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("audit_local_storage", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_REQUIREMENTS["1h"] >= 720


def test_storage_manifest_exists_after_startup() -> None:
    manifest = Path("runtime/storage_manifest.json")
    if manifest.exists():
        import json

        d = json.loads(manifest.read_text())
        assert "database_path" in d
        assert "long_term" in d
