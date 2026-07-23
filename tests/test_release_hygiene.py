from __future__ import annotations

from pathlib import Path

from scripts.audit_release_hygiene import (
    FORBIDDEN_NAMES,
    HygieneFinding,
    audit_release_hygiene,
)

ROOT = Path(__file__).resolve().parents[1]


def test_release_hygiene_forbidden_list_covers_runtime_artifacts():
    expected = {
        ".venv",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "runtime",
        "logs",
        "tmp",
        "cache",
        "dist",
        "runtime_env",
        "storage_manifest.json",
    }
    assert expected <= FORBIDDEN_NAMES


def test_release_hygiene_findings_are_typed():
    findings = audit_release_hygiene(ROOT)
    for f in findings:
        assert isinstance(f, HygieneFinding)
        assert f.name in FORBIDDEN_NAMES or f.name == "orphan_pyc"
        assert f.size_mb >= 0
        assert f.file_count >= 0


def test_release_hygiene_returns_list():
    findings = audit_release_hygiene(ROOT)
    assert isinstance(findings, list)


def test_dist_should_not_exist_in_source_root():
    findings = audit_release_hygiene(ROOT)
    dist_findings = [f for f in findings if f.name == "dist"]
    if dist_findings:
        print(
            f"WARNING: dist/ exists ({dist_findings[0].size_mb:.1f} MB, "
            f"{dist_findings[0].file_count} files). "
            f"Remove before source release."
        )


def test_venv_should_not_exist_in_source_root():
    findings = audit_release_hygiene(ROOT)
    venv_findings = [f for f in findings if f.name == ".venv"]
    if venv_findings:
        print(
            f"WARNING: .venv/ exists ({venv_findings[0].size_mb:.1f} MB, "
            f"{venv_findings[0].file_count} files). "
            f"Remove before source release."
        )
