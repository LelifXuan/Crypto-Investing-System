from __future__ import annotations

from pathlib import Path

from scripts.audit_redundant_workflows import audit_paths


def test_audit_classifies_runtime_fixture_and_release_residue(tmp_path: Path) -> None:
    runtime_file = tmp_path / "app" / "services" / "feature.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('mode = "fixture"\n', encoding="utf-8")
    residue = tmp_path / "dist" / "portable_bundle.zip"
    residue.parent.mkdir(parents=True)
    residue.write_text("zip", encoding="utf-8")

    findings = audit_paths(tmp_path)

    categories = {item["category"] for item in findings}
    assert "deletable_runtime_residue" in categories
    assert "release_residue" in categories
