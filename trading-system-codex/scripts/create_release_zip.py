from __future__ import annotations

import sys
from zipfile import ZIP_DEFLATED, ZipFile

sys.dont_write_bytecode = True

from release_common import DIST_DIR, PROJECT_ROOT, should_skip  # noqa: E402

OUTPUT = DIST_DIR / "trading-system-fastapi-github.zip"
PREFIX = "trading-system-fastapi/"


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if path.is_dir() or should_skip(path, root=PROJECT_ROOT):
                continue
            rel = path.relative_to(PROJECT_ROOT)
            zf.write(path, PREFIX + rel.as_posix())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
