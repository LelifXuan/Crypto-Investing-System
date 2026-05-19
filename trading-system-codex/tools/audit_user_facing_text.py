#!/usr/bin/env python
"""Audit user-facing text for patterns that push judgment to users.

Scans app/static/**, app/services/**, app/templates/** for forbidden
and warning patterns. Exits 1 if any forbidden pattern is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATTERNS = [
    re.compile(p) for p in [
        r"若综合仍偏[多空].*说明",
        r"说明其他系统.*抵消",
        r"其他系统仍在抵消",
        r"用户自行",
        r"自行判断",
        r"自行确认",
        r"自己判断",
    ]
]

WARN_PATTERNS = [
    re.compile(p) for p in [
        r"若[^。；;\n]{0,60}(?:说明|表示|意味着)",
        r"如果[^。；;\n]{0,60}(?:说明|表示|意味着)",
    ]
]

SCAN_GLOBS = [
    "app/static/pages/**/*.js",
    "app/static/core/**/*.js",
    "app/services/**/*.py",
    "app/templates/**/*.html",
]

ALLOW_FORBIDDEN = {
    Path("app/static/core/knowledge.js"),
}


def scan_file(path: Path, strict_warn: bool = False) -> list[str]:
    issues = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return issues

    for pattern in FORBIDDEN_PATTERNS:
        matches = pattern.findall(content)
        for match in matches:
            if path in ALLOW_FORBIDDEN:
                continue
            line_num = _find_line(content, match)
            issues.append(f"[FAIL] {path}:{line_num} contains forbidden operational text: {match}")

    for pattern in WARN_PATTERNS:
        matches = pattern.findall(content)
        for match in matches:
            level = "FAIL" if strict_warn else "WARN"
            line_num = _find_line(content, match)
            issues.append(f"[{level}] {path}:{line_num} contains vague conditional text: {match}")

    return issues


def _find_line(content: str, match: str) -> int:
    idx = content.find(match)
    if idx < 0:
        return 0
    return content[:idx].count("\n") + 1


def main() -> int:
    strict_warn = "--strict-warn" in sys.argv

    issues: list[str] = []
    for glob_pattern in SCAN_GLOBS:
        for file_path in sorted(ROOT.glob(glob_pattern)):
            issues.extend(scan_file(file_path, strict_warn=strict_warn))

    if issues:
        for issue in issues:
            print(issue)

    failures = sum(1 for issue in issues if issue.startswith("[FAIL]"))
    warnings = sum(1 for issue in issues if issue.startswith("[WARN]"))

    print(f"\n{failures} failures, {warnings} warnings")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
