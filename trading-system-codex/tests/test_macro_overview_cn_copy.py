from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACRO_FILE = ROOT / "app" / "services" / "macro_overview.py"


def test_macro_overview_no_empty_or_slash_only_labels():
    text = MACRO_FILE.read_text(encoding="utf-8", errors="replace")
    violations = []

    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("label_cn="):
            value = stripped.split("label_cn=", 1)[1]
            if value in ('""', "''"):
                violations.append((line_no, f"empty label_cn at line {line_no}"))
            elif value in ('" / "', "' / '", '"/ "', "'/ '", '" /"', "' /'"):
                violations.append((line_no, f"slash-only label_cn at line {line_no}: {value}"))

    assert violations == [], f"Broken label_cn found: {violations}"


def test_macro_overview_no_stale_insight_placeholder():
    text = MACRO_FILE.read_text(encoding="utf-8", errors="replace")
    assert 'insight=","' not in text, "Stale insight=',' placeholder still present"
    assert "insight=', '" not in text, "Stale insight=', ' placeholder still present"
