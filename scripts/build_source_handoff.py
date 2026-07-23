from __future__ import annotations

import argparse
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised by command-line execution
    from release_common import PROJECT_ROOT, scan_secret_like_content, should_skip
except ModuleNotFoundError:  # pragma: no cover - exercised by pytest package import
    from scripts.release_common import PROJECT_ROOT, scan_secret_like_content, should_skip


def build_source_handoff(source_root: Path, output_zip: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_zip = output_zip.resolve()
    included: list[str] = []
    blocked: list[dict[str, str]] = []
    candidates = [path for path in sorted(source_root.rglob("*")) if path.is_file()]
    secret_findings = scan_secret_like_content(candidates)
    secret_paths = {finding.path.resolve() for finding in secret_findings}

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            rel = path.relative_to(source_root).as_posix()
            if path.resolve() in secret_paths:
                blocked.append({"path": rel, "reason": "secret_like_content"})
                continue
            if should_skip(path, root=source_root):
                blocked.append({"path": rel, "reason": "release_excluded"})
                continue
            if rel.endswith((".zip", ".7z")):
                blocked.append({"path": rel, "reason": "nested_archive"})
                continue
            archive.write(path, rel)
            included.append(rel)

    manifest = {
        "schema_version": "source-handoff-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_root": str(source_root),
        "archive": str(output_zip),
        "included_files": included,
        "blocked_files": blocked,
        "secret_finding_count": len(secret_findings),
    }
    manifest_path = output_zip.with_suffix(output_zip.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized source handoff archive.")
    parser.add_argument("--source-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "dist" / "source_handoff.zip",
    )
    args = parser.parse_args()
    report = build_source_handoff(args.source_root, args.output)
    print(json.dumps({k: report[k] for k in ("archive", "secret_finding_count")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
