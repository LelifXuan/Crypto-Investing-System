from __future__ import annotations

from pathlib import Path

from scripts.audit_mojibake import MojibakeFinding, audit_mojibake

ROOT = Path(__file__).resolve().parents[1]

STRATEGY_USER_VISIBLE = [
    "app/static/pages/strategy.js",
    "app/static/main.js",
    "app/templates/page.html",
    "app/web/router.py",
    "app/schemas/strategy.py",
    "app/api/v1/endpoints/strategy.py",
]

CRITICAL_STARTUP = [
    "app/main.py",
    "app/api/router.py",
    "app/core/config.py",
    "app/core/db.py",
]


def _filter_display(findings: list[MojibakeFinding]) -> list[MojibakeFinding]:
    return [f for f in findings if f.severity in {"block", "display"}]


def test_strategy_user_visible_files_have_no_mojibake():
    findings = audit_mojibake(ROOT, STRATEGY_USER_VISIBLE)
    assert findings == [], (
        f"Strategy UI files contain mojibake: "
        f"{[(f.file_path, f.line, f.content[:80]) for f in findings]}"
    )


def test_critical_startup_files_have_no_display_mojibake():
    findings = _filter_display(audit_mojibake(ROOT, CRITICAL_STARTUP))
    assert findings == [], (
        f"Critical startup files have display-level mojibake: "
        f"{[(f.file_path, f.line) for f in findings]}"
    )


def test_api_endpoints_have_no_display_mojibake():
    endpoint_dir = ROOT / "app" / "api" / "v1" / "endpoints"
    py_files = list(endpoint_dir.glob("*.py"))
    paths = [str(p.relative_to(ROOT)) for p in py_files]
    findings = _filter_display(audit_mojibake(ROOT, paths))
    assert findings == [], (
        f"API endpoints have display-level mojibake: "
        f"{[(f.file_path, f.line) for f in findings]}"
    )


def test_schema_files_have_no_display_mojibake():
    schema_dir = ROOT / "app" / "schemas"
    py_files = list(schema_dir.glob("*.py"))
    paths = [str(p.relative_to(ROOT)) for p in py_files]
    findings = _filter_display(audit_mojibake(ROOT, paths))
    assert findings == [], (
        f"Schema files have display-level mojibake: "
        f"{[(f.file_path, f.line) for f in findings]}"
    )


def test_sanitizer_files_are_not_blocked_by_default():
    """Sanitizer files may contain mojibake patterns for detection - only check severity."""
    findings = audit_mojibake(ROOT, ["scripts/audit_mojibake.py"])
    blocks = [f for f in findings if f.severity == "block"]
    assert blocks == [], f"Sanitizer script incorrectly classified as block-level: {blocks}"


def test_audit_script_handles_nonexistent_paths():
    findings = audit_mojibake(ROOT, ["nonexistent/file.py"])
    assert findings == []
