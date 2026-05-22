from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "app/services/strategy": "legacy_workflow",
    "fix_all_encoding.py": "one_off_patch",
    "fix_cache.py": "one_off_patch",
    "fix_chip.py": "one_off_patch",
}


def main():
    findings = []
    for pattern, kind in PATTERNS.items():
        matches = list(ROOT.glob(pattern))
        if matches:
            findings.append(
                {
                    "pattern": pattern,
                    "type": kind,
                    "paths": [str(m.relative_to(ROOT)) for m in matches],
                }
            )
    if findings:
        print(
            json.dumps({"findings": findings, "count": len(findings)}, ensure_ascii=False, indent=2)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
