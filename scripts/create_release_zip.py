from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile

sys.dont_write_bytecode = True

from release_common import DIST_DIR, PROJECT_ROOT, should_skip  # noqa: E402

OUTPUT = DIST_DIR / "trading-system-fastapi-github.zip"
MANIFEST = DIST_DIR / "release_manifest.json"
PREFIX = "trading-system-fastapi/"


def sha256_hex(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if path.is_dir() or should_skip(path, root=PROJECT_ROOT):
                continue
            rel = path.relative_to(PROJECT_ROOT)
            zf.write(path, PREFIX + rel.as_posix())
    print(f"Wrote {OUTPUT}")

    checksum = sha256_hex(OUTPUT)
    sha_path = DIST_DIR / "trading-system-fastapi-github.zip.sha256"
    sha_path.write_text(f"{checksum}  trading-system-fastapi-github.zip\n", encoding="utf-8")
    print(f"Wrote {sha_path}")

    manifest = {
        "version": "see pyproject.toml",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sha256": checksum,
        "file": "trading-system-fastapi-github.zip",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST}")


if __name__ == "__main__":
    main()
