from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TEXT_EXTENSIONS = {".py", ".js", ".html", ".css", ".md", ".json", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "runtime",
    "logs",
    "tmp",
    "cache",
    "dist",
    "data",
}
MOJIBAKE_PATTERNS = re.compile(
    r"\ufffd|锟|閿|ã|â|â¬|æ|ç|è®|å|æ|æ|"
    r"¥º|ºº|Â£|¨Â|¨¶|||æ[\\x80-\\xff]|ç[\\x80-\\xff]|è[\\x80-\\xff]",
    re.IGNORECASE,
)
SEVERE_PATTERN = re.compile(r"\ufffd|锟|閿|¥º|ºº|Â£|¨Â|¨¶||")

STARTUP_CRITICAL_FILES = {
    "app/main.py",
    "app/api/router.py",
    "app/api/dependencies.py",
    "app/core/config.py",
    "app/core/db.py",
    "app/core/paths.py",
    "app/core/security.py",
}

DISPLAY_BUSINESS_FILES = {
    "app/templates/",
    "app/static/",
    "app/web/router.py",
    "app/api/v1/endpoints/strategy.py",
    "app/api/v1/endpoints/alerts.py",
    "app/api/v1/endpoints/market_events.py",
    "app/api/v1/endpoints/monitoring.py",
    "app/schemas/",
}

SANITIZER_ALLOWED_FILES = {
    "scripts/audit_mojibake.py",
    "tests/test_mojibake_audit.py",
    "tests/test_strategy_frontend_static.py",
    "tests/test_knowledge_catalog.py",
    "tests/test_market_event_translation.py",
}

ARCHIVE_DOC_DIRS = {
    "docs/",
    "_github_ready_ref/",
    "_tmp_",
}


@dataclass
class MojibakeFinding:
    file_path: str
    line: int
    content: str
    severity: str  # block, display, sanitizer, archive, warn
    category: str  # startup, display_business, sanitizer, archive, other


def _classify_file(rel_path: str) -> tuple[str, str]:
    """Return (category, default_severity)."""
    normalized = rel_path.replace("\\", "/")
    if any(normalized.startswith(d) for d in ARCHIVE_DOC_DIRS):
        return "archive", "warn"
    if normalized in SANITIZER_ALLOWED_FILES or any(
        part.startswith("_tmp") for part in Path(rel_path).parts
    ):
        return "sanitizer", "warn"
    if normalized in STARTUP_CRITICAL_FILES:
        return "startup", "block"
    if any(normalized.startswith(d) for d in DISPLAY_BUSINESS_FILES):
        return "display_business", "display"
    return "other", "warn"


def _is_severe_pattern(text: str) -> bool:
    return bool(SEVERE_PATTERN.search(text))


def _is_comment_only(line: str, suffix: str) -> bool:
    stripped = line.strip()
    if suffix == ".py":
        return stripped.startswith("#")
    if suffix in {".js", ".ts"}:
        return stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")
    if suffix == ".html":
        return stripped.startswith("<!--")
    return False


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_EXTENSIONS:
            continue
        if set(path.relative_to(root).parts) & SKIP_DIRS:
            continue
        yield path


def audit_mojibake(
    root: Path,
    paths: list[str] | None = None,
) -> list[MojibakeFinding]:
    targets = [root / item for item in paths] if paths else list(iter_text_files(root))
    findings: list[MojibakeFinding] = []
    for path in targets:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(root))
        category, default_severity = _classify_file(rel)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not MOJIBAKE_PATTERNS.search(line):
                continue
            if _is_comment_only(line, path.suffix):
                continue
            if _is_severe_pattern(line):
                severity = (
                    "block" if category in {"startup", "display_business"} else default_severity
                )
            else:
                severity = default_severity
            findings.append(
                MojibakeFinding(
                    file_path=rel,
                    line=line_no,
                    content=line[:200],
                    severity=severity,
                    category=category,
                )
            )
    return findings


def format_text(findings: list[MojibakeFinding]) -> str:
    if not findings:
        return "No mojibake findings."
    lines = [f"Found {len(findings)} mojibake issue(s):\n"]
    for f in findings:
        lines.append(f"  [{f.severity.upper()}] {f.file_path}:{f.line} ({f.category})")
        lines.append(f"    {f.content}")
    return "\n".join(lines)


def format_json(findings: list[MojibakeFinding]) -> str:
    return json.dumps(
        [asdict(f) for f in findings],
        ensure_ascii=False,
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit text files for mojibake (encoding corruption)."
    )
    parser.add_argument("--root", default=".", help="Repository root directory.")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON.")
    parser.add_argument(
        "--block-on-display",
        action="store_true",
        help="Exit with code 1 if any display_business or startup file has mojibake.",
    )
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = audit_mojibake(root, args.paths or None)

    if args.json:
        print(format_json(findings))
    else:
        print(format_text(findings))

    if not findings:
        return 0
    if args.block_on_display:
        blocks = [f for f in findings if f.severity in {"block", "display"}]
        if blocks:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
