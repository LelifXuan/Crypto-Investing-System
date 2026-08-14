from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KNOWN_PATHS = {
    "app/services/strategy": "compatibility_retained",
    "fix_all_encoding.py": "deletable_one_off",
    "fix_cache.py": "deletable_one_off",
    "fix_chip.py": "deletable_one_off",
}
RUNTIME_TEXT_PATTERNS = {
    'mode = "fixture"',
    '"mode": "fixture"',
    "btc_derivatives_snapshots.json",
}
RELEASE_RESIDUE_DIRS = {".pytest_cache", ".ruff_cache", "dist", "logs", "runtime"}


def audit_paths(root: Path = ROOT) -> list[dict[str, object]]:
    root = Path(root)
    findings: list[dict[str, object]] = []
    for relative, category in KNOWN_PATHS.items():
        path = root / relative
        if path.exists():
            findings.append(
                {
                    "category": category,
                    "path": relative,
                    "reason": "known legacy or one-off path",
                }
            )
    app_root = root / "app"
    if app_root.exists():
        for path in sorted(app_root.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            matches = sorted(pattern for pattern in RUNTIME_TEXT_PATTERNS if pattern in text)
            if matches:
                findings.append(
                    {
                        "category": "deletable_runtime_residue",
                        "path": path.relative_to(root).as_posix(),
                        "reason": ", ".join(matches),
                    }
                )
    for name in sorted(RELEASE_RESIDUE_DIRS):
        path = root / name
        if path.exists():
            findings.append(
                {
                    "category": "release_residue",
                    "path": name,
                    "reason": "generated artifact must not ship",
                }
            )
    return findings


def main() -> int:
    findings = audit_paths()
    blocking = [
        item
        for item in findings
        if item["category"] in {"deletable_runtime_residue", "deletable_one_off"}
    ]
    print(
        json.dumps(
            {
                "findings": findings,
                "count": len(findings),
                "blocking_count": len(blocking),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
