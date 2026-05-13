from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

FORBIDDEN_NAMES = {
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
    "runtime_env",
    "storage_manifest.json",
}

ALLOW_SELF = {"dist", "cache"}


@dataclass
class HygieneFinding:
    name: str
    path: str
    size_mb: float
    file_count: int


def _dir_size(path: Path) -> tuple[float, int]:
    if path.is_file():
        return path.stat().st_size / (1024 * 1024), 1
    total = 0.0
    count = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
            count += 1
    return total / (1024 * 1024), count


def audit_release_hygiene(root: Path) -> list[HygieneFinding]:
    findings: list[HygieneFinding] = []
    for name in sorted(FORBIDDEN_NAMES):
        path = root / name
        if not path.exists():
            continue
        size_mb, file_count = _dir_size(path)
        findings.append(
            HygieneFinding(
                name=name,
                path=str(path.relative_to(root)),
                size_mb=round(size_mb, 2),
                file_count=file_count,
            )
        )
    for path in root.rglob("*.pyc"):
        if "__pycache__" not in str(path):
            findings.append(
                HygieneFinding(
                    name="orphan_pyc",
                    path=str(path.relative_to(root)),
                    size_mb=round(path.stat().st_size / 1024 / 1024, 4),
                    file_count=1,
                )
            )
    return findings


def format_text(findings: list[HygieneFinding]) -> str:
    if not findings:
        return "Release hygiene check passed. No forbidden artifacts found."
    lines = [f"Found {len(findings)} release hygiene issue(s):\n"]
    total_mb = sum(f.size_mb for f in findings)
    lines.append(f"  Total waste: {total_mb:.1f} MB\n")
    for f in findings:
        lines.append(
            f"  [{f.name}] {f.path}  ({f.size_mb:.1f} MB, {f.file_count} files)"
        )
    lines.append(
        "\nRecommendation: Add to .gitignore or clean_release.py, then run clean_release.py."
    )
    return "\n".join(lines)


def format_json(findings: list[HygieneFinding]) -> str:
    return json.dumps(
        [asdict(f) for f in findings],
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit repository for release hygiene violations."
    )
    parser.add_argument("--root", default=".", help="Repository root directory.")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = audit_release_hygiene(root)

    if args.json:
        print(format_json(findings))
    else:
        print(format_text(findings))

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
